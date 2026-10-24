package io.raph.speakerstudio;

import org.junit.Test;
import static org.junit.Assert.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class SpeakerSettingsTest {
    @Test public void namesUseUtf8BytesAndTerminator() throws Exception {
        assertEquals("Café",SpeakerSettings.decodeName(SpeakerSettings.encodeName("  Café  ")));
        assertEquals(31,SpeakerSettings.encodeName("é".repeat(15)).length);
        assertThrows(IOException.class,()->SpeakerSettings.encodeName("é".repeat(16)));
        assertThrows(IOException.class,()->SpeakerSettings.encodeName("bad\nname"));
        assertThrows(IOException.class,()->SpeakerSettings.encodeName(" "));
        assertThrows(IOException.class,()->SpeakerSettings.decodeName("missing null".getBytes(StandardCharsets.UTF_8)));
        assertThrows(IOException.class,()->SpeakerSettings.decodeName(new byte[]{(byte)0xff,0}));
    }
    @Test public void powerNotificationInvalidatesControlsAndReadings() throws Exception {
        try(SpeakerController c=new SpeakerController(()->{})) {
            c.eq=3;c.firmware="1.2";c.renameSupported=true;c.bands=new byte[5];
            assertTrue(c.notification(new Protocol.Message(0x443,new byte[0])));
            assertFalse(c.connected());assertEquals(-1,c.eq);assertNull(c.bands);assertEquals("",c.firmware);
        }
    }
    @Test public void balancePushUsesSignedByte() throws Exception {
        try(SpeakerController c=new SpeakerController(()->{})) {
            assertTrue(c.notification(new Protocol.Message(0x19c,new byte[]{(byte)-128})));
            assertEquals(-128,c.balance);assertTrue(c.balanceSupported);
            assertFalse(c.notification(new Protocol.Message(0x19c,new byte[0])));
            assertFalse(c.notification(new Protocol.Message(0x421,new byte[10])));
        }
    }
}
