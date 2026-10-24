package io.raph.speakerstudio;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.*;
import java.util.Arrays;

/** Same UTF-8 limits as the desktop; never silently truncate a name. */
final class SpeakerSettings {
    static byte[] encodeName(String text) throws IOException {
        String value=text.trim();
        if(value.isEmpty() || value.codePoints().anyMatch(c -> c<32 || c==127))
            throw new IOException("Enter a name without control characters");
        byte[] bytes=value.getBytes(StandardCharsets.UTF_8);
        if(bytes.length>30) throw new IOException("Speaker names can use up to 30 UTF-8 bytes");
        return Arrays.copyOf(bytes,bytes.length+1);
    }
    static String decodeName(byte[] bytes) throws IOException {
        int end=0; while(end<bytes.length && bytes[end]!=0) end++;
        if(end==bytes.length) throw new IOException("Speaker name is missing its terminator");
        try {
            String result=StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes,0,end)).toString();
            encodeName(result); return result;
        } catch(CharacterCodingException e) { throw new IOException("Speaker returned an invalid UTF-8 name",e); }
    }
}
