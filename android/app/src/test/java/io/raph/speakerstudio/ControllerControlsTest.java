package io.raph.speakerstudio;

import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.concurrent.*;

public class ControllerControlsTest {
    static class Rig implements AutoCloseable {
        final SpeakerController controller;
        final PipedInputStream input=new PipedInputStream(), speakerInput=new PipedInputStream();
        final PipedOutputStream speakerOutput=new PipedOutputStream(input), output=new PipedOutputStream(speakerInput);
        final ExecutorService worker=Executors.newSingleThreadExecutor();
        Rig() throws Exception { this(new SpeakerController(()->{})); }
        Rig(SpeakerController controller) throws Exception {
            this(controller,true);
        }
        Rig(SpeakerController controller,boolean attach) throws Exception {
            this.controller=controller;
            if(attach) {
                LegacySession session=link(controller::notification,()->{});
                Field field=SpeakerController.class.getDeclaredField("session");field.setAccessible(true);field.set(controller,session);
            }
        }
        LegacySession link(LegacySession.Notifications notifications,Runnable closed) {
            return new LegacySession(input,output,()->{input.close();output.close();},notifications,closed);
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
    @Test public void receiverResultTimeoutPreservesHostAndRejectsLateLevel() throws Exception {
        java.util.concurrent.atomic.AtomicLong clock=new java.util.concurrent.atomic.AtomicLong(10000);
        SpeakerController c=new SpeakerController(()->{},clock::get,clock::addAndGet,25);
        try(Rig r=new Rig(c)) {
            String target="00:11:22:33:44:66";
            c.broadcast=3;c.inventoryKnown=true;
            CountDownLatch lateAck=new CountDownLatch(1);
            c.notification(new Protocol.Message(0x418,Arrays.copyOf(Protocol.mac(target),7)));
            Future<?> peer=r.worker.submit(()->{try {
                byte[] request=Arrays.copyOf(Protocol.mac(target),8);request[7]=0x1e;
                r.ack(0x420,request);
                Thread.sleep(80);
                byte[] result=Arrays.copyOf(request,10);result[8]=1;result[9]=16;
                r.speakerOutput.write(new Protocol.Message(0x421,result).encode());r.speakerOutput.flush();
                assertEquals(0,Protocol.read(r.speakerInput).command());lateAck.countDown();
                r.ack(0x18d,(byte)16);
                r.reply(0x18e,new byte[0],0x18f,(byte)16);
            }catch(Exception e){throw new RuntimeException(e);}});
            c.readMemberLevel(target);
            assertTrue(c.connected());assertNull(c.memberLevel(target));
            assertEquals("Individual volume not reported",c.memberLevelProblem(target));
            c.readMemberLevel(target); // No second request may reuse an unsequenced late reply.
            assertTrue(lateAck.await(2,TimeUnit.SECONDS));
            c.hostVolume(50);peer.get(2,TimeUnit.SECONDS);
            assertTrue(c.connected());assertNull(c.memberLevel(target));assertEquals(52,c.volume);
        }
    }
    @Test public void unconfirmedReceiverLevelCannotBeWritten() throws Exception {
        try(Rig r=new Rig()) {
            assertThrows(IOException.class,()->r.controller.memberVolume("00:11:22:33:44:66",80));
        }
    }
    @Test(timeout=5000) public void retriesFailedSocketAndKeepsControlsWithUnavailableReadings() throws Exception {
        CountDownLatch disconnected=new CountDownLatch(1);
        java.util.concurrent.atomic.AtomicBoolean watch=new java.util.concurrent.atomic.AtomicBoolean();
        try(Rig r=new Rig(new SpeakerController(()->{if(watch.get()) disconnected.countDown();},()->0,millis->{}),false)) {
            byte[] empty=new byte[0];
            Future<?> peer=r.worker.submit(()->{
                r.reply(6,empty,7,"HUMBOLDT".getBytes(java.nio.charset.StandardCharsets.US_ASCII));
                r.reply(0x414,empty,0x415,(byte)0,(byte)0);
                r.reply(0x175,empty,0x176,(byte)0); // Truncated battery reply.
                r.reply(0x18e,empty,0x18f,(byte)16);
                r.reply(0x16d,empty,0,(byte)1,(byte)0x6d,(byte)9); // Name temporarily busy.
                r.reply(3,empty,4,(byte)1,(byte)6,(byte)45);
                r.reply(0x177,empty,0x178,(byte)0);
                r.reply(0x188,empty,0,(byte)1,(byte)0x88,(byte)1);
                r.reply(0x1be,empty,0x1bf,(byte)1,(byte)0x16);
                return null;
            });
            java.util.concurrent.atomic.AtomicInteger opens=new java.util.concurrent.atomic.AtomicInteger();
            r.controller.connect("00:11:22:33:44:55","Garden",(notifications,closed)->{
                if(opens.incrementAndGet()==1) throw new IOException("Temporary socket failure");
                return r.link(notifications,closed);
            });
            assertTrue(r.controller.connected()); assertEquals(2,opens.get());
            assertEquals("MEGABOOM 3",r.controller.model);
            assertEquals(-1,r.controller.battery); assertEquals(52,r.controller.volume);
            assertEquals("Garden",r.controller.name);
            peer.get(2,TimeUnit.SECONDS);
            watch.set(true);
            r.speakerOutput.close();
            assertTrue(disconnected.await(1,TimeUnit.SECONDS));
            assertFalse(r.controller.connected()); assertEquals(-1,r.controller.volume);
            assertEquals("",r.controller.firmware);
        }
    }
}
