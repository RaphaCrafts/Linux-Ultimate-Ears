package io.raph.speakerstudio;

/** Exact catalogue selection. Appearance never grants protocol capabilities. */
final class SpeakerPhotos {
    static String path(String model,int finish,int manual) {
        String family=family(model,finish);if(family==null)return null;
        SpeakerFinish.Finish colour=manual>=0 && manual<SpeakerFinish.PALETTE.length?SpeakerFinish.PALETTE[manual]:SpeakerFinish.detected(model,finish);
        String suffix=switch(colour.name()) {
            case "Black" -> "night-black";case "Blue" -> "lagoon-blue";case "Purple" -> "ultraviolet-purple";
            case "Red" -> "sunset-red";case "Peach" -> "seashell-peach";case "Denim" -> "denim";
            case "Cloud" -> "cloud";case "Pink","Unicorn pink" -> "unicorn-pink";default -> null;
        };
        return suffix==null?null:"speakers/"+family+"-"+suffix+".webp";
    }
    static String family(String model,int finish) {
        if(model.equals("MEGABOOM 3"))return "megaboom-3";
        if(model.equals("BOOM 3"))return "boom-3";
        if(!model.isEmpty())return null;
        // Only a known enum finish can identify a receiver's catalogue family.
        if(finish>=0x116 && finish<=0x11b || finish==0x11e || finish==0x11f || finish==0x431)return "megaboom-3";
        if(finish>=0x110 && finish<=0x115 || finish==0x11c || finish==0x11d)return "boom-3";
        return null;
    }
}
