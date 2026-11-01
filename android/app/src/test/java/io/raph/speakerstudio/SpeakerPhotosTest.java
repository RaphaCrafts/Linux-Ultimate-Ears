package io.raph.speakerstudio;
import org.junit.Test;
import static org.junit.Assert.*;
public class SpeakerPhotosTest {
    @Test public void selectsExactKnownProductPhotographs() {
        assertEquals("speakers/megaboom-3-unicorn-pink.webp",SpeakerPhotos.path("MEGABOOM 3",0x431,-1));
        assertEquals("speakers/megaboom-3-ultraviolet-purple.webp",SpeakerPhotos.path("",0x119,-1));
        assertEquals("speakers/boom-3-lagoon-blue.webp",SpeakerPhotos.path("BOOM 3",0x112,-1));
        assertEquals("speakers/megaboom-3-unicorn-pink.webp",SpeakerPhotos.path("MEGABOOM 3",0x119,8));
    }
    @Test public void unknownModelsAndUnavailableFinishesUseFallback() {
        assertNull(SpeakerPhotos.path("MEGABOOM",0x119,-1));
        assertNull(SpeakerPhotos.path("",0,-1));
        assertNull(SpeakerPhotos.path("MEGABOOM 3",0,-1));
        assertNull(SpeakerPhotos.path("MEGABOOM 3",0x117,-1));
    }
}
