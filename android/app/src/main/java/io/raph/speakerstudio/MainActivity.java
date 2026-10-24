package io.raph.speakerstudio;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.*;
import android.bluetooth.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.provider.Settings;
import android.view.*;
import android.widget.*;
import java.util.*;
import java.util.concurrent.*;

@SuppressLint({"SetTextI18n", "MissingPermission"})
public final class MainActivity extends Activity {
    private static final int BG=0xff10171c, CARD=0xff1b262d, TEXT=0xffeff7f6, MUTED=0xffa4b8bd, CYAN=0xff70e5cf;
    private LinearLayout body, navigation;
    private ScrollView scroll;
    private String page="speakers";
    private boolean scrubbing, eqDirty;
    private byte[] eqDraft;
    private final Map<String,Integer> pendingLevels=new HashMap<>();
    private SpeakerController controller;
    private ExecutorService worker;
    private boolean active, busy, party=false;
    private String status="Pair your speakers in Android Bluetooth settings, then choose a host.";
    private final Map<String,String> names=new HashMap<>();
    interface Action { void run(SpeakerController c) throws Exception; }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG); getWindow().setNavigationBarColor(BG);
        getWindow().getDecorView().setSystemUiVisibility(0);
        if(state!=null) { page=state.getString("page","speakers"); party=page.equals("party"); }
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setBackgroundColor(BG);
        scroll=new ScrollView(this); scroll.setFillViewport(true); scroll.setClipToPadding(false);
        body=new LinearLayout(this); body.setOrientation(LinearLayout.VERTICAL); body.setPadding(dp(22),dp(18),dp(22),dp(24));
        scroll.addView(body); root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        navigation=new LinearLayout(this); navigation.setPadding(dp(14),dp(6),dp(14),dp(6)); navigation.setBackgroundColor(CARD);
        root.addView(navigation); setContentView(root);
        root.setOnApplyWindowInsetsListener((v,insets) -> {
            if (Build.VERSION.SDK_INT>=30) {
                android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                v.setPadding(bars.left,bars.top,bars.right,bars.bottom);
            } else v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());
            return insets;
        });
    }
    @Override protected void onStart() {
        super.onStart(); active=true; busy=false;
        scrubbing=false;eqDirty=false;eqDraft=null;pendingLevels.clear();
        controller=new SpeakerController(() -> runOnUiThread(() -> { if(active && !busy && !scrubbing) render(); }));
        worker=Executors.newSingleThreadExecutor(); render();
    }
    @Override protected void onStop() {
        active=false;
        controller.close(); worker.shutdownNow(); busy=false;
        status="Controls released. Reconnect to read your group; music can continue.";
        super.onStop();
    }
    @Override protected void onSaveInstanceState(Bundle state) { state.putString("page",page); super.onSaveInstanceState(state); }
    private int dp(int value) { return Math.round(value*getResources().getDisplayMetrics().density); }
    private GradientDrawable background(int color) {
        GradientDrawable d=new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(18)); return d;
    }
    private TextView text(LinearLayout parent,String value,int size,int color,boolean bold) {
        TextView t=new TextView(this); t.setText(value); t.setTextSize(size); t.setTextColor(color);
        if(bold) t.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        t.setPadding(0,dp(5),0,dp(7)); parent.addView(t); return t;
    }
    private LinearLayout card() {
        LinearLayout box=new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(dp(18),dp(14),dp(18),dp(14));
        box.setBackground(background(CARD)); LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2); lp.setMargins(0,dp(10),0,dp(6));
        body.addView(box,lp); return box;
    }
    private Button button(LinearLayout parent,String title,boolean enabled,Runnable action) {
        Button b=new Button(this); b.setText(title); b.setAllCaps(false); b.setTextColor(enabled?TEXT:MUTED);
        b.setTextSize(15); b.setMinHeight(dp(52)); b.setEnabled(enabled && !busy);
        b.setBackground(background(0xff293a43));
        LinearLayout.LayoutParams spacing=new LinearLayout.LayoutParams(-1,-2); spacing.setMargins(0,dp(5),0,dp(5)); b.setLayoutParams(spacing);
        parent.addView(b,spacing); b.setOnClickListener(v -> action.run()); return b;
    }
    private boolean permitted() { return Build.VERSION.SDK_INT<31 || checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED; }
    private BluetoothAdapter adapter() {
        BluetoothManager manager=getSystemService(BluetoothManager.class); return manager==null?null:manager.getAdapter();
    }
    private void render() {
        if(!active) return;
        int position=scroll.getScrollY();
        body.removeAllViews(); navigation.removeAllViews(); boolean connected=controller.connected();
        if(!connected) { eqDirty=false;eqDraft=null;pendingLevels.clear(); }
        text(body,"SPEAKER STUDIO",12,CYAN,true).setLetterSpacing(.18f);
        text(body,page.equals("sound")?"Make it your sound.":party?"Better together.":"Your listening space.",29,TEXT,true);
        text(body,party?"Play through your speakers together.":page.equals("sound")?"Fine-tune every track, your way.":"A little more control. A lot more music.",14,MUTED,false);
        String[] labels={"Speakers","Sound","PartyUp"}, pages={"speakers","sound","party"};
        for(int i=0;i<labels.length;i++) {
            final String target=pages[i]; boolean selected=page.equals(target);
            Button tab=new Button(this); tab.setText(labels[i]); tab.setAllCaps(false); tab.setTextSize(14);
            tab.setTextColor(selected?BG:MUTED); tab.setBackground(background(selected?CYAN:CARD));
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,dp(52),1); lp.setMargins(dp(3),0,dp(3),0); navigation.addView(tab,lp);
            tab.setOnClickListener(v->{page=target;party=page.equals("party");render();scroll.scrollTo(0,0);});
        }
        LinearLayout info=card(); text(info,busy?"Working…":connected?"●  Connected to "+controller.name:"○  Ready to connect",15,connected?CYAN:TEXT,true);
        TextView message=text(info,status,13,MUTED,false); message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        if(!permitted()) primary(info,"Allow nearby devices",()->requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT},1));
        if(!connected) {
            body.addView(new SpeakerArtwork(this,party),new LinearLayout.LayoutParams(-1,dp(220)));
            text(body,"Good sound starts here.",24,TEXT,true);
            text(body,"Turn on your speakers, pair them in Bluetooth settings, then choose the one playing your phone’s music.",16,MUTED,false);
            primary(body,"Choose a speaker",()->choose(false));
            button(body,"Open Bluetooth settings",true,()->startActivity(new Intent(Settings.ACTION_BLUETOOTH_SETTINGS)));
            if(page.equals("sound")) text(body,"Connect to unlock sound profiles and the five-band equalizer.",14,MUTED,false);
            if(party) text(body,"Connect a host, then add your paired speakers to PartyUp. The host shares its music with the group.",14,MUTED,false);
        } else if(page.equals("sound")) renderSound();
        else if(party) renderParty();
        else renderSpeaker();
        text(body,"Independent app for Ultimate Ears speakers",11,MUTED,false);
        scroll.post(()->scroll.scrollTo(0,Math.min(position,Math.max(0,body.getHeight()-scroll.getHeight()))));
    }
    private void primary(LinearLayout parent,String title,Runnable action) {
        Button b=button(parent,title,true,action); b.setTextColor(BG); b.setTypeface(Typeface.DEFAULT,Typeface.BOLD); b.setBackground(background(CYAN));
    }
    private void slider(LinearLayout parent,String title,int value,int max,boolean enabled,java.util.function.IntConsumer action) {
        int shown=pendingLevels.getOrDefault(title,value);
        TextView label=text(parent,title+"  ·  "+shown,14,TEXT,true);
        SeekBar bar=new SeekBar(this); bar.setMax(max); bar.setProgress(Math.max(0,shown)); bar.setEnabled(enabled && !busy);
        bar.setProgressTintList(android.content.res.ColorStateList.valueOf(CYAN)); bar.setThumbTintList(android.content.res.ColorStateList.valueOf(CYAN));
        bar.setContentDescription(title); parent.addView(bar,new LinearLayout.LayoutParams(-1,dp(52)));
        bar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar s,int p,boolean user) { label.setText(title+"  ·  "+p); }
            public void onStartTrackingTouch(SeekBar s) { scrubbing=true; }
            public void onStopTrackingTouch(SeekBar s) { scrubbing=false;pendingLevels.put(title,s.getProgress());action.accept(s.getProgress()); }
        });
    }
    private void renderSpeaker() {
        body.addView(new SpeakerArtwork(this,false),new LinearLayout.LayoutParams(-1,dp(210)));
        TextView name=text(body,controller.name,28,TEXT,true); name.setGravity(Gravity.CENTER);
        TextView details=text(body,controller.model+"   ·   "+(controller.battery<0?"Battery unavailable":controller.battery+"% battery"),14,CYAN,false); details.setGravity(Gravity.CENTER);
        LinearLayout volume=card(); text(volume,"Listening level",19,TEXT,true);
        if(controller.volume>=0) slider(volume,(controller.broadcast&2)!=0?"Group volume (%)":"Volume (%)",controller.volume,100,true,p->run("Volume confirmed",c->c.volume(p)));
        button(volume,"Refresh readings",true,()->run("Readings refreshed",SpeakerController::refresh));
        LinearLayout settings=card(); text(settings,"Speaker settings",20,TEXT,true);
        button(settings,"Rename speaker",controller.renameSupported,()->input("Rename speaker",controller.name,value->run("Speaker renamed",c->c.rename(value))));
        button(settings,"Find my speaker · play battery prompt",true,()->run("Speaker is announcing its battery level",SpeakerController::identify));
        button(settings,"Firmware · "+(controller.firmware.isEmpty()?"unavailable":controller.firmware),true,this::firmware);
        button(settings,"Change speaker",true,()->choose(false));
        button(settings,"Bluetooth settings / audio output",true,()->startActivity(new Intent(Settings.ACTION_BLUETOOTH_SETTINGS)));
        button(settings,"Release controls for listening",true,()->run("Controls released. Music can keep playing.",SpeakerController::disconnect));
        button(settings,"Turn off speaker",true,()->new AlertDialog.Builder(this).setTitle("Turn off "+controller.name+"?").setMessage("Music will stop on this speaker.")
            .setNegativeButton("Keep listening",null).setPositiveButton("Turn off",(d,w)->run("Speaker turned off",SpeakerController::powerOff)).show());
    }
    private void firmware() {
        new AlertDialog.Builder(this).setTitle("Speaker firmware")
            .setMessage("Installed version: "+(controller.firmware.isEmpty()?"unavailable":controller.firmware)+"\n\nUse the official UE | BOOM app to check for updates and install them. Finish listening and end PartyUp first. Release Speaker Studio controls before opening the updater.")
            .setPositiveButton("Done",null).setNeutralButton("Release controls",(d,w)->run("Controls released for the official updater",SpeakerController::disconnect)).show();
    }
    private void input(String title,String initial,java.util.function.Consumer<String> accept) {
        EditText entry=new EditText(this); entry.setText(initial); entry.setSingleLine(true); entry.setPadding(dp(24),dp(16),dp(24),dp(16)); entry.setSelectAllOnFocus(true);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(title).setView(entry).setNegativeButton("Cancel",null).setPositiveButton("Save",null).create();
        dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            String value=entry.getText().toString().trim(); if(value.isEmpty()) { entry.setError("Enter a name"); return; }
            accept.accept(value); dialog.dismiss();
        })); dialog.show();
    }
    private void renderSound() {
        LinearLayout presets=card(); text(presets,"Sound profiles",21,TEXT,true);
        text(presets,"Stored on your speaker, wherever you listen.",14,MUTED,false);
        String[] labels={"Out loud","Vocal","Intimate","Bass boost"};
        for(int i=0;i<labels.length;i++) { final int code=i;
            button(presets,(controller.eq==i?"✓  ":"")+labels[i],controller.eq>=0,()->run("Sound profile confirmed",c->{c.preset(code);runOnUiThread(()->eqDirty=false);}));
        }
        LinearLayout custom=card(); text(custom,"Your equalizer",21,TEXT,true);
        text(custom,"Five bands · bass to treble",14,MUTED,false);
        if(!controller.customSupported) { text(custom,"Custom EQ is unavailable on this speaker.",14,MUTED,false); return; }
        if(!eqDirty || eqDraft==null) eqDraft=Arrays.copyOf(controller.bands,5);
        byte[] draft=eqDraft;
        String[] frequencies={"60 Hz","300 Hz","1 kHz","3 kHz","12 kHz"};
        text(custom,"Adjust the stored custom curve. Built-in profiles remain unchanged.",13,MUTED,false);
        for(int i=0;i<5;i++) {
            final int index=i;
            TextView label=text(custom,frequencies[i]+"  ·  "+String.format(java.util.Locale.ROOT,"%+.1f dB",draft[i]*12f/127),14,TEXT,true);
            SeekBar bar=new SeekBar(this); bar.setMax(255); bar.setProgress(draft[i]+128); bar.setEnabled(!busy); bar.setContentDescription(frequencies[i]);
            custom.addView(bar,new LinearLayout.LayoutParams(-1,dp(48)));
            bar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
                public void onProgressChanged(SeekBar s,int p,boolean user) { draft[index]=(byte)(p-128); if(user) eqDirty=true;label.setText(frequencies[index]+"  ·  "+String.format(java.util.Locale.ROOT,"%+.1f dB",draft[index]*12f/127)); }
                public void onStartTrackingTouch(SeekBar s) { scrubbing=true; } public void onStopTrackingTouch(SeekBar s) { scrubbing=false; }
            });
        }
        primary(custom,"Apply custom sound",()->run("Custom EQ confirmed",c->{c.custom(draft.clone());runOnUiThread(()->eqDirty=false);}));
        button(custom,"Save as a new profile",true,()->input("Name this sound profile","",name->{
            String key="profile:"+name.toLowerCase(java.util.Locale.ROOT);
            boolean reserved=Arrays.stream(labels).anyMatch(label->label.equalsIgnoreCase(name)) || name.equalsIgnoreCase("custom");
            if(name.length()>64 || name.contains("|") || name.codePoints().anyMatch(c->c<32 || c==127) || reserved || getPreferences(0).contains(key)) { status="Choose a new name, up to 64 characters. Existing profiles are kept."; render(); return; }
            getPreferences(0).edit().putString(key,name+"|"+android.util.Base64.encodeToString(draft,android.util.Base64.NO_WRAP)).apply(); status="Sound profile saved"; render();
        }));
        java.util.Map<String,?> saved=new java.util.TreeMap<>(getPreferences(0).getAll());
        for(String key:saved.keySet()) if(key.startsWith("profile:")) {
            String[] value=saved.get(key).toString().split("\\|",2);
            if(value.length!=2) continue;
            button(custom,value[0],true,()->{
                try { byte[] curve=android.util.Base64.decode(value[1],android.util.Base64.NO_WRAP); run("Saved profile confirmed",c->c.custom(curve)); }
                catch(IllegalArgumentException error) { status="Saved profile could not be read"; render(); }
            });
        }
    }
    private void renderParty() {
        body.addView(new SpeakerArtwork(this,true),new LinearLayout.LayoutParams(-1,dp(185)));
        List<Protocol.Member> members=controller.members(); boolean broadcasting=(controller.broadcast&2)!=0;
        LinearLayout group=card(); text(group,"Your group",22,TEXT,true);
        text(group,controller.name+" · Host",17,TEXT,true);
        text(group,broadcasting?members.size()+" confirmed receiver"+(members.size()==1?"":"s"):"Add a speaker to fill the room.",14,CYAN,false);
        if(broadcasting && !controller.inventoryKnown) text(group,"Waiting for the full group report. Reconnect to inspect the group if it does not arrive.",13,MUTED,false);
        if(broadcasting && controller.volume>=0) slider(group,"Group volume (%)",controller.volume,100,true,p->run("Group volume confirmed",c->c.volume(p)));
        if(broadcasting) {
            button(group,"Refresh individual levels",true,()->run("Individual levels refreshed",SpeakerController::groupLevels));
            if(controller.volume>=0) slider(group,controller.name+" (%)",controller.volume,100,true,p->run("Host level confirmed",c->c.hostVolume(p)));
        }
        for(Protocol.Member member:members) {
            String name=names.getOrDefault(member.address(),"Receiver "+member.address().substring(12));
            text(group,name,18,TEXT,true); text(group,member.battery()<0?"Receiver · battery unavailable":member.battery()+"% battery",13,MUTED,false);
            Integer level=controller.memberLevel(member.address());
            if(level!=null) slider(group,name+" (%)",level,100,true,p->run("Receiver level confirmed",c->c.memberVolume(member.address(),p)));
            else text(group,"Refresh levels to check individual volume support.",12,MUTED,false);
            button(group,"Remove "+name,true,()->run("Receiver removed",c->c.remove(member.address())));
        }
        primary(group,"+ Add a speaker",()->{if(controller.groupSupported)choose(true);else{status="PartyUp unavailable on this speaker";render();}});
        boolean pair=broadcasting && controller.inventoryKnown && members.size()==1;
        LinearLayout mode=card(); text(mode,"How you listen",20,TEXT,true);
        button(mode,(controller.audioMode==0 && broadcasting?"✓  ":"")+"Double Up · full sound",pair,()->run("Double Up confirmed",c->c.mode(false)));
        button(mode,(controller.audioMode==0x50 && broadcasting?"✓  ":"")+"Stereo · left and right",pair,()->run("Stereo confirmed",c->{c.mode(true);c.refresh();}));
        text(mode,"Stereo needs two speakers and a complete group report. Double Up shares the full sound.",13,MUTED,false);
        if(pair && controller.audioMode==0x50 && controller.balanceSupported) {
            slider(mode,"Balance · left to right",controller.balance+128,255,true,p->run("Balance confirmed",c->c.balance(p-128)));
            button(mode,"Centre balance",true,()->run("Balance centred",c->c.balance(0)));
        }
        button(mode,"Refresh group readings",true,()->run("Group readings refreshed",SpeakerController::refresh));
        button(mode,"End group",broadcasting,()->new AlertDialog.Builder(this).setTitle("End this PartyUp group?")
            .setMessage("Receivers will stop playing the host’s music.").setNegativeButton("Keep playing",null)
            .setPositiveButton("End group",(d,w)->run("Group ended",SpeakerController::end)).show());
        text(body,"Phone audio uses native PartyUp. Computer Mix requires Linux PipeWire and is only available in the desktop app.",12,MUTED,false);
    }
    private void choose(boolean receiver) {
        if(!permitted()) { requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT},1); return; }
        try {
            BluetoothAdapter bt=adapter();
            if(bt==null) { status="This device has no Bluetooth adapter."; render(); return; }
            if(!bt.isEnabled()) { startActivity(new Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE)); return; }
            List<BluetoothDevice> devices=new ArrayList<>(bt.getBondedDevices());
            devices.removeIf(d->receiver && (d.getAddress().equals(controller.address) || controller.members().stream().anyMatch(m->m.address().equals(d.getAddress()))));
            devices.sort(Comparator.comparing(d->d.getName()==null?d.getAddress():d.getName()));
            String[] labels=new String[devices.size()];
            for(int i=0;i<devices.size();i++) {
                BluetoothDevice d=devices.get(i); String name=d.getName()==null?"Unnamed device":d.getName();
                names.put(d.getAddress(),name); labels[i]=name+"\n"+d.getAddress();
            }
            if(devices.isEmpty()) { status="No paired "+(receiver?"receivers":"devices")+". Pair speakers in Bluetooth settings first."; render(); return; }
            new AlertDialog.Builder(this).setTitle(receiver?"Add receiver · choose a speaker":"Choose your music's host speaker")
                .setItems(labels,(dialog,index)-> {
                    BluetoothDevice d=devices.get(index);
                    run(receiver?"Receiver join confirmed":"Host connected. Select it as Android's media output.",c->{if(receiver)c.add(d);else { c.connect(d);runOnUiThread(()->eqDirty=false); }});
                }).setNegativeButton("Cancel",null).show();
        } catch(SecurityException error) { status="Nearby devices permission is required. Enable it in Android app settings."; render(); }
    }
    private void run(String success,Action action) {
        if(busy || !active) return;
        SpeakerController current=controller; busy=true; status="Waiting for speaker confirmation…"; render();
        worker.execute(()-> {
            String result=success;
            try { action.run(current); }
            catch(Exception error) { result=error.getMessage()==null?"Bluetooth operation failed. Reconnect and retry.":error.getMessage(); }
            String message=result;
            runOnUiThread(()-> { if(active && controller==current) { busy=false;pendingLevels.clear(); status=message; render(); } });
        });
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results) {
        super.onRequestPermissionsResult(request,permissions,results);
        status=permitted()?"Choose a paired host speaker.":"Nearby devices permission was denied. Allow it in Android app settings to connect.";
        render();
    }
}
