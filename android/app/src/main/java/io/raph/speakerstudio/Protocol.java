package io.raph.speakerstudio;

import java.io.*;
import java.util.*;

/** Original legacy codec, shared wire format with the Linux implementation. */
final class Protocol {
    record Message(int command, byte[] payload) {
        byte[] encode() {
            if (command < 0 || command > 65535 || payload.length > 253)
                throw new IllegalArgumentException("Frame exceeds legacy limits");
            byte[] frame = new byte[payload.length + 3];
            frame[0] = (byte)(payload.length + 2);
            frame[1] = (byte)(command >> 8); frame[2] = (byte)command;
            System.arraycopy(payload, 0, frame, 3, payload.length);
            return frame;
        }
    }
    static Message read(InputStream input) throws IOException {
        int length = input.read();
        if (length < 0) throw new EOFException("Speaker disconnected");
        if (length < 2) throw new IOException("Invalid speaker frame length");
        byte[] frame = new byte[length];
        int offset = 0;
        while (offset < length) {
            int count = input.read(frame, offset, length - offset);
            if (count < 0) throw new EOFException("Incomplete speaker frame");
            offset += count;
        }
        return new Message(u16(frame, 0), Arrays.copyOfRange(frame, 2, length));
    }
    static int u16(byte[] p, int offset) { return (p[offset] & 255) * 256 + (p[offset+1] & 255); }
    static byte[] mac(String address) {
        if (!address.matches("(?i)([0-9a-f]{2}:){5}[0-9a-f]{2}"))
            throw new IllegalArgumentException("Invalid Bluetooth address");
        String[] parts = address.split(":"); byte[] bytes = new byte[6];
        for (int i=0; i<6; i++) bytes[i] = (byte)Integer.parseInt(parts[i], 16);
        return bytes;
    }
    static String address(byte[] payload, int offset) {
        StringJoiner result = new StringJoiner(":");
        for (int i=offset; i<offset+6; i++) result.add(String.format(Locale.ROOT, "%02X", payload[i] & 255));
        return result.toString();
    }
    record Member(String address, int battery) {}
    static List<Member> members(byte[] p) throws IOException {
        if (p.length == 0 || p.length != 1 + (p[0]&255)*10) throw new IOException("Invalid group inventory");
        List<Member> members = new ArrayList<>();
        for (int i=1; i<p.length; i+=10) {
            int state = u16(p, i+6), battery = (state >> 8) & 127;
            if ((state & 15) == 8) members.add(new Member(address(p,i), battery <= 100 ? battery : -1));
        }
        return members;
    }
    static String model(byte[] payload) throws IOException {
        String identity = new String(payload, java.nio.charset.StandardCharsets.US_ASCII).replaceAll("\u0000+$", "");
        return switch (identity) {
            case "TITUS" -> "MEGABOOM"; case "HUMBOLDT" -> "MEGABOOM 3";
            case "BOOM" -> "BOOM"; case "MAXIMUS" -> "BOOM 2"; case "MENDOCINO" -> "BOOM 3";
            default -> throw new IOException("Unsupported model. Initial targets: BOOM 3 / MEGABOOM 3.");
        };
    }
}
