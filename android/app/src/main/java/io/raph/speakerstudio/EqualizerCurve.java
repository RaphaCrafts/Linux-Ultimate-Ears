package io.raph.speakerstudio;

import android.content.Context;
import android.graphics.*;
import android.view.View;

/** Read-only curve preview; the five native SeekBars provide accessible editing. */
final class EqualizerCurve extends View {
    private final Paint paint=new Paint(3);
    private byte[] bands=new byte[5];
    private final Path path=new Path();
    private final float[] xs=new float[5],ys=new float[5];
    private static final String[] LABELS={"60","300","1k","3k","12k"};
    public EqualizerCurve(Context context) {this(context,new byte[5]);}
    EqualizerCurve(Context context,byte[] bands) {super(context);setBands(bands);setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);}
    void setBands(byte[] values) {bands=values.clone();invalidate();}
    @Override protected void onDraw(Canvas c) {
        float density=getResources().getDisplayMetrics().density,left=16*density,right=getWidth()-16*density,top=12*density,bottom=getHeight()-26*density,mid=(top+bottom)/2;
        paint.setStrokeWidth(density);paint.setColor(0xff384047);
        for(int i=0;i<3;i++)c.drawLine(left,top+(bottom-top)*i/2,right,top+(bottom-top)*i/2,paint);
        path.reset();
        for(int i=0;i<5;i++) {xs[i]=left+(right-left)*i/4;ys[i]=mid-(bands[i]/128f)*(bottom-top)/2;
            c.drawLine(xs[i],top,xs[i],bottom,paint);if(i==0)path.moveTo(xs[i],ys[i]);else path.lineTo(xs[i],ys[i]);}
        paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2.5f*density);paint.setColor(0xffd5f578);c.drawPath(path,paint);paint.setStyle(Paint.Style.FILL);
        for(int i=0;i<5;i++)c.drawCircle(xs[i],ys[i],4*density,paint);
        paint.setColor(0xffa9afb4);paint.setTextSize(11*getResources().getDisplayMetrics().scaledDensity);
        for(int i=0;i<5;i++) {paint.setTextAlign(i==0?Paint.Align.LEFT:i==4?Paint.Align.RIGHT:Paint.Align.CENTER);c.drawText(LABELS[i],xs[i],getHeight()-5*density,paint);}
    }
}
