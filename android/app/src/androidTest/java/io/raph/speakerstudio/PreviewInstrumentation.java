package io.raph.speakerstudio;

import android.app.*;
import android.content.Intent;
import android.graphics.Bitmap;
import android.os.Bundle;
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
            Field page=MainActivity.class.getDeclaredField("page"), party=MainActivity.class.getDeclaredField("party");page.setAccessible(true);party.setAccessible(true);
            for(String tab:new String[]{"speakers","sound","party"}) {
                runOnMainSync(()->{try {page.set(screen,tab);party.set(screen,tab.equals("party"));render.invoke(screen);}catch(Exception e){throw new RuntimeException(e);}});
                waitForIdleSync(); capture("android-"+tab);
            }
            result.putString("stream","Phone connection, speaker, sound and PartyUp screens rendered successfully.\n");
            finish(Activity.RESULT_OK,result);
        } catch(Exception e) { result.putString("stream",e.toString());finish(Activity.RESULT_CANCELED,result); }
        finally {
            if(fake!=null)fake.close();if(keepAlive!=null)try{keepAlive.close();}catch(IOException ignored){}
            if(activity!=null) { MainActivity screen=activity;runOnMainSync(screen::finish); }
        }
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
