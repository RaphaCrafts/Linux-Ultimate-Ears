package io.raph.speakerstudio;

import java.util.regex.Pattern;

/** Name hints help discovery; only protocol replies establish control support. */
final class SpeakerDirectory {
    private static final Pattern UE_NAME=Pattern.compile(
        "^(?:(?:UE|ULTIMATE[ _-]*EARS)[ _-]+)?(?:MEGABOOM|WONDERBOOM|EVERBOOM|EPICBOOM|HYPERBOOM|BOOM|ROLL)(?:[ _-]*[0-9]+)?(?:[ _-].*)?$",
        Pattern.CASE_INSENSITIVE);
    static boolean visible(String name,boolean confirmed) {
        return confirmed || name!=null && UE_NAME.matcher(name.trim()).matches();
    }
}
