package ai.jarvis.mvp;

import android.content.Context;
import android.media.MediaRecorder;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;

/**
 * C2: нативний голос — записати з мікрофона (MediaRecorder, m4a) і відправити на
 * /api/v1/voice (STT → агент). Потребує RECORD_AUDIO. Викликати у фоні (блокуючий запис).
 */
public final class Voice {
    private Voice() {}

    public static byte[] record(Context c, int ms) throws Exception {
        File f = File.createTempFile("voice", ".m4a", c.getCacheDir());
        MediaRecorder r = new MediaRecorder();
        try {
            r.setAudioSource(MediaRecorder.AudioSource.MIC);
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
            r.setOutputFile(f.getAbsolutePath());
            r.prepare();
            r.start();
            Thread.sleep(ms);
            r.stop();
        } finally {
            r.release();
        }
        byte[] data = readFile(f);
        f.delete();
        return data;
    }

    /** Відправляє аудіо → {transcript, reply}. */
    public static String send(Context c, byte[] audio) {
        return IngestClient.postRaw(c, "/api/v1/voice", audio, "audio/mp4");
    }

    private static byte[] readFile(File f) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        FileInputStream in = new FileInputStream(f);
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        in.close();
        return out.toByteArray();
    }
}
