package io.raph.speakerstudio;

import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;
import java.util.*;

public class ProtocolTest {
    @Test public void fragmentedAndConcatenatedFrames() throws Exception {
        byte[] bytes={3,1,(byte)0x9c,(byte)0xfe,2,4,0x16};
        InputStream fragmented=new ByteArrayInputStream(bytes) {
            @Override public synchronized int read(byte[] b,int off,int len) { return super.read(b,off,Math.min(1,len)); }
        };
        Protocol.Message first=Protocol.read(fragmented);
        assertEquals(0x19c,first.command()); assertArrayEquals(new byte[]{(byte)0xfe},first.payload());
        assertEquals(0x416,Protocol.read(fragmented).command());
        assertArrayEquals(new byte[]{3,1,(byte)0x9d,0},new Protocol.Message(0x19d,new byte[]{0}).encode());
    }
    @Test public void invalidAndTruncatedFramesFail() {
        assertThrows(IOException.class,()->Protocol.read(new ByteArrayInputStream(new byte[]{1,0})));
        assertThrows(EOFException.class,()->Protocol.read(new ByteArrayInputStream(new byte[]{4,1,2})));
        assertThrows(IllegalArgumentException.class,()->new Protocol.Message(4,new byte[254]).encode());
    }
    @Test public void inventoryOnlyIncludesPlayingReceivers() throws Exception {
        byte[] p=new byte[21]; p[0]=2;
        System.arraycopy(Protocol.mac("AA:BB:CC:DD:EE:FF"),0,p,1,6);
        p[7]=75; p[8]=8;
        System.arraycopy(Protocol.mac("11:22:33:44:55:66"),0,p,11,6);
        p[17]=50; p[18]=1; // nearby, not a member
        List<Protocol.Member> group=Protocol.members(p);
        assertEquals(1,group.size()); assertEquals("AA:BB:CC:DD:EE:FF",group.get(0).address());
        assertEquals(75,group.get(0).battery());
        assertThrows(IOException.class,()->Protocol.members(new byte[]{2,0}));
        assertThrows(IOException.class,()->Protocol.members(new byte[]{0,0}));
    }
    @Test public void capabilityComesFromIdentity() throws Exception {
        assertEquals("MEGABOOM 3",Protocol.model("HUMBOLDT\0".getBytes()));
        assertThrows(IOException.class,()->Protocol.model("WONDERBOOM".getBytes()));
        assertThrows(IllegalArgumentException.class,()->Protocol.mac("speaker"));
    }
}
