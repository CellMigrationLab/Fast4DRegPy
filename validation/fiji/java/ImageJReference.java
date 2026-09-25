import ij.process.FloatProcessor;
import ij.process.ImageProcessor;
import java.io.*;
import java.nio.*;
import java.nio.file.*;

/**
 * Calls ImageJ's own ImageProcessor.translate and FloatProcessor.resize on a
 * little-endian float32 plane so Fast4DRegPy's NumPy port can be compared
 * against the real implementation.
 *
 * Usage: translate IN W H DX DY OUT | resize IN W H NEW_H OUT
 */
public class ImageJReference {
    static FloatProcessor read(String path, int w, int h) throws IOException {
        ByteBuffer b = ByteBuffer.wrap(Files.readAllBytes(Paths.get(path))).order(ByteOrder.LITTLE_ENDIAN);
        float[] px = new float[w * h];
        b.asFloatBuffer().get(px);
        return new FloatProcessor(w, h, px);
    }

    static void write(ImageProcessor ip, String path) throws IOException {
        float[] px = (float[]) ip.getPixels();
        ByteBuffer b = ByteBuffer.allocate(px.length * 4).order(ByteOrder.LITTLE_ENDIAN);
        b.asFloatBuffer().put(px);
        Files.write(Paths.get(path), b.array());
    }

    public static void main(String[] a) throws IOException {
        int w = Integer.parseInt(a[2]), h = Integer.parseInt(a[3]);
        FloatProcessor fp = read(a[1], w, h);
        fp.setInterpolationMethod(ImageProcessor.BICUBIC);
        if (a[0].equals("translate")) {
            fp.translate(Double.parseDouble(a[4]), Double.parseDouble(a[5]));
            write(fp, a[6]);
        } else {
            write(fp.resize(w, Integer.parseInt(a[4])), a[5]);
        }
    }
}
