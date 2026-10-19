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
    private final ScheduledExecutorService timer = Executors.newSingleThreadScheduledExecutor();
    private final Map<String, CompletableFuture<Void>> events = new ConcurrentHashMap<>();
    private final Map<String, Protocol.Member> members = new ConcurrentHashMap<>();
    private volatile LegacySession session;
    private volatile BluetoothSocket connecting;
    private volatile boolean stopped;
    volatile String name="", model="", address="";
    volatile int broadcast=0, audioMode=0, battery=-1, volume=-1, steps=31;
    volatile boolean inventoryKnown=false, groupSupported=false;
    SpeakerController(Runnable changed) { this.changed=changed; }
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
            model=Protocol.model(session.query(6,7)); refresh();
        }
        catch(Exception error) { disconnect(); throw error; }
    }
    private LegacySession requireSession() throws IOException {
        if (!connected()) throw new IOException("Connect a host speaker first"); return session;
    }
    private byte[] config(LegacySession s) throws Exception {
        byte[] p=null;
        for (int i=0; i<8; i++) {
            try { p=s.query(0x414,0x415); break; }
            catch (LegacySession.CommandError e) { if (e.status!=9 || i==7) throw e; Thread.sleep(350); }
        }
        if (p==null || p.length!=2 || (p[0]&255)>3) throw new IOException("Invalid group configuration");
        broadcast=p[0]&255; audioMode=p[1]&255;
        if ((broadcast&2)==0) { members.clear(); inventoryKnown=false; }
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
        readVolume(s); changed.run();
    }
    private void readVolume(LegacySession s) throws Exception {
        byte[] p;
        try { p=s.query(0x18e,0x18f); steps=31; }
        catch(LegacySession.CommandError e) { if(e.status!=1) throw e; p=s.query(0x191,0x192); steps=15; }
        if(p.length!=1 || (p[0]&255)>steps) throw new IOException("Invalid volume reading");
        volume=Math.round((p[0]&255)*100f/steps);
    }
    void add(BluetoothDevice receiver) throws Exception {
        LegacySession s=requireSession();
        if (!groupSupported) throw new IOException("PartyUp is unavailable on this host");
        String target=receiver.getAddress();
        if(target.equals(address) || members.containsKey(target)) throw new IOException("Speaker already in this group");
        // Validate actual hardware identity and capability; names and artwork are not evidence.
        try (LegacySession probe=open(receiver,false)) {
            Protocol.model(probe.query(6,7)); byte[] p=probe.query(0x414,0x415);
            if(p.length!=2 || (p[0]&255)>3) throw new IOException("Invalid receiver configuration");
            if((p[0]&2)!=0) throw new IOException("End the receiver's existing group first");
        }
        config(s);
        if ((broadcast&2)!=0 && audioMode!=0)
            throw new IOException("Select Double Up before adding another receiver");
        if ((broadcast&2)==0) { s.set(0x413,(byte)3,(byte)0); config(s); }
        if ((broadcast&2)==0) throw new IOException("Host did not start broadcasting");
        byte[] payload=Arrays.copyOf(Protocol.mac(target),7); payload[6]=2;
        groupChange(s,0x417,0x418,target,payload);
    }
    void remove(String target) throws Exception { groupChange(requireSession(),0x419,0x41a,target,Protocol.mac(target)); }
    private void groupChange(LegacySession s,int command,int event,String target,byte[] payload) throws Exception {
        String key=event+":"+target; CompletableFuture<Void> completion=new CompletableFuture<>(); events.put(key,completion);
        try {
            s.set(command,payload); completion.get(30,TimeUnit.SECONDS);
        } catch(TimeoutException e) {
            // No definitive completion: force a fresh control connection before another mutation.
            s.close(); throw new IOException("Group change unconfirmed. Reconnect and check the speakers before retrying.",e);
        } catch(ExecutionException e) { throw new IOException(e.getCause().getMessage(),e.getCause()); }
        finally { events.remove(key); changed.run(); }
    }
    void mode(boolean stereo) throws Exception {
        LegacySession s=requireSession(); config(s);
        if ((broadcast&2)==0 || !inventoryKnown || members.size()!=1)
            throw new IOException("Mode selection needs exactly one confirmed receiver");
        int requested=stereo?0x50:0;
        s.set(0x413,(byte)broadcast,(byte)requested); config(s);
        if(audioMode!=requested || (broadcast&2)==0) throw new IOException("Speaker did not confirm playback mode");
        changed.run();
    }
    void end() throws Exception {
        LegacySession s=requireSession(); s.set(0x413,(byte)0,(byte)0); config(s);
        if(broadcast!=0) throw new IOException("Speaker did not confirm group ended"); changed.run();
    }
    void volume(int percent) throws Exception {
        LegacySession s=requireSession(); int raw=Math.round(Math.max(0,Math.min(100,percent))*steps/100f);
        s.set(steps==31?0x18d:0x190,(byte)raw);
        if ((broadcast&2)!=0) s.set(0x41b);
        readVolume(s); changed.run();
    }
    boolean notification(Protocol.Message m) throws IOException {
        byte[] p=m.payload();
        if(m.command()==0x19c) return p.length==1;
        if(m.command()==0x416) {
            List<Protocol.Member> inventory=Protocol.members(p);
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
                if(m.command()==0x418) members.putIfAbsent(target,new Protocol.Member(target,-1)); else members.remove(target);
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
        members.clear(); inventoryKnown=false; groupSupported=false; broadcast=0; volume=-1; battery=-1; model="";
        changed.run();
    }
    @Override public void close() { stopped=true; disconnect(); timer.shutdownNow(); }
}
