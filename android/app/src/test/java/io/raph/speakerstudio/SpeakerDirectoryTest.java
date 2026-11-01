package io.raph.speakerstudio;

import org.junit.Test;
import static org.junit.Assert.*;

public class SpeakerDirectoryTest {
    @Test public void namedUeModelsAreSuggested() {
        for(String name:new String[]{"BOOM","UE BOOM 2","MEGABOOM 3","Ultimate Ears MEGABOOM","Wonderboom 4","boom-3","EPICBOOM"," UE ROLL 2 "})
            assertTrue(name,SpeakerDirectory.visible(name,false));
    }
    @Test public void unrelatedBondedDevicesStayOutOfMainList() {
        for(String name:new String[]{"WF-1000XM6","Oura Ring 4","JBL Clip 4","Brompton_Elec","BoomBox","boomerang","PINK 3","Living room"})
            assertFalse(name,SpeakerDirectory.visible(name,false));
        assertFalse(SpeakerDirectory.visible(null,false));
    }
    @Test public void confirmedCustomNamesSurviveRenaming() {
        assertTrue(SpeakerDirectory.visible("PINK 3",true));
        assertTrue(SpeakerDirectory.visible("Living room",true));
        assertTrue(SpeakerDirectory.visible(null,true));
    }
}
