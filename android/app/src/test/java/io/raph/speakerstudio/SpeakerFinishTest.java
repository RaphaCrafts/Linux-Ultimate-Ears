package io.raph.speakerstudio;

import org.junit.Test;
import static org.junit.Assert.*;

public class SpeakerFinishTest {
    @Test public void supportedFinishesRespectHostModel() {
        assertEquals("Purple",SpeakerFinish.detected("MEGABOOM 3",0x119).name());
        assertEquals("Unicorn pink",SpeakerFinish.detected("MEGABOOM 3",0x431).name());
        assertEquals("Blue",SpeakerFinish.detected("BOOM 3",0x112).name());
        assertSame(SpeakerFinish.UNKNOWN,SpeakerFinish.detected("BOOM 3",0x119));
        assertSame(SpeakerFinish.UNKNOWN,SpeakerFinish.detected("BOOM 2",0x431));
    }
    @Test public void groupColourDoesNotInventAModel() {
        assertEquals("Purple",SpeakerFinish.detected("",0x119).name());
        assertEquals("Unicorn pink",SpeakerFinish.detected("",0x431).name());
        assertSame(SpeakerFinish.UNKNOWN,SpeakerFinish.detected("",0xffff));
        assertSame(SpeakerFinish.UNKNOWN,SpeakerFinish.detected("",-1));
        assertSame(SpeakerFinish.UNKNOWN,SpeakerFinish.detected("",0));
    }
    @Test public void finishQueryReadsUnsignedCodeAndToleratesBusy() throws Exception {
        try(ControllerControlsTest.Rig r=new ControllerControlsTest.Rig()) {
            java.util.concurrent.Future<?> peer=r.worker.submit(()->{try {
                r.reply(0x1be,new byte[0],0x1bf,(byte)4,(byte)0x31);
                r.reply(0x1be,new byte[0],0,(byte)1,(byte)0xbe,(byte)9);
            }catch(Exception e){throw new RuntimeException(e);}});
            r.controller.readFinish();assertEquals(0x431,r.controller.finishCode);
            r.controller.readFinish();assertEquals(0x431,r.controller.finishCode);
            peer.get(2,java.util.concurrent.TimeUnit.SECONDS);
        }
    }
}
