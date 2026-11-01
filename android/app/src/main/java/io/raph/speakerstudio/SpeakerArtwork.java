package io.raph.speakerstudio;

import android.content.Context;
import android.graphics.*;
import android.view.View;

/** Shared product photograph with an original vector fallback for unknown finishes. */
final class SpeakerArtwork extends View {
    private final Paint paint=new Paint(3);
    private Bitmap photo;
    private final RectF photoBounds=new RectF();
    private static final android.util.LruCache<String,Bitmap> PHOTOS=new android.util.LruCache<>(8*1024*1024) {
        @Override protected int sizeOf(String key,Bitmap value){return value.getByteCount();}
    };
    private final boolean pair;
    private int speakerColour=0xff147d80;
    private Shader bodyShader,glowShader;
    private final Shader secondShader=new LinearGradient(-48,0,48,0,new int[]{0xff181929,0xff575aa4,0xff252646},null,Shader.TileMode.CLAMP);
    private void palette() {
        bodyShader=new LinearGradient(-48,0,48,0,new int[]{shade(speakerColour,.28f),speakerColour,shade(speakerColour,.42f)},null,Shader.TileMode.CLAMP);
        glowShader=new RadialGradient(0,65,150,new int[]{0x30000000|(speakerColour&0xffffff),speakerColour&0xffffff},null,Shader.TileMode.CLAMP);
    }
    public SpeakerArtwork(Context context) { this(context,false); }
    SpeakerArtwork(Context context,boolean pair) {
        super(context); this.pair=pair;palette(); setContentDescription(pair?"Two speakers playing together":"Ultimate Ears style speaker illustration");
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
    }
    SpeakerArtwork(Context context,int colour) { this(context,false);speakerColour=colour;palette(); }
    SpeakerArtwork(Context context,int colour,String asset) {
        this(context,colour);
        if(asset!=null) {
            photo=PHOTOS.get(asset);
            if(photo==null)try(java.io.InputStream input=context.getAssets().open(asset)) {
                photo=BitmapFactory.decodeStream(input);if(photo!=null)PHOTOS.put(asset,photo);
            }catch(java.io.IOException ignored){}
        }
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if(photo!=null) {
            float scale=Math.min(getWidth()/(float)photo.getWidth(),getHeight()/(float)photo.getHeight());
            float width=photo.getWidth()*scale,height=photo.getHeight()*scale;
            photoBounds.set((getWidth()-width)/2,(getHeight()-height)/2,(getWidth()+width)/2,(getHeight()+height)/2);
            canvas.drawBitmap(photo,null,photoBounds,paint);return;
        }
        float scale=Math.min(getWidth()/(getWidth()<getHeight()?130f:360f),getHeight()/230f);
        canvas.save(); canvas.translate(getWidth()/2f,getHeight()/2f); canvas.scale(scale,scale);
        paint.setShader(glowShader);
        canvas.drawOval(-165,-70,165,115,paint); paint.setShader(null);
        if(pair) { canvas.save(); canvas.translate(68,8); canvas.rotate(12); speaker(canvas,0xff575aa4); canvas.restore(); }
        canvas.save(); canvas.translate(pair?-57:0,-3); canvas.rotate(pair?-10:-6); speaker(canvas,speakerColour); canvas.restore(); canvas.restore();
    }
    private int shade(int c,float scale) { return Color.rgb(Math.round(Color.red(c)*scale),Math.round(Color.green(c)*scale),Math.round(Color.blue(c)*scale)); }
    private void speaker(Canvas c,int color) {
        paint.setColor(0x50000000); c.drawOval(-54,87,54,103,paint);
        paint.setShader(color==speakerColour?bodyShader:secondShader);
        c.drawRoundRect(-47,-96,47,95,30,30,paint); paint.setShader(null);
        paint.setColor(0x40ffffff);
        for(int y=-73;y<79;y+=5) for(int x=-38;x<40;x+=5) c.drawCircle(x,y,0.7f,paint);
        paint.setColor(shade(color,.35f)); c.drawOval(-47,-96,47,-72,paint);
        paint.setColor(0xff62e6d2); c.drawCircle(0,-84,3,paint);
        paint.setColor(0xfff5f5f0); paint.setStrokeWidth(6); paint.setStrokeCap(Paint.Cap.ROUND);
        c.drawLine(-13,-25,13,-25,paint); c.drawLine(0,-38,0,-12,paint); c.drawLine(-13,27,13,27,paint);
    }
}
