package io.raph.speakerstudio;

import java.io.*;
import java.util.concurrent.*;

/** One in-flight request. A timeout closes the stream so late replies cannot be reused. */
final class LegacySession implements Closeable {
    interface Notifications { boolean receive(Protocol.Message message) throws IOException; }
    static final class CommandError extends IOException {
        final int status;
        CommandError(int status) {
            super(switch(status) {
                case 1 -> "This speaker does not support that control";
                case 3 -> "Setting outside the speaker's allowed range";
                case 9 -> "Speaker is busy. Wait and retry.";
                default -> "Speaker rejected command (status " + status + ")";
            }); this.status = status;
        }
    }
    private record Pending(int command, int response, CompletableFuture<byte[]> result) {}
    private final InputStream input;
    private final OutputStream output;
    private final Closeable transport;
    private final Notifications notifications;
    private final Runnable disconnected;
    private final Object writeLock = new Object();
    private volatile Pending pending;
    private volatile boolean closed;
    LegacySession(InputStream input, OutputStream output, Closeable transport,
                  Notifications notifications, Runnable disconnected) {
        this.input=input; this.output=output; this.transport=transport;
        this.notifications=notifications; this.disconnected=disconnected;
        Thread reader = new Thread(this::readLoop, "speaker-reader"); reader.setDaemon(true); reader.start();
    }
    boolean isOpen() { return !closed; }
    synchronized byte[] request(int command, int response, byte[] payload) throws Exception {
        return request(command, response, payload, 5000);
    }
    synchronized byte[] request(int command, int response, byte[] payload, long timeout) throws Exception {
        if (closed) throw new IOException("Speaker controls disconnected. Reconnect.");
        Pending next = new Pending(command, response, new CompletableFuture<>()); pending=next;
        try {
            send(new Protocol.Message(command, payload));
            return next.result.get(timeout, TimeUnit.MILLISECONDS);
        } catch (TimeoutException | InterruptedException error) {
            close();
            if (error instanceof InterruptedException) Thread.currentThread().interrupt();
            throw new IOException("Speaker did not respond. Reconnect before retrying.", error);
        } catch (ExecutionException error) {
            if (error.getCause() instanceof Exception cause) throw cause;
            throw new IOException(error);
        } catch (IOException error) { close(); throw error; }
        finally { pending=null; }
    }
    byte[] query(int command, int response) throws Exception { return request(command, response, new byte[0]); }
    void set(int command, byte... payload) throws Exception { request(command, 0, payload); }
    private void send(Protocol.Message message) throws IOException {
        synchronized (writeLock) { output.write(message.encode()); output.flush(); }
    }
    private void readLoop() {
        try {
            while (!closed) {
                Protocol.Message m = Protocol.read(input); byte[] p=m.payload(); Pending active=pending;
                boolean matched=false;
                if (active != null && !active.result.isDone()) {
                    if (m.command()==0 && p.length==3 && Protocol.u16(p,0)==active.command) {
                        if (p[2]!=0) { active.result.completeExceptionally(new CommandError(p[2]&255)); matched=true; }
                        else if (active.response==0) { active.result.complete(p); matched=true; }
                        else matched=true; // A successful queue ACK is not a query result.
                    } else if (active.response!=0 && m.command()==active.response) {
                        active.result.complete(p); matched=true;
                    }
                }
                if (!matched && m.command()!=0 && notifications.receive(m))
                    send(new Protocol.Message(0, new byte[]{(byte)(m.command()>>8),(byte)m.command(),0}));
            }
        } catch (Exception error) { close(); }
    }
    @Override public void close() {
        boolean notify;
        synchronized (writeLock) {
            notify=!closed; closed=true;
            try { transport.close(); } catch (IOException ignored) { }
        }
        Pending active=pending;
        if (active!=null) active.result.completeExceptionally(new IOException("Speaker controls disconnected"));
        if (notify) disconnected.run();
    }
}
