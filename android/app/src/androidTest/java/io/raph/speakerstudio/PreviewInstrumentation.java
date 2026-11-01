package io.raph.speakerstudio;

import android.app.*;
import android.content.Intent;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.lang.reflect.*;

/** Emulator-only visual smoke test. The fake transport never touches Bluetooth. */
public final class PreviewInstrumentation extends Instrumentation {
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        Bundle result=new Bundle(); MainActivity activity=null;
        PipedOutputStream keepAlive=null; LegacySession fake=null;
        try {
            activity=(MainActivity)startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            MainActivity screen=activity;
            waitForIdleSync(); capture("android-connect");
            Field controllerField=MainActivity.class.getDeclaredField("controller"); controllerField.setAccessible(true);
            SpeakerController c=(SpeakerController)controllerField.get(screen);
            PipedInputStream input=new PipedInputStream(); keepAlive=new PipedOutputStream(input);
            fake=new LegacySession(input,new ByteArrayOutputStream(),input,m->false,()->{});
            Field transport=SpeakerController.class.getDeclaredField("session"); transport.setAccessible(true); transport.set(c,fake);
            c.name="Living room"; c.model="MEGABOOM 3"; c.address="00:11:22:33:44:55";
            c.volume=55;c.battery=82;c.eq=3;c.finishCode=0x119;c.customSupported=true;c.bands=new byte[]{-18,8,30,16,0};c.renameSupported=true;c.firmware="1.2.3";
            c.groupSupported=true;c.broadcast=3;c.audioMode=0x50;c.balanceSupported=true;
            byte[] inventory=new byte[11];inventory[0]=1;System.arraycopy(Protocol.mac("00:11:22:33:44:66"),0,inventory,1,6);inventory[7]=16;inventory[8]=8;inventory[9]=4;inventory[10]=0x31;
            c.notification(new Protocol.Message(0x416,inventory));
            byte[] level=new byte[10];System.arraycopy(Protocol.mac("00:11:22:33:44:66"),0,level,0,6);level[7]=0x1e;level[8]=1;level[9]=18;
            c.notification(new Protocol.Message(0x421,level));
            Field names=MainActivity.class.getDeclaredField("names");names.setAccessible(true);
            ((java.util.Map<String,String>)names.get(screen)).put("00:11:22:33:44:66","Kitchen");
            Field status=MainActivity.class.getDeclaredField("status");status.setAccessible(true);status.set(screen,"Preview · simulated speaker readings");
            Method render=MainActivity.class.getDeclaredMethod("render");render.setAccessible(true);
            runOnMainSync(()->{try {render.invoke(screen);}catch(Exception e){throw new RuntimeException(e);}});
            if(screen.getPreferences(0).getInt("finish:"+c.address,-1)!=0x119)throw new AssertionError("Detected finish was not saved");
            runOnMainSync(()->screen.getPreferences(0).edit().putInt("colour:"+c.address,8).apply());
            Method appearance=MainActivity.class.getDeclaredMethod("appearance",String.class,String.class,int.class);appearance.setAccessible(true);
            SpeakerFinish.Finish chosen=(SpeakerFinish.Finish)appearance.invoke(screen,c.address,c.model,c.finishCode);
            if(!chosen.name().equals("Pink"))throw new AssertionError("Manual colour did not override detection");
            runOnMainSync(()->screen.getPreferences(0).edit().remove("colour:"+c.address).apply());
            for(String tab:new String[]{"Speakers","Sound"}) {
                tap(screen,tab);
                waitForIdleSync();
                String required=tab.equals("Speakers")?"+ Add speaker":"Apply EQ";
                if(findButton(screen.getWindow().getDecorView(),required)==null) throw new AssertionError("Missing control: "+required);
                capture("android-"+tab.toLowerCase(java.util.Locale.ROOT));
                if(true) {
                    runOnMainSync(()->{
                        ScrollView scroll=(ScrollView)((android.view.ViewGroup)screen.findViewById(android.R.id.content)).getChildAt(0).findViewWithTag("content-scroll");
                        scroll.fullScroll(View.FOCUS_DOWN);
                    });
                    waitForIdleSync();capture("android-"+tab.toLowerCase(java.util.Locale.ROOT)+"-controls");
                }
            }
            tap(screen,"Speakers");
            if(findButton(screen.getWindow().getDecorView(),"✓  Stereo")==null) throw new AssertionError("Confirmed pair has no stereo control");
            // Incomplete inventory must never offer Stereo, even when a member was reported.
            runOnMainSync(()->{c.inventoryKnown=false;try{render.invoke(screen);}catch(Exception e){throw new RuntimeException(e);}});
            if(findButton(screen.getWindow().getDecorView(),"✓  Stereo")!=null) throw new AssertionError("Stereo offered without complete inventory");
            runOnMainSync(()->{c.inventoryKnown=true;try{render.invoke(screen);}catch(Exception e){throw new RuntimeException(e);}});
            runOnMainSync(()->{
                try {
                    java.util.concurrent.atomic.AtomicInteger committed=new java.util.concurrent.atomic.AtomicInteger(-1);
                    Method slider=MainActivity.class.getDeclaredMethod("slider",LinearLayout.class,String.class,int.class,int.class,boolean.class,java.util.function.IntConsumer.class);slider.setAccessible(true);
                    LinearLayout preview=new LinearLayout(screen);slider.invoke(screen,preview,"Preview volume",55,100,true,(java.util.function.IntConsumer)committed::set);
                    SeekBar volume=(SeekBar)preview.getChildAt(1);Bundle progress=new Bundle();progress.putFloat(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE,65f);
                    volume.performAccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.getId(),progress);
                    if(committed.get()!=65)throw new AssertionError("Accessible volume change did not commit");
                } catch(Exception error){throw new RuntimeException(error);}
            });
            tap(screen,"Sound");
            runOnMainSync(()->{
                View band=screen.getWindow().getDecorView().findViewWithTag("eq-band-0");
                Bundle progress=new Bundle();progress.putFloat(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE,180f);
                if(!band.performAccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.getId(),progress))throw new AssertionError("EQ is not accessible");
            });
            tap(screen,"Speakers");tap(screen,"Sound");
            Field draft=MainActivity.class.getDeclaredField("eqDraft");draft.setAccessible(true);
            if(((byte[])draft.get(screen))[0]!=52)throw new AssertionError("EQ draft lost on tab change");
            capture("android-sound-draft");
            runOnMainSync(()->{c.broadcast=0;try{c.notification(new Protocol.Message(0x416,new byte[]{0}));}catch(Exception e){throw new RuntimeException(e);}});
            tap(screen,"Speakers");capture("android-standalone");
            runOnMainSync(()->{c.battery=-1;c.volume=-1;c.finishCode=-1;try{render.invoke(screen);}catch(Exception e){throw new RuntimeException(e);}});
            waitForIdleSync();capture("android-unavailable");
            if(screen.getPreferences(0).getInt("finish:"+c.address,-1)!=0x119)throw new AssertionError("Unavailable finish erased remembered colour");
            runOnMainSync(()->{c.battery=82;c.volume=55;c.finishCode=0x119;try{render.invoke(screen);}catch(Exception e){throw new RuntimeException(e);}});
            tap(screen,"Speakers");tap(screen,"●  Purple   ·   Colour");capture("android-colour");
            sendKeyDownUpSync(KeyEvent.KEYCODE_BACK);waitForIdleSync();
            runOnMainSync(()->{c.name="Living room upstairs speaker";try{render.invoke(screen);}catch(Exception e){throw new RuntimeException(e);}});
            waitForIdleSync();capture("android-long-name");
            runOnMainSync(()->{c.name="Living room";try{render.invoke(screen);}catch(Exception e){throw new RuntimeException(e);}});
            tap(screen,"Speakers"); tap(screen,"•••");waitForIdleSync();capture("android-settings");
            result.putString("stream","Navigation, colour persistence, EQ draft/accessibility, battery states and stereo gating passed.\n");
            finish(Activity.RESULT_OK,result);
        } catch(Throwable e) { result.putString("stream",e.toString());finish(Activity.RESULT_CANCELED,result); }
        finally {
            if(fake!=null)fake.close();if(keepAlive!=null)try{keepAlive.close();}catch(IOException ignored){}
            if(activity!=null) { MainActivity screen=activity;runOnMainSync(screen::finish); }
        }
    }
    private Button findButton(View view,String label) {
        if(view instanceof Button && label.contentEquals(((Button)view).getText())) return (Button)view;
        if(view instanceof ViewGroup) for(int i=0;i<((ViewGroup)view).getChildCount();i++) {
            Button found=findButton(((ViewGroup)view).getChildAt(i),label);if(found!=null)return found;
        }
        return null;
    }
    private void tap(MainActivity screen,String label) {
        runOnMainSync(()->{
            Button button=findButton(screen.getWindow().getDecorView(),label);
            if(button==null || !button.isEnabled()) throw new AssertionError("Unavailable button: "+label);
            button.performClick();
        });
        waitForIdleSync();
    }
    private void capture(String name) throws Exception {
        // Wait for a composited frame after the main thread has become idle.
        long deadline=android.os.SystemClock.uptimeMillis()+10000;
        while(true) {
            android.view.accessibility.AccessibilityNodeInfo window=getUiAutomation().getRootInActiveWindow();
            if(window!=null && "io.raph.speakerstudio".contentEquals(window.getPackageName())) break;
            if(android.os.SystemClock.uptimeMillis()>deadline) throw new IOException("Another window is obscuring the app");
            Thread.sleep(250);
        }
        Thread.sleep(750);
        Bitmap image=getUiAutomation().takeScreenshot();
        if(image==null)throw new IOException("Screenshot unavailable");
        try(FileOutputStream out=new FileOutputStream(new File(getTargetContext().getExternalFilesDir(null),name+".png"))) {
            image.compress(Bitmap.CompressFormat.PNG,100,out);
        } finally { image.recycle(); }
    }
}
