package io.raph.speakerstudio;
import org.junit.Test;
import static org.junit.Assert.*;
import java.util.List;
public class ResumePolicyTest {
    @Test public void resumesOnlyActiveKnownOutput() {
        assertEquals("a",ResumePolicy.choose("a",true,List.of("a","b")));
        assertEquals("b",ResumePolicy.choose("a",true,List.of("b")));
        assertNull(ResumePolicy.choose("a",true,List.of()));
        assertNull(ResumePolicy.choose("a",true,List.of("b","c")));
    }
    @Test public void explicitReleaseDisablesRecovery() {
        assertNull(ResumePolicy.choose("a",false,List.of("a")));
    }
}
