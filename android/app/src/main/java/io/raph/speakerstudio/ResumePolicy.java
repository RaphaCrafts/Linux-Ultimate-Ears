package io.raph.speakerstudio;

import java.util.List;

/** Resume only a confirmed speaker already exposed as a phone audio output. */
final class ResumePolicy {
    static String choose(String previous,boolean enabled,List<String> activeSpeakers) {
        if(!enabled)return null;
        if(activeSpeakers.contains(previous))return previous;
        return activeSpeakers.size()==1?activeSpeakers.get(0):null;
    }
}
