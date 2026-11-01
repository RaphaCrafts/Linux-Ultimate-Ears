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
            c.volume=55;c.battery=82;c.eq=3;c.customSupported=true;c.bands=new byte[]{0,0,0,0,0};c.renameSupported=true;c.firmware="1.2.3";
            c.groupSupported=true;c.broadcast=3;c.audioMode=0x50;c.balanceSupported=true;
            byte[] inventory=new byte[11];inventory[0]=1;System.arraycopy(Protocol.mac("00:11:22:33:44:66"),0,inventory,1,6);inventory[7]=75;inventory[8]=8;
            c.notification(new Protocol.Message(0x416,inventory));
            Field status=MainActivity.class.getDeclaredField("status");status.setAccessible(true);status.set(screen,"Preview · simulated speaker readings");
            Method render=MainActivity.class.getDeclaredMethod("render");render.setAccessible(true);
            runOnMainSync(()->{try {render.invoke(screen);}catch(Exception e){throw new RuntimeException(e);}});
            for(String tab:new String[]{"Speakers","Mix","Sound"}) {
                tap(screen,tab);
                waitForIdleSync();
                String required=tab.equals("Speakers")?"Find speaker":tab.equals("Mix")?"+ Add speaker":"Apply EQ";
                if(findButton(screen.getWindow().getDecorView(),required)==null) throw new AssertionError("Missing control: "+required);
                capture("android-"+(tab.equals("Mix")?"party":tab.toLowerCase(java.util.Locale.ROOT)));
                if(!tab.equals("Speakers")) {
                    runOnMainSync(()->{
                        ScrollView scroll=(ScrollView)((android.view.ViewGroup)screen.findViewById(android.R.id.content)).getChildAt(0).findViewWithTag("content-scroll");
                        scroll.fullScroll(View.FOCUS_DOWN);
                    });
                    waitForIdleSync();capture("android-"+tab.toLowerCase(java.util.Locale.ROOT)+"-controls");
                }
            }
            tap(screen,"Mix");
            if(findButton(screen.getWindow().getDecorView(),"✓  Stereo")==null) throw new AssertionError("Confirmed pair has no stereo control");
            // Incomplete inventory must never offer Stereo, even when a member was reported.
            runOnMainSync(()->{c.inventoryKnown=false;try{render.invoke(screen);}catch(Exception e){throw new RuntimeException(e);}});
            if(findButton(screen.getWindow().getDecorView(),"✓  Stereo")!=null) throw new AssertionError("Stereo offered without complete inventory");
            runOnMainSync(()->{c.inventoryKnown=true;try{render.invoke(screen);}catch(Exception e){throw new RuntimeException(e);}});
            tap(screen,"Speakers"); tap(screen,"•••");waitForIdleSync();capture("android-settings");
            result.putString("stream","Connection, tab navigation, primary controls, stereo gating and settings passed.\n");
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
