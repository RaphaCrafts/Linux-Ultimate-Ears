package io.raph.speakerstudio;

import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;
import java.util.concurrent.*;

public class LegacySessionTest {
    static class Peer implements AutoCloseable {
        final PipedInputStream clientInput=new PipedInputStream();
        final PipedOutputStream speakerOutput=new PipedOutputStream(clientInput);
        final PipedInputStream speakerInput=new PipedInputStream();
        final PipedOutputStream clientOutput=new PipedOutputStream(speakerInput);
        final LegacySession session;
        final ExecutorService executor=Executors.newSingleThreadExecutor();
        Peer() throws IOException {
            session=new LegacySession(clientInput,clientOutput,()->{clientInput.close();clientOutput.close();},
                m->m.command()==0x19c && m.payload().length==1,()->{});
        }
        void send(int command,byte... payload) throws IOException { speakerOutput.write(new Protocol.Message(command,payload).encode()); speakerOutput.flush(); }
        Future<byte[]> request(int command,int response,long timeout) { return executor.submit(()->session.request(command,response,new byte[0],timeout)); }
        public void close() throws Exception { session.close();speakerInput.close();speakerOutput.close();executor.shutdownNow(); }
    }
    @Test public void queryAckDoesNotCompleteQuery() throws Exception {
        try(Peer p=new Peer()) {
            Future<byte[]> result=p.request(6,7,2000); assertEquals(6,Protocol.read(p.speakerInput).command());
            p.send(0,(byte)0,(byte)6,(byte)0);
            assertThrows(TimeoutException.class,()->result.get(50,TimeUnit.MILLISECONDS));
            p.send(7,(byte)'B'); assertArrayEquals(new byte[]{'B'},result.get(1,TimeUnit.SECONDS));
        }
    }
    @Test public void unrelatedAckCannotCompleteSetter() throws Exception {
        try(Peer p=new Peer()) {
            Future<byte[]> result=p.request(0x417,0,2000); Protocol.read(p.speakerInput);
            p.send(0,(byte)4,(byte)0x19,(byte)0);
            assertThrows(TimeoutException.class,()->result.get(50,TimeUnit.MILLISECONDS));
            p.send(0,(byte)4,(byte)0x17,(byte)0); assertEquals(3,result.get(1,TimeUnit.SECONDS).length);
        }
    }
    @Test public void errorsAndTimeoutsAreNotSuccess() throws Exception {
        try(Peer p=new Peer()) {
            Future<byte[]> result=p.request(6,7,2000); Protocol.read(p.speakerInput); p.send(0,(byte)0,(byte)6,(byte)1);
            assertTrue(assertThrows(ExecutionException.class,()->result.get(1,TimeUnit.SECONDS)).getCause() instanceof LegacySession.CommandError);
            Future<byte[]> timed=p.request(6,7,80); Protocol.read(p.speakerInput);
            assertThrows(ExecutionException.class,()->timed.get(1,TimeUnit.SECONDS)); assertFalse(p.session.isOpen());
            assertThrows(IOException.class,()->p.session.query(6,7));
        }
    }
    @Test public void unsolicitedBalanceIsAcknowledgedWithoutCompletingPendingQuery() throws Exception {
        try(Peer p=new Peer()) {
            Future<byte[]> result=p.request(6,7,2000); Protocol.read(p.speakerInput);
            p.send(0x19c,(byte)0xfe);
            Protocol.Message ack=Protocol.read(p.speakerInput); assertEquals(0,ack.command());
            assertArrayEquals(new byte[]{1,(byte)0x9c,0},ack.payload()); assertFalse(result.isDone());
            p.send(7,(byte)'B'); result.get(1,TimeUnit.SECONDS);
        }
    }
    @Test public void closeUnblocksOutstandingRequest() throws Exception {
        try(Peer p=new Peer()) {
            Future<byte[]> result=p.request(6,7,2000); Protocol.read(p.speakerInput); p.session.close();
            assertThrows(ExecutionException.class,()->result.get(1,TimeUnit.SECONDS));
        }
    }
}
