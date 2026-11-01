package io.raph.speakerstudio;

import android.content.Context;
import android.graphics.*;
import android.view.View;

/** A battery icon with an explicit unknown state; percentage text is supplied beside it. */
final class BatteryIcon extends View {
    private final Paint paint=new Paint(3);
    private final int level;
    public BatteryIcon(Context context) {this(context,-1);}
    BatteryIcon(Context context,int level) {super(context);this.level=level;setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);}
    @Override protected void onDraw(Canvas c) {
        float w=getWidth(),h=getHeight(),top=h*.25f,bottom=h*.75f;
        paint.setColor(0xff69727a);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(h*.06f);
        c.drawRoundRect(w*.05f,top,w*.85f,bottom,h*.08f,h*.08f,paint);
        paint.setStyle(Paint.Style.FILL);c.drawRoundRect(w*.88f,h*.39f,w*.95f,h*.61f,h*.03f,h*.03f,paint);
        if(level>=0) {paint.setColor(level<=10?0xffff8a90:level<=20?0xffffcc80:0xffd5f578);
            c.drawRoundRect(w*.12f,top+h*.08f,w*.12f+w*.66f*Math.max(0,Math.min(100,level))/100,bottom-h*.08f,h*.03f,h*.03f,paint);}
        else {paint.setColor(0xffa9afb4);c.drawRect(w*.35f,h*.47f,w*.57f,h*.53f,paint);}
    }
}
