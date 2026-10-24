package io.raph.speakerstudio;

import android.content.Context;
import android.graphics.*;
import android.view.View;

/** Original vector illustration; scales cleanly at every phone density. */
final class SpeakerArtwork extends View {
    private final Paint paint=new Paint(3);
    private final boolean pair;
    private final Shader glow=new RadialGradient(0,65,150,new int[]{0x3026d7c5,0x0026d7c5},null,Shader.TileMode.CLAMP);
    private final Shader teal=new LinearGradient(-48,0,48,0,new int[]{0xff101b22,0xff147d80,0xff14262b},null,Shader.TileMode.CLAMP);
    private final Shader violet=new LinearGradient(-48,0,48,0,new int[]{0xff101b22,0xff575aa4,0xff14262b},null,Shader.TileMode.CLAMP);
    public SpeakerArtwork(Context context) { this(context,false); }
    SpeakerArtwork(Context context,boolean pair) {
        super(context); this.pair=pair; setContentDescription(pair?"Two speakers playing together":"Ultimate Ears style speaker illustration");
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float scale=Math.min(getWidth()/360f,getHeight()/230f);
        canvas.save(); canvas.translate(getWidth()/2f,getHeight()/2f); canvas.scale(scale,scale);
        paint.setShader(glow);
        canvas.drawOval(-165,-70,165,115,paint); paint.setShader(null);
        if(pair) { canvas.save(); canvas.translate(68,8); canvas.rotate(12); speaker(canvas,0xff575aa4); canvas.restore(); }
        canvas.save(); canvas.translate(pair?-57:0,-3); canvas.rotate(pair?-10:-6); speaker(canvas,0xff147d80); canvas.restore(); canvas.restore();
    }
    private void speaker(Canvas c,int color) {
        paint.setColor(0x50000000); c.drawOval(-54,87,54,103,paint);
        paint.setShader(color==0xff147d80?teal:violet);
        c.drawRoundRect(-47,-96,47,95,30,30,paint); paint.setShader(null);
        paint.setColor(0x306ce1dc);
        for(int y=-73;y<79;y+=5) for(int x=-38;x<40;x+=5) c.drawCircle(x,y,0.7f,paint);
        paint.setColor(0xff172a2e); c.drawOval(-47,-96,47,-72,paint);
        paint.setColor(0xff62e6d2); c.drawCircle(0,-84,3,paint);
        paint.setColor(0xffb3fff0); paint.setStrokeWidth(6); paint.setStrokeCap(Paint.Cap.ROUND);
        c.drawLine(-13,-25,13,-25,paint); c.drawLine(0,-38,0,-12,paint); c.drawLine(-13,27,13,27,paint);
    }
}
