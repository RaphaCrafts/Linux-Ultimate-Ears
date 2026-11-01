package io.raph.speakerstudio;

/** Original appearance palette. Finish IDs follow the documented legacy enum. */
final class SpeakerFinish {
    record Finish(String name,int colour) {}
    static final Finish UNKNOWN=new Finish("Colour not set",0xff7e8993);
    static final Finish[] PALETTE={new Finish("Black",0xff444b54),new Finish("Forest",0xff548b74),
        new Finish("Blue",0xff478fcb),new Finish("Purple",0xff9569cf),new Finish("Red",0xffd66069),
        new Finish("Peach",0xffe5aa92),new Finish("Denim",0xff667f9e),new Finish("Cloud",0xffd2d9dc),
        new Finish("Pink",0xffe7a4ce)};
    static Finish detected(String model,int code) {
        int base=model.equals("BOOM 3")?0x110:model.equals("MEGABOOM 3")?0x116:-1;
        if(base>=0 && code>=base && code<base+6)return PALETTE[code-base];
        if((model.isEmpty()||model.equals("MEGABOOM 3")) && code==0x431)return new Finish("Unicorn pink",PALETTE[8].colour());
        if(model.equals("BOOM 3") && (code==0x11c||code==0x11d))return PALETTE[code-0x11c+6];
        if(model.equals("MEGABOOM 3") && (code==0x11e||code==0x11f))return PALETTE[code-0x11e+6];
        // Group records carry a finish ID but no model; show only known enum colours.
        if(model.isEmpty()) {
            if(code>=0x110&&code<=0x11b)return PALETTE[(code-0x110)%6];
            if(code>=0x11c&&code<=0x11f)return PALETTE[(code-0x11c)%2+6];
        }
        return UNKNOWN;
    }
}
