package io.raph.speakerstudio;

import android.annotation.SuppressLint;
import android.bluetooth.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;

/** Commands run on the activity's worker, notifications on the socket reader. No polling. */
@SuppressLint("MissingPermission") // Activity gates all operations on BLUETOOTH_CONNECT.
final class SpeakerController implements Closeable {
    private static final UUID SPP = UUID.fromString("00001101-0000-1000-8000-00805f9b34fb");
    private final Runnable changed;
    private final java.util.function.LongSupplier monotonic;
    private final Sleeper sleeper;
    private final long receiverTimeout;
    private final Set<String> unresolvedReceivers=ConcurrentHashMap.newKeySet();
    private final Map<String,String> levelProblems=new ConcurrentHashMap<>();
    static final class LevelUnavailable extends IOException {LevelUnavailable(String message){super(message);}}
    private volatile long groupReadyAt;
    interface Sleeper { void sleep(long milliseconds) throws InterruptedException; }
    private final ScheduledExecutorService timer = Executors.newSingleThreadScheduledExecutor();
    private final Map<String, CompletableFuture<Void>> events = new ConcurrentHashMap<>();
    private final Map<String, Protocol.Member> members = new ConcurrentHashMap<>();
    private volatile LegacySession session;
    private volatile BluetoothSocket connecting;
    private volatile boolean stopped;
    volatile String name="", model="", address="";
    volatile int broadcast=0, audioMode=0, battery=-1, volume=-1, steps=31, eq=-1, balance=0;
    volatile String firmware="";
    volatile int finishCode=-1;
    volatile boolean renameSupported, customSupported, balanceSupported;
    volatile byte[] bands;
    private final Map<String,Integer> levels=new ConcurrentHashMap<>();
    private final Map<String,CompletableFuture<Integer>> attributes=new ConcurrentHashMap<>();
    volatile boolean inventoryKnown=false, groupSupported=false;
    SpeakerController(Runnable changed) { this(changed,()->System.nanoTime()/1_000_000,Thread::sleep); }
    SpeakerController(Runnable changed,java.util.function.LongSupplier monotonic,Sleeper sleeper) {
        this(changed,monotonic,sleeper,8000);
    }
    SpeakerController(Runnable changed,java.util.function.LongSupplier monotonic,Sleeper sleeper,long receiverTimeout) {
        this.changed=changed;this.monotonic=monotonic;this.sleeper=sleeper;this.receiverTimeout=receiverTimeout;
    }
    private void groupSettling() { groupReadyAt=monotonic.getAsLong()+6000; }
    private void awaitGroupReady() throws InterruptedException {
        long remaining;
        while((remaining=groupReadyAt-monotonic.getAsLong())>0) sleeper.sleep(remaining);
    }
    private void groupSet(LegacySession session,int command,byte... payload) throws Exception {
        for(int attempt=0;;attempt++) {
            try { session.set(command,payload); return; }
            catch(LegacySession.CommandError error) {
                // Only an explicit BUSY rejection is safe to resend, never a timeout.
                if(error.status!=9 || attempt==2) throw error;
                sleeper.sleep(300L*(attempt+1));
            }
        }
    }
    boolean connected() { LegacySession current=session; return current!=null && current.isOpen(); }
    List<Protocol.Member> members() {
        List<Protocol.Member> result = new ArrayList<>(members.values());
        result.sort(Comparator.comparing(Protocol.Member::address)); return result;
    }
    private LegacySession open(BluetoothDevice device, boolean host) throws Exception {
        if (stopped) throw new IOException("Controls closed");
        BluetoothSocket socket=device.createRfcommSocketToServiceRecord(SPP);
        connecting=socket;
        ScheduledFuture<?> timeout=null;
        try {
            if (stopped) throw new IOException("Controls closed");
            timeout=timer.schedule(() -> { try { socket.close(); } catch(IOException ignored) {} }, 15, TimeUnit.SECONDS);
            socket.connect();
            if (stopped) throw new IOException("Controls closed");
            return new LegacySession(socket.getInputStream(), socket.getOutputStream(), socket,
                host ? this::notification : m -> false,
                host ? () -> {
                    groupSupported=false; members.clear(); inventoryKnown=false;
                    events.values().forEach(f -> f.completeExceptionally(new IOException("Host disconnected. Reconnect.")));
                    attributes.values().forEach(f -> f.completeExceptionally(new IOException("Host disconnected. Reconnect.")));
                    levels.clear();
                    changed.run();
                } : () -> {});
        } catch(Exception error) { socket.close(); throw error; }
        finally { if(timeout!=null) timeout.cancel(false); connecting=null; }
    }
    void connect(BluetoothDevice device) throws Exception {
        disconnect();
        address=device.getAddress(); name=device.getName()==null ? address : device.getName();
        session=open(device,true);
        try {
            if(stopped) throw new IOException("Controls closed");
            model=Protocol.model(session.query(6,7));
            refresh();
            readFinish();
        }
        catch(Exception error) { disconnect(); throw error; }
    }
    void readFinish() throws Exception {
        try {
            byte[] finish=optional(requireSession(),0x1be,0x1bf);
            if(finish!=null && finish.length==2)finishCode=Protocol.u16(finish,0);
        } catch(LegacySession.CommandError error) {
            // Appearance is optional. A busy speaker can keep its remembered colour.
            if(error.status!=9)throw error;
        }
    }
    private LegacySession requireSession() throws IOException {
        if (!connected()) throw new IOException("Connect a host speaker first"); return session;
    }
    private byte[] config(LegacySession s) throws Exception {
        byte[] p=null;
        for (int i=0; i<8; i++) {
            try { p=s.query(0x414,0x415); break; }
            catch (LegacySession.CommandError e) { if (e.status!=9 || i==7) throw e; sleeper.sleep(350); }
        }
        if (p==null || p.length!=2 || (p[0]&255)>3) throw new IOException("Invalid group configuration");
        broadcast=p[0]&255; audioMode=p[1]&255;
        if ((broadcast&2)==0) { members.clear(); levels.clear(); inventoryKnown=false; }
        return p;
    }
    void refresh() throws Exception {
        LegacySession s=requireSession();
        try { config(s); groupSupported=true; }
        catch (LegacySession.CommandError e) { if(e.status!=1) throw e; groupSupported=false; }
        try {
            byte[] p=s.query(0x175,0x176);
            if(p.length<12 || (p[4]&255)>100) throw new IOException("Invalid battery reading");
            battery=p[4]&255;
        } catch (LegacySession.CommandError e) { if(e.status!=1) throw e; battery=-1; }
        readVolume(s);
        byte[] p=optional(s,0x16d,0x16e); renameSupported=p!=null;
        if(p!=null) name=SpeakerSettings.decodeName(p);
        p=optional(s,3,4);
        if(p!=null) { if(p.length==0) throw new IOException("Invalid firmware version");
            StringJoiner version=new StringJoiner("."); for(byte n:p) version.add(Integer.toString(n&255)); firmware=version.toString(); }
        p=optional(s,0x177,0x178); eq=-1;
        if(p!=null) { if(p.length!=1 || (p[0]&255)>4) throw new IOException("Invalid equalizer reading"); eq=p[0]&255; }
        p=optional(s,0x188,0x189); customSupported=p!=null && p.length>=5; bands=customSupported?Arrays.copyOf(p,5):null;
        balanceSupported=false;
        if((broadcast&2)!=0) { p=optional(s,0x19b,0x19c); balanceSupported=p!=null && p.length==1; if(balanceSupported) balance=p[0]; }
        changed.run();
    }
    private byte[] optional(LegacySession s,int command,int response) throws Exception {
        try { return s.query(command,response); }
        catch(LegacySession.CommandError e) { if(e.status!=1) throw e; return null; }
    }
    void rename(String value) throws Exception {
        if(!renameSupported) throw new IOException("Naming is unavailable on this speaker");
        LegacySession s=requireSession(); String expected=value.trim();
        s.set(0x16f,SpeakerSettings.encodeName(value)); name=SpeakerSettings.decodeName(s.query(0x16d,0x16e));
        if(!name.equals(expected)) throw new IOException("Speaker stored the name as "+name);
        changed.run();
    }
    void preset(int code) throws Exception {
        if(eq<0 || code<0 || code>4) throw new IOException("Equalizer unavailable");
        requireSession().set(0x179,(byte)code); refresh();
        if(eq!=code) throw new IOException("Speaker did not confirm sound profile");
    }
    void custom(byte[] values) throws Exception {
        if(!customSupported || values==null || values.length!=5) throw new IOException("Five custom EQ bands required");
        requireSession().set(0x18a,values); preset(4);
        if(!Arrays.equals(values,bands)) throw new IOException("Speaker did not confirm custom EQ levels");
    }
    void identify() throws Exception { requireSession().set(0x16b); }
    void powerOff() throws Exception { requireSession().set(0x1b6); disconnect(); }
    void balance(int value) throws Exception {
        LegacySession s=requireSession(); config(s);
        if(!balanceSupported || !inventoryKnown || members.size()!=1 || audioMode!=0x50 || (broadcast&2)==0)
            throw new IOException("Select Stereo with exactly two speakers before adjusting balance");
        if(value< -128 || value>127) throw new IOException("Invalid balance");
        s.set(0x19d,(byte)value); byte[] p=s.query(0x19b,0x19c);
        if(p.length!=1) throw new IOException("Invalid balance reading"); balance=p[0]; changed.run();
    }
    Integer memberLevel(String target) { return levels.get(target); }
    String memberLevelProblem(String target) {return levelProblems.getOrDefault(target,"Individual level not read");}
    private int attribute(String target,Integer value) throws Exception {
        LegacySession s=requireSession();
        if((broadcast&2)==0 || !members.containsKey(target)) throw new IOException("Receiver is no longer in this group");
        if(unresolvedReceivers.contains(target))throw new LevelUnavailable("Individual read unavailable until controls reconnect");
        int event=value==null?0x421:0x423; String key=event+":"+target;
        CompletableFuture<Integer> done=new CompletableFuture<>(); attributes.put(key,done);
        byte[] payload=Arrays.copyOf(Protocol.mac(target),value==null?8:9); payload[6]=0; payload[7]=0x1e;
        if(value!=null) payload[8]=value.byteValue();
        try { s.set(value==null?0x420:0x422,payload); return done.get(receiverTimeout,TimeUnit.MILLISECONDS); }
        catch(TimeoutException e) {
            // The queue ACK completed. Quarantine this receiver's unsequenced
            // results, while leaving unrelated host controls and audio usable.
            unresolvedReceivers.add(target);levels.remove(target);
            throw new LevelUnavailable("Individual volume not reported");
        }
        catch(ExecutionException e) { if(e.getCause() instanceof LevelUnavailable unavailable)throw unavailable;throw new IOException(e.getCause().getMessage(),e.getCause()); }
        finally { attributes.remove(key); }
    }
    void groupLevels() throws Exception {
        awaitGroupReady();
        readVolume(requireSession());
        for(Protocol.Member member:members()) readMemberLevel(member.address());
        changed.run();
    }
    void readMemberLevel(String target) throws Exception {
        awaitGroupReady();
        try { attribute(target,null); }
        catch(LevelUnavailable e) {levels.remove(target);levelProblems.put(target,e.getMessage());}
        catch(LegacySession.CommandError e) {if(e.status!=1)throw e;levels.remove(target);levelProblems.put(target,"Individual volume unsupported");}
        changed.run();
    }
    void memberVolume(String target,int percent) throws Exception {
        if(!levels.containsKey(target)) throw new IOException("Refresh individual levels first");
        attribute(target,Math.round(Math.max(0,Math.min(100,percent))*31f/100)); attribute(target,null); changed.run();
    }
    void hostVolume(int percent) throws Exception {
        LegacySession s=requireSession();
        s.set(steps==31?0x18d:0x190,(byte)Math.round(Math.max(0,Math.min(100,percent))*steps/100f));
        readVolume(s); changed.run();
    }
    private void readVolume(LegacySession s) throws Exception {
        byte[] p;
        try { p=s.query(0x18e,0x18f); steps=31; }
        catch(LegacySession.CommandError e) { if(e.status!=1) throw e; p=s.query(0x191,0x192); steps=15; }
        if(p.length!=1 || (p[0]&255)>steps) throw new IOException("Invalid volume reading");
        volume=Math.round((p[0]&255)*100f/steps);
    }
    void add(BluetoothDevice receiver) throws Exception { add(receiver.getAddress()); }
    void add(String target) throws Exception {
        Protocol.mac(target); // Reject invalid targets before sending any command.
        awaitGroupReady();
        LegacySession s=requireSession();
        if (!groupSupported) throw new IOException("PartyUp is unavailable on this host");
        if(target.equals(address) || members.containsKey(target)) throw new IOException("Speaker already in this group");
        // Joining is a host operation. A receiver may withhold its direct SPP
        // service; requiring that extra socket prevents an otherwise valid join.
        // Only the host's completion/inventory establishes actual membership.
        config(s);
        if(members.containsKey(target)) return;
        if ((broadcast&2)!=0 && audioMode!=0)
            throw new IOException("Select Double Up before adding another receiver");
        if ((broadcast&2)==0) { groupSet(s,0x413,(byte)3,(byte)0); config(s); }
        if ((broadcast&2)==0) throw new IOException("Host did not start broadcasting");
        byte[] payload=Arrays.copyOf(Protocol.mac(target),7); payload[6]=2;
        groupChange(s,0x417,0x418,target,payload);
        groupSettling();
    }
    void remove(String target) throws Exception { groupChange(requireSession(),0x419,0x41a,target,Protocol.mac(target)); }
    private void groupChange(LegacySession s,int command,int event,String target,byte[] payload) throws Exception {
        String key=event+":"+target; CompletableFuture<Void> completion=new CompletableFuture<>(); events.put(key,completion);
        try {
            groupSet(s,command,payload); completion.get(30,TimeUnit.SECONDS);
        } catch(TimeoutException e) {
            // No definitive completion: force a fresh control connection before another mutation.
            s.close(); throw new IOException("Group change unconfirmed. Reconnect and check the speakers before retrying.",e);
        } catch(ExecutionException e) { throw new IOException(e.getCause().getMessage(),e.getCause()); }
        finally { events.remove(key); changed.run(); }
    }
    void mode(boolean stereo) throws Exception {
        awaitGroupReady();
        LegacySession s=requireSession(); config(s);
        if ((broadcast&2)==0 || !inventoryKnown || members.size()!=1)
            throw new IOException("Mode selection needs exactly one confirmed receiver");
        int requested=stereo?0x50:0;
        // Rewriting the current mode needlessly reconfigures the live broadcast.
        if(audioMode==requested) return;
        groupSet(s,0x413,(byte)broadcast,(byte)requested); config(s);
        if(audioMode!=requested || (broadcast&2)==0) throw new IOException("Speaker did not confirm playback mode");
        changed.run();
    }
    void end() throws Exception {
        LegacySession s=requireSession(); groupSet(s,0x413,(byte)0,(byte)0); config(s);
        if(broadcast!=0) throw new IOException("Speaker did not confirm group ended"); changed.run();
    }
    void volume(int percent) throws Exception {
        awaitGroupReady();
        LegacySession s=requireSession(); int raw=Math.round(Math.max(0,Math.min(100,percent))*steps/100f);
        int previousBalance=balance;
        s.set(steps==31?0x18d:0x190,(byte)raw);
        if ((broadcast&2)!=0) {s.set(0x41b);levels.clear();}
        if((broadcast&2)!=0 && audioMode==0x50 && balanceSupported) s.set(0x19d,(byte)previousBalance);
        readVolume(s); changed.run();
    }
    boolean notification(Protocol.Message m) throws IOException {
        byte[] p=m.payload();
        if(m.command()==0x443) { disconnect(); return true; }
        if(m.command()==0x19c) { if(p.length!=1) return false; balance=p[0]; balanceSupported=true; changed.run(); return true; }
        if(m.command()==0x421 || m.command()==0x423) {
            if(p.length<9 || (p[8]!=0 && p[8]!=1)) return false;
            String target=Protocol.address(p,0); int attr=Protocol.u16(p,6);
            CompletableFuture<Integer> done=attributes.get(m.command()+":"+target);
            if(attr!=0x1e) return false;
            boolean valid=p[8]==0?p.length==9:m.command()==0x421?p.length==10 && (p[9]&255)<=31:p.length==9;
            if(!valid) {
                if(done!=null && !done.isDone()) done.completeExceptionally(new IOException("Invalid receiver level result"));
                return false;
            }
            if(unresolvedReceivers.contains(target))return true;
            // A valid duplicate/unsolicited result still needs its ACK. It must not
            // complete another receiver's pending operation or resurrect a member.
            if(done==null || done.isDone()) {
                if(m.command()==0x421 && p[8]==1 && members.containsKey(target)) {
                    levels.put(target,Math.round((p[9]&255)*100f/31)); changed.run();
                }
                return true;
            }
            if(!members.containsKey(target)) {
                done.completeExceptionally(new IOException("Receiver left the group")); return true;
            }
            if(p[8]==0) done.completeExceptionally(new LevelUnavailable("Individual volume unsupported"));
            else if(m.command()==0x421) {
                if(p.length!=10 || (p[9]&255)>31) done.completeExceptionally(new IOException("Invalid receiver level"));
                else { levels.put(target,Math.round((p[9]&255)*100f/31));levelProblems.remove(target); done.complete(p[9]&255); }
            } else done.complete(0);
            changed.run(); return true;
        }
        if(m.command()==0x416) {
            List<Protocol.Member> inventory=Protocol.members(p);
            levels.keySet().removeIf(a -> inventory.stream().noneMatch(mb -> mb.address().equals(a)));
            members.clear(); inventory.forEach(member -> members.put(member.address(),member)); inventoryKnown=true;
            for(Protocol.Member member:inventory) {
                CompletableFuture<Void> waiter=events.get(0x418+":"+member.address()); if(waiter!=null) waiter.complete(null);
            }
            changed.run(); return true;
        }
        if(m.command()==0x418 || m.command()==0x41a) {
            if(p.length!=7) return false;
            String target=Protocol.address(p,0); CompletableFuture<Void> waiter=events.get(m.command()+":"+target);
            // Only inventory records establish a complete inventory. Completion proves this member alone.
            if(p[6]==0) {
                if(m.command()==0x418) { if(members.putIfAbsent(target,new Protocol.Member(target,-1))==null)groupSettling(); } else { members.remove(target); levels.remove(target);levelProblems.remove(target); }
                if(waiter!=null) waiter.complete(null);
            } else if(waiter!=null) waiter.completeExceptionally(new IOException(switch(p[6]&255) {
                case 3 -> "Press the receiver's pairing button twice, then retry";
                case 4 -> "Turn on the receiver, then retry";
                default -> "Speaker could not complete group change (status "+(p[6]&255)+")";
            }));
            changed.run(); return true;
        }
        return false;
    }
    void disconnect() {
        LegacySession old=session; session=null; if(old!=null) old.close();
        BluetoothSocket socket=connecting; if(socket!=null) try { socket.close(); } catch(IOException ignored) {}
        members.clear(); levels.clear();unresolvedReceivers.clear();levelProblems.clear(); groupReadyAt=0; inventoryKnown=false; groupSupported=false; broadcast=0; volume=-1; battery=-1; model="";
        finishCode=-1; eq=-1; bands=null; customSupported=false; renameSupported=false; balanceSupported=false; firmware="";
        changed.run();
    }
    @Override public void close() { stopped=true; disconnect(); timer.shutdownNow(); }
}
