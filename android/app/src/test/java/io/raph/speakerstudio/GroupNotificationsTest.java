package io.raph.speakerstudio;

import org.junit.Test;
import static org.junit.Assert.*;
import java.io.IOException;
import java.util.Arrays;

public class GroupNotificationsTest {
    private byte[] completion(int status) {
        byte[] p=Arrays.copyOf(Protocol.mac("AA:BB:CC:DD:EE:FF"),7); p[6]=(byte)status; return p;
    }
    @Test public void queueAckDoesNotEstablishMembership() throws Exception {
        try(SpeakerController c=new SpeakerController(()->{})) {
            assertFalse(c.notification(new Protocol.Message(0,new byte[]{4,0x17,0})));
            assertEquals(0,c.members().size());
            assertTrue(c.notification(new Protocol.Message(0x418,completion(0))));
            assertEquals(1,c.members().size());
            assertFalse(c.inventoryKnown); // A single completion is not a complete inventory.
            assertTrue(c.notification(new Protocol.Message(0x41a,completion(0))));
            assertTrue(c.members().isEmpty());
        }
    }
    @Test public void rejectedOrMalformedCompletionNeverAddsMember() throws Exception {
        try(SpeakerController c=new SpeakerController(()->{})) {
            c.notification(new Protocol.Message(0x418,completion(3)));
            assertFalse(c.notification(new Protocol.Message(0x418,new byte[]{0})));
            assertTrue(c.members().isEmpty());
        }
    }
    @Test public void fullInventoryReplacesMembersAndExcludesNearbyDevices() throws Exception {
        try(SpeakerController c=new SpeakerController(()->{})) {
            c.notification(new Protocol.Message(0x418,completion(0)));
            byte[] p=new byte[11];p[0]=1;System.arraycopy(Protocol.mac("11:22:33:44:55:66"),0,p,1,6);
            p[7]=80;p[8]=1;
            c.notification(new Protocol.Message(0x416,p));
            assertTrue(c.inventoryKnown);assertTrue(c.members().isEmpty());
            p[8]=8;c.notification(new Protocol.Message(0x416,p));
            assertEquals("11:22:33:44:55:66",c.members().get(0).address());
            assertThrows(IOException.class,()->c.notification(new Protocol.Message(0x416,new byte[]{2})));
        }
    }
}
