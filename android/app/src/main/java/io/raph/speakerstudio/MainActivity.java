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
    private static final int BG=0xff101214, CARD=0xff1c2024, TEXT=0xfff4f5f0, MUTED=0xffa9afb4, ACCENT=0xffd5f578;
    private LinearLayout body, navigation;
    private ScrollView scroll;
    private String page="speakers";
    private boolean scrubbing, eqDirty;
    private byte[] eqDraft;
    private final Map<String,Integer> pendingLevels=new HashMap<>();
    private SpeakerController controller;
    private ExecutorService worker;
    private boolean active, busy, party=false;
    private String status="";
    private final Map<String,String> names=new HashMap<>();
    interface Action { void run(SpeakerController c) throws Exception; }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG); getWindow().setNavigationBarColor(BG);
        getWindow().getDecorView().setSystemUiVisibility(0);
        if(state!=null) { page=state.getString("page","speakers"); party=page.equals("party"); }
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setBackgroundColor(BG);
        scroll=new ScrollView(this); scroll.setTag("content-scroll"); scroll.setFillViewport(true); scroll.setClipToPadding(false);
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
        status="Controls released";
        super.onStop();
    }
    @Override protected void onSaveInstanceState(Bundle state) { state.putString("page",page); super.onSaveInstanceState(state); }
    private int dp(int value) { return Math.round(value*getResources().getDisplayMetrics().density); }
    private GradientDrawable background(int color) {
        GradientDrawable d=new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(24)); return d;
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
        b.setBackground(background(0xff2a3035));
        b.setAlpha(enabled && !busy?1f:.45f);
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
        else rememberSpeakers();
        LinearLayout heading=new LinearLayout(this); heading.setGravity(Gravity.CENTER_VERTICAL); body.addView(heading);
        TextView brand=text(heading,"SPEAKER / STUDIO",12,ACCENT,true); brand.setLetterSpacing(.12f);
        brand.setLayoutParams(new LinearLayout.LayoutParams(0,-2,1));
        Button more=button(heading,"•••",true,this::settings); more.setContentDescription("Speaker settings and help");
        more.setLayoutParams(new LinearLayout.LayoutParams(dp(56),dp(48)));
        text(body,page.equals("sound")?"Sound":party?"Mix":"Speakers",32,TEXT,true);
        String[] labels={"Speakers","Mix","Sound"}, pages={"speakers","party","sound"};
        for(int i=0;i<labels.length;i++) {
            final String target=pages[i]; boolean selected=page.equals(target);
            Button tab=new Button(this); tab.setText(labels[i]); tab.setAllCaps(false); tab.setTextSize(14);
            tab.setContentDescription(labels[i]+(selected?", selected":"")); tab.setSelected(selected);
            tab.setTextColor(selected?BG:MUTED); tab.setBackground(background(selected?ACCENT:CARD));
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,dp(52),1); lp.setMargins(dp(3),0,dp(3),0); navigation.addView(tab,lp);
            tab.setOnClickListener(v->{page=target;party=page.equals("party");render();scroll.post(()->scroll.scrollTo(0,0));});
        }
        if(busy || !status.isEmpty()) {
            TextView message=text(body,busy?"Connecting / updating…":status,13,MUTED,false);
            message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        }
        if(!connected) renderConnect();
        else if(page.equals("sound")) renderSound();
        else if(party) renderParty();
        else renderSpeaker();
        scroll.post(()->scroll.scrollTo(0,Math.min(position,Math.max(0,body.getHeight()-scroll.getHeight()))));
    }
    private void renderConnect() {
        body.addView(new SpeakerArtwork(this,true),new LinearLayout.LayoutParams(-1,dp(185)));
        text(body,"Ready when you are.",25,TEXT,true);
        text(body,"Choose a powered-on, paired speaker.",14,MUTED,false);
        LinearLayout paired=card(); text(paired,"Your speakers",19,TEXT,true);
        if(!permitted()) {
            primary(paired,"Allow nearby devices",()->requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT},1));
        } else {
            BluetoothAdapter bt=adapter();
            if(bt==null) text(paired,"Bluetooth is unavailable on this device.",14,MUTED,false);
            else if(!bt.isEnabled()) primary(paired,"Turn on Bluetooth",()->startActivity(new Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE)));
            else {
                List<BluetoothDevice> devices=pairedDevices();
                devices.removeIf(device->!knownSpeaker(device));
                if(devices.isEmpty()) text(paired,"No saved UE speakers yet",14,MUTED,false);
                for(BluetoothDevice device:devices) {
                    String name=deviceName(device);
                    if(devices.stream().filter(other->deviceName(other).equals(deviceName(device))).count()>1) name+=" · "+device.getAddress().substring(12);
                    button(paired,name+"   →",true,()->connect(device,false));
                }
            }
        }
        button(paired,"Add paired speaker",true,()->choose(false,true));
        button(paired,"+ Pair a new speaker",true,this::bluetoothSettings);
    }
    private void bluetoothSettings() { startActivity(new Intent(Settings.ACTION_BLUETOOTH_SETTINGS)); }
    private List<BluetoothDevice> pairedDevices() {
        BluetoothAdapter bt=adapter();
        List<BluetoothDevice> devices=bt==null?new ArrayList<>():new ArrayList<>(bt.getBondedDevices());
        devices.sort(Comparator.comparing(this::deviceName));
        for(BluetoothDevice device:devices) names.put(device.getAddress(),deviceName(device));
        return devices;
    }
    private boolean knownSpeaker(BluetoothDevice device) {
        return SpeakerDirectory.visible(device.getName(),getPreferences(0).contains("speaker:"+device.getAddress()));
    }
    private void rememberSpeakers() {
        if(controller.model.isEmpty()) return;
        android.content.SharedPreferences preferences=getPreferences(0);
        android.content.SharedPreferences.Editor editor=preferences.edit();
        String host="speaker:"+controller.address;
        boolean updated=!preferences.contains(host);
        if(updated)editor.putString(host,controller.model);
        for(Protocol.Member member:controller.members()) {
            String key="speaker:"+member.address();
            if(!preferences.contains(key)) {editor.putString(key,"PartyUp receiver");updated=true;}
        }
        if(updated)editor.apply();
    }
    private String deviceName(BluetoothDevice device) { return device.getName()==null?"Unnamed device":device.getName(); }
    private void connect(BluetoothDevice device,boolean receiver) {
        run(receiver?"Speaker added":"Connected",c->{
            if(receiver)c.add(device);else { c.connect(device);runOnUiThread(()->eqDirty=false); }
        });
    }
    private void settings() {
        boolean connected=controller.connected();
        String[] items=connected?new String[]{"Rename speaker","Find speaker","Refresh readings","Firmware","Change speaker","Bluetooth / audio output","Release controls","Turn off speaker","Phone mix & wake"}
            :new String[]{"Bluetooth settings","Phone mix & wake"};
        new AlertDialog.Builder(this).setTitle(connected?controller.name:"Speaker Studio").setItems(items,(dialog,index)->{
            if(!connected) { if(index==0)bluetoothSettings();else platformInfo();return; }
            switch(index) {
                case 0: if(controller.renameSupported)input("Rename speaker",controller.name,value->run("Speaker renamed",c->c.rename(value)));
                    else {status="Renaming unavailable on this speaker";render();} break;
                case 1: run("Playing battery prompt",SpeakerController::identify);break;
                case 2: run("Readings refreshed",SpeakerController::refresh);break;
                case 3: firmware();break;
                case 4: choose(false);break;
                case 5: bluetoothSettings();break;
                case 6: run("Controls released",SpeakerController::disconnect);break;
                case 7: new AlertDialog.Builder(this).setTitle("Turn off "+controller.name+"?")
                    .setNegativeButton("Cancel",null).setPositiveButton("Turn off",(d,w)->run("Speaker turned off",SpeakerController::powerOff)).show();break;
                default: platformInfo();
            }
        }).show();
    }
    private void platformInfo() {
        new AlertDialog.Builder(this).setTitle("Phone mix & wake")
            .setMessage("Group playback uses PartyUp. Separate streams to multiple speakers aren’t available in this Android build.\n\nRemote wake isn’t available yet. Turn on your speaker with its power button.")
            .setPositiveButton("Done",null).show();
    }
    private void primary(LinearLayout parent,String title,Runnable action) {
        Button b=button(parent,title,true,action); b.setTextColor(BG); b.setTypeface(Typeface.DEFAULT,Typeface.BOLD); b.setBackground(background(ACCENT));
    }
    private String levelLabel(String title,int value,int max) {
        if(max==255) {
            int delta=value-128;
            String balance=delta==0?"Centre":(delta<0?"L ":"R ")+Math.round(Math.abs(delta)*100f/(delta<0?128:127))+"%";
            return title+"  ·  "+balance;
        }
        return title.replace(" (%)","")+"  ·  "+value+(max==100?"%":"");
    }
    private void slider(LinearLayout parent,String title,int value,int max,boolean enabled,java.util.function.IntConsumer action) {
        int shown=pendingLevels.getOrDefault(title,value);
        TextView label=text(parent,levelLabel(title,shown,max),14,TEXT,true);
        SeekBar bar=new SeekBar(this); bar.setMax(max); bar.setProgress(Math.max(0,shown)); bar.setEnabled(enabled && !busy);
        bar.setProgressTintList(android.content.res.ColorStateList.valueOf(ACCENT)); bar.setThumbTintList(android.content.res.ColorStateList.valueOf(ACCENT));
        bar.setContentDescription(title); parent.addView(bar,new LinearLayout.LayoutParams(-1,dp(52)));
        bar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar s,int p,boolean user) { label.setText(levelLabel(title,p,max)); }
            public void onStartTrackingTouch(SeekBar s) { scrubbing=true; }
            public void onStopTrackingTouch(SeekBar s) { scrubbing=false;pendingLevels.put(title,s.getProgress());action.accept(s.getProgress()); }
        });
    }
    private void renderSpeaker() {
        LinearLayout hero=card();
        text(hero,"●  CONNECTED",11,ACCENT,true).setLetterSpacing(.12f);
        hero.addView(new SpeakerArtwork(this,false),new LinearLayout.LayoutParams(-1,dp(170)));
        TextView name=text(hero,controller.name,27,TEXT,true); name.setGravity(Gravity.CENTER);
        TextView details=text(hero,controller.model+"   ·   "+(controller.battery<0?"Battery —":controller.battery+"% battery"),14,MUTED,false); details.setGravity(Gravity.CENTER);
        LinearLayout volume=card(); text(volume,"Volume",20,TEXT,true);
        if(controller.volume>=0) slider(volume,(controller.broadcast&2)!=0?"Group (%)":"Speaker (%)",controller.volume,100,true,p->run("Volume set",c->c.volume(p)));
        else text(volume,"Volume unavailable",14,MUTED,false);
        LinearLayout quick=new LinearLayout(this); quick.setGravity(Gravity.CENTER_VERTICAL); volume.addView(quick);
        Button find=button(quick,"Find speaker",true,()->run("Playing battery prompt",SpeakerController::identify));
        LinearLayout.LayoutParams left=new LinearLayout.LayoutParams(0,dp(52),1);left.setMargins(0,dp(4),dp(5),0);find.setLayoutParams(left);
        Button output=button(quick,"Audio output",true,this::bluetoothSettings);
        LinearLayout.LayoutParams right=new LinearLayout.LayoutParams(0,dp(52),1);right.setMargins(dp(5),dp(4),0,0);output.setLayoutParams(right);
        primary(body,"Mix speakers   →",()->{page="party";party=true;render();scroll.post(()->scroll.scrollTo(0,0));});
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

        String[] labels={"Out loud","Vocal","Intimate","Bass boost"};
        for(int row=0;row<2;row++) {
            LinearLayout options=new LinearLayout(this); presets.addView(options);
            for(int col=0;col<2;col++) {
                final int code=row*2+col;
                Button option=button(options,(controller.eq==code?"✓  ":"")+labels[code],controller.eq>=0,
                    ()->run("Sound profile set",c->{c.preset(code);runOnUiThread(()->eqDirty=false);}));
                LinearLayout.LayoutParams tile=new LinearLayout.LayoutParams(0,-2,1);tile.setMargins(dp(col==0?0:4),dp(4),dp(col==0?4:0),dp(4));option.setLayoutParams(tile);
                if(controller.eq==code) {option.setBackground(background(ACCENT));option.setTextColor(BG);}
            }
        }
        LinearLayout custom=card(); text(custom,"Custom EQ",21,TEXT,true);
        text(custom,"Five bands · bass to treble",14,MUTED,false);
        if(!controller.customSupported) { text(custom,"Custom EQ is unavailable on this speaker.",14,MUTED,false); return; }
        if(!eqDirty || eqDraft==null) eqDraft=Arrays.copyOf(controller.bands,5);
        byte[] draft=eqDraft;
        String[] frequencies={"60 Hz","300 Hz","1 kHz","3 kHz","12 kHz"};

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
        primary(custom,"Apply EQ",()->run("Custom EQ confirmed",c->{c.custom(draft.clone());runOnUiThread(()->eqDirty=false);}));
        button(custom,"Save profile",true,()->input("Name this sound profile","",name->{
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
        List<Protocol.Member> members=controller.members(); boolean broadcasting=(controller.broadcast&2)!=0;
        LinearLayout source=card(); text(source,"PHONE AUDIO",11,ACCENT,true).setLetterSpacing(.12f);
        text(source,"Phone  →  "+controller.name,20,TEXT,true);
        text(source,"Select your speaker in Android audio output.",13,MUTED,false);
        text(source,broadcasting?"PartyUp · group active":"Single speaker · add more below",13,MUTED,false);
        button(source,"Audio output  ↗",true,this::bluetoothSettings);
        Button add=button(body,"+ Add speaker",controller.groupSupported,()->choose(true));
        add.setTextColor(BG);add.setBackground(background(ACCENT));
        if(!controller.groupSupported) text(body,"PartyUp unavailable on this speaker",13,MUTED,false);
        LinearLayout group=card(); text(group,"Speakers",22,TEXT,true);
        text(group,controller.name+"  ·  Host",16,TEXT,true);
        if(broadcasting && !controller.inventoryKnown) text(group,"Waiting for group report…",13,MUTED,false);
        if(controller.volume>=0) slider(group,broadcasting?"Group (%)":"Volume (%)",controller.volume,100,true,p->run("Volume set",c->c.volume(p)));
        if(broadcasting) {
            button(group,"Refresh speaker levels",true,()->run("Levels refreshed",SpeakerController::groupLevels));
            if(controller.volume>=0) slider(group,controller.name+" (%)",controller.volume,100,true,p->run("Host level set",c->c.hostVolume(p)));
        }
        for(Protocol.Member member:members) {
            String name=names.getOrDefault(member.address(),"Speaker "+member.address().substring(12));
            LinearLayout receiver=card(); text(receiver,name,19,TEXT,true);
            text(receiver,member.battery()<0?"Connected · Battery —":"Connected · "+member.battery()+"% battery",13,ACCENT,false);
            Integer level=controller.memberLevel(member.address());
            if(level!=null) slider(receiver,name+" (%)",level,100,true,p->run("Speaker level set",c->c.memberVolume(member.address(),p)));
            button(receiver,"Remove speaker",true,()->run("Speaker removed",c->c.remove(member.address())));
        }
        boolean pair=broadcasting && controller.inventoryKnown && members.size()==1;
        if(pair) {
            LinearLayout mode=card(); text(mode,"Playback",20,TEXT,true);
            button(mode,(controller.audioMode==0?"✓  ":"")+"Double Up",true,()->run("Double Up set",c->c.mode(false)));
            button(mode,(controller.audioMode==0x50?"✓  ":"")+"Stereo",true,()->run("Stereo set",c->{c.mode(true);c.refresh();}));
            if(controller.audioMode==0x50 && controller.balanceSupported) {
                slider(mode,"Balance",controller.balance+128,255,true,p->run("Balance set",c->c.balance(p-128)));
                button(mode,"Centre",true,()->run("Balance centred",c->c.balance(0)));
            }
        }
        if(broadcasting) button(body,"End group",true,()->new AlertDialog.Builder(this).setTitle("End group?")
            .setNegativeButton("Cancel",null).setPositiveButton("End group",(d,w)->run("Group ended",SpeakerController::end)).show());
    }
    private void choose(boolean receiver) { choose(receiver,false); }
    private void choose(boolean receiver,boolean allPaired) {
        if(!permitted()) { requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT},1); return; }
        try {
            BluetoothAdapter bt=adapter();
            if(bt==null) { status="This device has no Bluetooth adapter."; render(); return; }
            if(!bt.isEnabled()) { startActivity(new Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE)); return; }
            List<BluetoothDevice> devices=pairedDevices();
            if(!allPaired) devices.removeIf(d->!knownSpeaker(d));
            devices.removeIf(d->receiver && (d.getAddress().equals(controller.address) || controller.members().stream().anyMatch(m->m.address().equals(d.getAddress()))));
            devices.sort(Comparator.comparing(d->d.getName()==null?d.getAddress():d.getName()));
            String[] labels=new String[devices.size()];
            for(int i=0;i<devices.size();i++) {
                BluetoothDevice d=devices.get(i); String name=d.getName()==null?"Unnamed device":d.getName();
                names.put(d.getAddress(),name); labels[i]=name;
                final String label=name;
                if(devices.stream().filter(other->deviceName(other).equals(label)).count()>1) labels[i]+=" · "+d.getAddress().substring(12);
            }
            if(devices.isEmpty() && !allPaired) {choose(receiver,true);return;}
            if(devices.isEmpty()) { status="No paired speakers available. Pair one in Bluetooth settings."; render(); return; }
            AlertDialog.Builder picker=new AlertDialog.Builder(this).setTitle(allPaired?"Choose a paired speaker":receiver?"Add speaker":"Choose speaker");
            if(!allPaired)picker.setNeutralButton("Other paired speakers",(d,w)->choose(receiver,true));
            picker
                .setItems(labels,(dialog,index)-> {
                    BluetoothDevice d=devices.get(index);
                    connect(d,receiver);
                }).setNegativeButton("Cancel",null).show();
        } catch(SecurityException error) { status="Nearby devices permission is required. Enable it in Android app settings."; render(); }
    }
    private void run(String success,Action action) {
        if(busy || !active) return;
        SpeakerController current=controller; busy=true; status="Updating…"; render();
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
