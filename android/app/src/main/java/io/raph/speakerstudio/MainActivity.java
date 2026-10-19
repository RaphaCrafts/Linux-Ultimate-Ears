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
    private static final int BG=0xff1b1e20, CARD=0xff262a2d, TEXT=0xfff3f4f4, MUTED=0xffbbc2c5, CYAN=0xff17b6cf;
    private LinearLayout body;
    private SpeakerController controller;
    private ExecutorService worker;
    private boolean active, busy, party=true;
    private String status="Pair your speakers in Android Bluetooth settings, then choose a host.";
    private final Map<String,String> names=new HashMap<>();
    interface Action { void run(SpeakerController c) throws Exception; }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG); getWindow().setNavigationBarColor(BG);
        getWindow().getDecorView().setSystemUiVisibility(0);
        if(state!=null) party=state.getBoolean("party",true);
        ScrollView scroll=new ScrollView(this); scroll.setFillViewport(true); scroll.setBackgroundColor(BG);
        body=new LinearLayout(this); body.setOrientation(LinearLayout.VERTICAL); body.setPadding(dp(22),dp(18),dp(22),dp(28));
        scroll.addView(body); setContentView(scroll);
        scroll.setOnApplyWindowInsetsListener((v,insets) -> {
            if (Build.VERSION.SDK_INT>=30) {
                android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                v.setPadding(bars.left,bars.top,bars.right,bars.bottom);
            } else v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());
            return insets;
        });
    }
    @Override protected void onStart() {
        super.onStart(); active=true; busy=false;
        controller=new SpeakerController(() -> runOnUiThread(() -> { if(active) render(); }));
        worker=Executors.newSingleThreadExecutor(); render();
    }
    @Override protected void onStop() {
        active=false;
        controller.close(); worker.shutdownNow(); busy=false;
        status="Controls released. Reconnect to read your group; music can continue.";
        super.onStop();
    }
    @Override protected void onSaveInstanceState(Bundle state) { state.putBoolean("party",party); super.onSaveInstanceState(state); }
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
        b.setTextSize(15); b.setMinHeight(dp(48)); b.setEnabled(enabled && !busy);
        b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xff343b40));
        parent.addView(b,new LinearLayout.LayoutParams(-1,-2)); b.setOnClickListener(v -> action.run()); return b;
    }
    private boolean permitted() { return Build.VERSION.SDK_INT<31 || checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED; }
    private BluetoothAdapter adapter() {
        BluetoothManager manager=getSystemService(BluetoothManager.class); return manager==null?null:manager.getAdapter();
    }
    private void render() {
        if(!active) return;
        body.removeAllViews(); boolean connected=controller.connected();
        text(body,"SPEAKER STUDIO",13,CYAN,true);
        text(body,party?"Together sounds better.":"Your speaker.",30,TEXT,true);
        text(body,"Independent controls for Ultimate Ears",14,MUTED,false);
        LinearLayout nav=new LinearLayout(this); body.addView(nav);
        for(String tab:new String[]{"Speaker","PartyUp"}) {
            Button b=new Button(this); b.setText(tab); b.setAllCaps(false); b.setTextColor((tab.equals("PartyUp")==party)?CYAN:TEXT);
            nav.addView(b,new LinearLayout.LayoutParams(0,dp(52),1)); b.setOnClickListener(v->{party=tab.equals("PartyUp");render();});
        }
        LinearLayout info=card(); text(info,busy?"Working…":connected?"Controls connected":"Ready when you are",17,TEXT,true);
        text(info,status,14,MUTED,false);
        if(!permitted()) button(info,"Allow nearby devices",true,()->requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT},1));
        button(info,connected?"Change host speaker":"Choose host speaker",permitted(),()->choose(false));
        button(info,"Bluetooth settings / audio output",true,()->startActivity(new Intent(Settings.ACTION_BLUETOOTH_SETTINGS)));
        if(connected) {
            LinearLayout host=card(); text(host,"HOST SPEAKER",12,CYAN,true);
            ImageView icon=new ImageView(this); icon.setImageResource(io.raph.speakerstudio.R.drawable.ic_speaker);
            icon.setContentDescription("Speaker illustration"); host.addView(icon,new LinearLayout.LayoutParams(-1,dp(110)));
            text(host,controller.name,24,TEXT,true); text(host,controller.model,14,MUTED,false);
            text(host,controller.battery<0?"Battery unavailable":"Battery "+controller.battery+"%",14,MUTED,false);
            text(host,(controller.broadcast&2)!=0?(controller.audioMode==0x50?"Stereo · host left":"PartyUp broadcasting"):"Playing on its own",14,CYAN,false);
            if(controller.volume>=0) {
                text(host,(controller.broadcast&2)!=0?"Group volume":"Speaker volume",16,TEXT,true);
                TextView level=text(host,controller.volume+"%",14,MUTED,false);
                SeekBar slider=new SeekBar(this); slider.setMax(100); slider.setProgress(controller.volume); slider.setEnabled(!busy);
                slider.setContentDescription("Volume percent"); host.addView(slider,new LinearLayout.LayoutParams(-1,dp(48)));
                slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
                    public void onProgressChanged(SeekBar s,int p,boolean user) { level.setText(p+"%"); }
                    public void onStartTrackingTouch(SeekBar s) {}
                    public void onStopTrackingTouch(SeekBar s) { run("Volume read back from host",c->c.volume(s.getProgress())); }
                });
            }
            button(host,"Refresh readings",true,()->run("Readings refreshed",SpeakerController::refresh));
            if(party) renderParty();
            button(body,"Release controls for listening",true,()->run("Controls released. Your speaker group can keep playing.",SpeakerController::disconnect));
        } else {
            LinearLayout guide=card(); text(guide,"One phone. Your speakers.",21,TEXT,true);
            text(guide,"1   Turn on and pair each BOOM / MEGABOOM in Android Bluetooth settings.\n\n2   Choose the speaker receiving your phone's music as the host.\n\n3   Add paired receivers in PartyUp, then play music in your usual app.",16,MUTED,false);
        }
        text(body,"Native PartyUp relays the host's audio to compatible receivers. BOOM 3 and MEGABOOM 3 are the initial targets. Android hardware testing and groups of three or more remain unverified.",12,MUTED,false);
        text(body,"Play music in your usual app. Once your group is ready, you can close Speaker Studio and keep listening. Not affiliated with Ultimate Ears.",12,MUTED,false);
    }
    private void renderParty() {
        LinearLayout group=card(); List<Protocol.Member> members=controller.members();
        text(group,"Playing together",22,TEXT,true);
        text(group,members.size()+" confirmed receiver"+(members.size()==1?"":"s"),14,CYAN,false);
        if((controller.broadcast&2)!=0 && !controller.inventoryKnown)
            text(group,"Full member inventory pending. Only individually confirmed receivers appear below; End group is still available.",14,MUTED,false);
        for(Protocol.Member member:members) {
            String name=names.getOrDefault(member.address(),member.address());
            text(group,name,18,TEXT,true);
            text(group,member.battery()<0?"Group receiver · battery unavailable":"Group receiver · battery "+member.battery()+"%",14,MUTED,false);
            button(group,"Remove "+name,true,()->run("Receiver removed",c->c.remove(member.address())));
        }
        button(group,"+ Add a paired speaker",controller.groupSupported,()->choose(true));
        boolean pair=(controller.broadcast&2)!=0 && controller.inventoryKnown && members.size()==1;
        button(group,"Double Up · full sound on every speaker",pair,()->run("Double Up confirmed",c->c.mode(false)));
        button(group,"Stereo · host left, receiver right",pair,()->run("Stereo confirmed",c->c.mode(true)));
        text(group,"Stereo needs exactly one receiver and a complete group report. Use Double Up for larger groups.",13,MUTED,false);
        button(group,"End group",(controller.broadcast&2)!=0,()->new AlertDialog.Builder(this).setTitle("End this PartyUp group?")
            .setMessage("Receivers will stop playing the host's music.").setNegativeButton("Keep playing",null)
            .setPositiveButton("End group",(d,w)->run("Group end confirmed",SpeakerController::end)).show());
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
                    run(receiver?"Receiver join confirmed":"Host connected. Select it as Android's media output.",c->{if(receiver)c.add(d);else c.connect(d);});
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
            runOnUiThread(()-> { if(active && controller==current) { busy=false; status=message; render(); } });
        });
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results) {
        super.onRequestPermissionsResult(request,permissions,results);
        status=permitted()?"Choose a paired host speaker.":"Nearby devices permission was denied. Allow it in Android app settings to connect.";
        render();
    }
}
