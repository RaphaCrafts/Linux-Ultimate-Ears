package io.raph.speakerstudio;

import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.concurrent.*;

public class ControllerControlsTest {
    static class Rig implements AutoCloseable {
        final SpeakerController controller=new SpeakerController(()->{});
        final PipedInputStream input=new PipedInputStream(), speakerInput=new PipedInputStream();
        final PipedOutputStream speakerOutput=new PipedOutputStream(input), output=new PipedOutputStream(speakerInput);
        final ExecutorService worker=Executors.newSingleThreadExecutor();
        Rig() throws Exception {
            LegacySession session=new LegacySession(input,output,()->{input.close();output.close();},controller::notification,()->{});
            Field field=SpeakerController.class.getDeclaredField("session");field.setAccessible(true);field.set(controller,session);
        }
        void reply(int expected,byte[] request,int response,byte... payload) throws Exception {
            Protocol.Message wire=Protocol.read(speakerInput);assertEquals(expected,wire.command());assertArrayEquals(request,wire.payload());
            speakerOutput.write(new Protocol.Message(response,payload).encode());speakerOutput.flush();
        }
        void ack(int command,byte... payload) throws Exception { reply(command,payload,0,(byte)(command>>8),(byte)command,(byte)0); }
        public void close() throws Exception {controller.close();speakerInput.close();speakerOutput.close();worker.shutdownNow();}
    }
    @Test public void renameRequiresConfirmedUtf8Name() throws Exception {
        try(Rig r=new Rig()) {
            r.controller.renameSupported=true;
            Future<?> peer=r.worker.submit(()->{try {
                r.ack(0x16f,SpeakerSettings.encodeName("Café"));
                r.reply(0x16d,new byte[0],0x16e,SpeakerSettings.encodeName("Other"));
            }catch(Exception e){throw new RuntimeException(e);}});
            assertThrows(IOException.class,()->r.controller.rename("Café"));peer.get(2,TimeUnit.SECONDS);
            assertEquals("Other",r.controller.name);
        }
    }
    @Test public void balanceChecksStereoAndReadsActualPosition() throws Exception {
        try(Rig r=new Rig()) {
            r.controller.groupSupported=true;r.controller.inventoryKnown=true;r.controller.balanceSupported=true;
            byte[] member=Arrays.copyOf(Protocol.mac("00:11:22:33:44:66"),7);
            r.controller.notification(new Protocol.Message(0x418,member));
            Future<?> peer=r.worker.submit(()->{try {
                r.reply(0x414,new byte[0],0x415,(byte)3,(byte)0x50);
                r.ack(0x19d,(byte)-35);
                r.reply(0x19b,new byte[0],0x19c,(byte)-34);
            }catch(Exception e){throw new RuntimeException(e);}});
            r.controller.balance(-35);peer.get(2,TimeUnit.SECONDS);assertEquals(-34,r.controller.balance);
        }
    }
    @Test public void groupVolumeReappliesStereoBalance() throws Exception {
        try(Rig r=new Rig()) {
            r.controller.broadcast=3;r.controller.audioMode=0x50;r.controller.balance=-20;r.controller.balanceSupported=true;
            Future<?> peer=r.worker.submit(()->{try {
                r.ack(0x18d,(byte)16);
                assertEquals(0x41b,Protocol.read(r.speakerInput).command());
                // The group sync can push its reset balance before its ACK.
                r.speakerOutput.write(new Protocol.Message(0x19c,new byte[]{0}).encode());r.speakerOutput.flush();
                assertEquals(0,Protocol.read(r.speakerInput).command());
                r.speakerOutput.write(new Protocol.Message(0,new byte[]{4,0x1b,0}).encode());r.speakerOutput.flush();
                r.ack(0x19d,(byte)-20);
                r.reply(0x18e,new byte[0],0x18f,(byte)16);
            }catch(Exception e){throw new RuntimeException(e);}});
            r.controller.volume(50);peer.get(2,TimeUnit.SECONDS);assertEquals(52,r.controller.volume);
        }
    }
    @Test public void unconfirmedReceiverLevelCannotBeWritten() throws Exception {
        try(Rig r=new Rig()) {
            assertThrows(IOException.class,()->r.controller.memberVolume("00:11:22:33:44:66",80));
        }
    }
}
