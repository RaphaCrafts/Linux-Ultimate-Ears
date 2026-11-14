package io.raph.speakerstudio;

import org.junit.Test;
import static org.junit.Assert.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicLong;

public class PartyUpStabilityTest {
    private static final String RECEIVER="00:11:22:33:44:66";
    private SpeakerController controller(AtomicLong time,List<Long> pauses) {
        return new SpeakerController(()->{},time::get,ms->{pauses.add(ms);time.addAndGet(ms);});
    }
    private void pair(SpeakerController c) throws Exception {
        byte[] payload=Arrays.copyOf(Protocol.mac(RECEIVER),7);
        c.notification(new Protocol.Message(0x418,payload));
        c.broadcast=3;c.inventoryKnown=true;
    }
    @Test public void joinUsesHostOnlyAndWaitsForReceiverCompletion() throws Exception {
        AtomicLong time=new AtomicLong(1000);List<Long> pauses=new ArrayList<>();
        try(ControllerControlsTest.Rig r=new ControllerControlsTest.Rig(controller(time,pauses))) {
            r.controller.address="00:11:22:33:44:55";r.controller.groupSupported=true;
            CountDownLatch queued=new CountDownLatch(1),complete=new CountDownLatch(1);
            Future<?> peer=r.worker.submit(()->{try {
                r.reply(0x414,new byte[0],0x415,(byte)0,(byte)0);
                r.ack(0x413,(byte)3,(byte)0);
                r.reply(0x414,new byte[0],0x415,(byte)3,(byte)0);
                byte[] target=Arrays.copyOf(Protocol.mac(RECEIVER),7);target[6]=2;
                r.ack(0x417,target);queued.countDown();
                assertTrue(complete.await(2,TimeUnit.SECONDS));target[6]=0;
                r.speakerOutput.write(new Protocol.Message(0x418,target).encode());r.speakerOutput.flush();
                assertEquals(0,Protocol.read(r.speakerInput).command());
            }catch(Exception e){throw new RuntimeException(e);}});
            ExecutorService action=Executors.newSingleThreadExecutor();
            try {
                Future<?> join=action.submit(()->{try {r.controller.add(RECEIVER);}catch(Exception e){throw new RuntimeException(e);}});
                assertTrue(queued.await(2,TimeUnit.SECONDS));assertFalse(join.isDone());assertTrue(r.controller.members().isEmpty());
                complete.countDown();join.get(2,TimeUnit.SECONDS);peer.get(2,TimeUnit.SECONDS);
                assertEquals(RECEIVER,r.controller.members().get(0).address());assertFalse(r.controller.inventoryKnown);
            } finally {complete.countDown();action.shutdownNow();}
        }
    }
    @Test public void modeSwitchWaitsForNewReceiverHandoff() throws Exception {
        AtomicLong time=new AtomicLong(1000);List<Long> pauses=new ArrayList<>();
        try(ControllerControlsTest.Rig r=new ControllerControlsTest.Rig(controller(time,pauses))) {
            pair(r.controller);
            Future<?> peer=r.worker.submit(()->{try {
                Protocol.Message first=Protocol.read(r.speakerInput);
                assertEquals(7000,time.get());assertEquals(0x414,first.command());
                r.speakerOutput.write(new Protocol.Message(0x415,new byte[]{3,0}).encode());r.speakerOutput.flush();
                r.ack(0x413,(byte)3,(byte)0x50);
                r.reply(0x414,new byte[0],0x415,(byte)3,(byte)0x50);
            }catch(Exception e){throw new RuntimeException(e);}});
            r.controller.mode(true);peer.get(2,TimeUnit.SECONDS);
            assertEquals(List.of(6000L),pauses);
        }
    }
    @Test public void addingThirdSpeakerConfirmsDoubleUpBeforeJoining() throws Exception {
        AtomicLong time=new AtomicLong(1000);List<Long> pauses=new ArrayList<>();
        String third="00:11:22:33:44:77";
        try(ControllerControlsTest.Rig r=new ControllerControlsTest.Rig(controller(time,pauses))) {
            pair(r.controller);r.controller.groupSupported=true;time.addAndGet(6000);
            Future<?> peer=r.worker.submit(()->{try {
                r.reply(0x414,new byte[0],0x415,(byte)3,(byte)0x50);
                r.ack(0x413,(byte)3,(byte)0);
                r.reply(0x414,new byte[0],0x415,(byte)3,(byte)0x50);
                r.reply(0x414,new byte[0],0x415,(byte)3,(byte)0);
                byte[] target=Arrays.copyOf(Protocol.mac(third),7);target[6]=2;
                r.ack(0x417,target);target[6]=0;
                r.speakerOutput.write(new Protocol.Message(0x418,target).encode());r.speakerOutput.flush();
                assertEquals(0,Protocol.read(r.speakerInput).command());
            }catch(Exception e){throw new RuntimeException(e);}});
            r.controller.add(third);peer.get(2,TimeUnit.SECONDS);
            assertEquals(List.of(250L,6000L),pauses);
            assertEquals(0,r.controller.audioMode);
            assertEquals(2,r.controller.members().size());
        }
    }
    @Test public void selectingCurrentModeDoesNotRewriteBroadcast() throws Exception {
        AtomicLong time=new AtomicLong(1000);List<Long> pauses=new ArrayList<>();
        try(ControllerControlsTest.Rig r=new ControllerControlsTest.Rig(controller(time,pauses))) {
            pair(r.controller);time.addAndGet(6000);
            Future<?> peer=r.worker.submit(()->{try {
                r.reply(0x414,new byte[0],0x415,(byte)3,(byte)0x50);
            }catch(Exception e){throw new RuntimeException(e);}});
            r.controller.mode(true);peer.get(2,TimeUnit.SECONDS);
            assertEquals(0,r.speakerInput.available());assertTrue(pauses.isEmpty());
        }
    }
    @Test public void explicitBusyRejectionUsesBoundedBackoff() throws Exception {
        AtomicLong time=new AtomicLong(1000);List<Long> pauses=new ArrayList<>();
        try(ControllerControlsTest.Rig r=new ControllerControlsTest.Rig(controller(time,pauses))) {
            pair(r.controller);time.addAndGet(6000);
            Future<?> peer=r.worker.submit(()->{try {
                r.reply(0x414,new byte[0],0x415,(byte)3,(byte)0);
                r.reply(0x413,new byte[]{3,0x50},0,(byte)4,(byte)0x13,(byte)9);
                r.reply(0x413,new byte[]{3,0x50},0,(byte)4,(byte)0x13,(byte)9);
                r.ack(0x413,(byte)3,(byte)0x50);
                r.reply(0x414,new byte[0],0x415,(byte)3,(byte)0x50);
            }catch(Exception e){throw new RuntimeException(e);}});
            r.controller.mode(true);peer.get(2,TimeUnit.SECONDS);
            assertEquals(List.of(300L,600L),pauses);
        }
    }
    @Test public void permanentRejectionIsNotRetried() throws Exception {
        AtomicLong time=new AtomicLong(1000);List<Long> pauses=new ArrayList<>();
        try(ControllerControlsTest.Rig r=new ControllerControlsTest.Rig(controller(time,pauses))) {
            pair(r.controller);time.addAndGet(6000);
            Future<?> peer=r.worker.submit(()->{try {
                r.reply(0x414,new byte[0],0x415,(byte)3,(byte)0);
                r.reply(0x413,new byte[]{3,0x50},0,(byte)4,(byte)0x13,(byte)3);
            }catch(Exception e){throw new RuntimeException(e);}});
            assertThrows(LegacySession.CommandError.class,()->r.controller.mode(true));peer.get(2,TimeUnit.SECONDS);
            assertEquals(0,r.speakerInput.available());assertTrue(pauses.isEmpty());
        }
    }
    @Test public void duplicateReceiverResultIsAckedWithoutAWaiter() throws Exception {
        AtomicLong time=new AtomicLong(1000);List<Long> pauses=new ArrayList<>();
        try(ControllerControlsTest.Rig r=new ControllerControlsTest.Rig(controller(time,pauses))) {
            pair(r.controller);
            byte[] result=Arrays.copyOf(Protocol.mac(RECEIVER),10);result[7]=0x1e;result[8]=1;result[9]=16;
            for(int repeat=0;repeat<2;repeat++) {
                r.speakerOutput.write(new Protocol.Message(0x421,result).encode());r.speakerOutput.flush();
                Protocol.Message ack=Protocol.read(r.speakerInput);
                assertEquals(0,ack.command());assertArrayEquals(new byte[]{4,0x21,0},ack.payload());
            }
            assertEquals(Integer.valueOf(52),r.controller.memberLevel(RECEIVER));
            r.controller.notification(new Protocol.Message(0x41a,Arrays.copyOf(Protocol.mac(RECEIVER),7)));
            assertTrue(r.controller.notification(new Protocol.Message(0x421,result)));
            assertNull(r.controller.memberLevel(RECEIVER));assertTrue(r.controller.members().isEmpty());
            result[9]=32;assertFalse(r.controller.notification(new Protocol.Message(0x421,result)));
        }
    }
}
