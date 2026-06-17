package ai.jarvis.mvp;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

/**
 * Головний екран — нативний чат із JARVIS (Стовп C). Оригінальний UI (бульбашки +
 * поле вводу + голос), не копіює чужих застосунків. Логін: сервер + Telegram-auth.
 * Уся бізнес-логіка на сервері (S3) — клієнт лише представлення.
 */
public class ChatActivity extends Activity {
    private LinearLayout messages;
    private ScrollView scroll;
    private EditText input;
    private boolean busy = false;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        // Deeplink jarvis://pair?server=&token= (QR зі штабу).
        Uri data = getIntent() != null ? getIntent().getData() : null;
        if (data != null && "jarvis".equals(data.getScheme()) && "pair".equals(data.getHost())) {
            doPair(data.getQueryParameter("server"), data.getQueryParameter("token"));
            return;
        }
        if (TextUtils.isEmpty(Prefs.url(this))) {
            showLogin();
        } else {
            showChat();
        }
    }

    // ---------------- Логін ----------------
    private void showLogin() {
        LinearLayout root = vbox(dp(24));
        TextView title = new TextView(this);
        title.setText("JARVIS"); title.setTextSize(32); root.addView(title);
        TextView hint = new TextView(this);
        hint.setText("Адреса твого JARVIS-сервера (LAN або tunnel):");
        hint.setPadding(0, dp(16), 0, dp(8)); root.addView(hint);

        final EditText server = new EditText(this);
        server.setSingleLine(true);
        server.setText(TextUtils.isEmpty(Prefs.url(this)) ? "http://" : Prefs.url(this));
        root.addView(server);

        Button tg = bigButton("Увійти через Telegram");
        tg.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                String url = normalize(server.getText().toString());
                if (url.isEmpty()) { toast("Вкажи адресу сервера"); return; }
                Prefs.get(ChatActivity.this).edit().putString(Prefs.KEY_URL, url).apply();
                loginViaTelegram();
            }
        });
        root.addView(tg);

        Button console = bigButton("Відкрити веб-консоль");
        console.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                String url = normalize(server.getText().toString());
                if (url.isEmpty()) { toast("Вкажи адресу сервера"); return; }
                Prefs.get(ChatActivity.this).edit().putString(Prefs.KEY_URL, url).apply();
                openConsole();
            }
        });
        root.addView(console);
        setContentView(wrapScroll(root));
    }

    private void loginViaTelegram() {
        toast("Відкриваю Telegram…");
        new Thread(new Runnable() {
            public void run() {
                final String token = TgAuth.start(ChatActivity.this);
                if (token == null) {
                    runOnUiThread(new Runnable() { public void run() {
                        toast("Не вдалося почати логін (сервер?)"); } });
                    return;
                }
                final boolean ok = TgAuth.poll(ChatActivity.this, token);
                runOnUiThread(new Runnable() { public void run() {
                    if (ok) { toast("✅ Вхід виконано"); showChat(); }
                    else { toast("Логін не підтверджено — спробуй ще"); }
                } });
            }
        }, "tg-login").start();
    }

    private void doPair(final String server, final String token) {
        toast("Парування…");
        new Thread(new Runnable() {
            public void run() {
                final boolean ok = Pairing.redeem(ChatActivity.this, server, token);
                runOnUiThread(new Runnable() { public void run() {
                    if (ok) showChat(); else { toast("Парування не вдалося"); showLogin(); }
                } });
            }
        }, "pair").start();
    }

    // ---------------- Чат ----------------
    private void showChat() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);

        scroll = new ScrollView(this);
        scroll.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        messages = new LinearLayout(this);
        messages.setOrientation(LinearLayout.VERTICAL);
        messages.setPadding(dp(12), dp(12), dp(12), dp(12));
        scroll.addView(messages);
        root.addView(scroll);

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setPadding(dp(8), dp(8), dp(8), dp(8));
        input = new EditText(this);
        input.setHint("Повідомлення…");
        input.setLayoutParams(new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        bar.addView(input);
        Button mic = new Button(this); mic.setText("🎤");
        mic.setOnClickListener(new View.OnClickListener() { public void onClick(View v) { voice(); } });
        bar.addView(mic);
        Button send = new Button(this); send.setText("➤");
        send.setOnClickListener(new View.OnClickListener() { public void onClick(View v) { sendCurrent(); } });
        bar.addView(send);
        root.addView(bar);

        setContentView(root);
        if (messages.getChildCount() == 0) {
            addBubble("Привіт! Я JARVIS. Питай — і я використаю твій контекст.", false);
        }
        CollectorScheduler.ensurePeriodic(this);
        NtfyService.apply(this);
    }

    private void sendCurrent() {
        if (busy) return;
        final String text = input.getText().toString().trim();
        if (text.isEmpty()) return;
        input.setText("");
        addBubble(text, true);
        final TextView typing = addBubble("…", false);
        busy = true;
        new Thread(new Runnable() {
            public void run() {
                final String reply = ChatClient.send(ChatActivity.this, text);
                runOnUiThread(new Runnable() { public void run() {
                    typing.setText(reply); busy = false; scrollDown();
                } });
            }
        }, "chat-send").start();
    }

    private void voice() {
        if (busy) return;
        if (checkSelfPermission("android.permission.RECORD_AUDIO")
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.RECORD_AUDIO"}, 2);
            toast("Дай дозвіл на мікрофон і повтори"); return;
        }
        final TextView rec = addBubble("🎤 запис 4с…", true);
        busy = true;
        new Thread(new Runnable() {
            public void run() {
                String transcript = "", reply = "";
                try {
                    String resp = Voice.send(ChatActivity.this, Voice.record(ChatActivity.this, 4000));
                    if (resp != null) {
                        JSONObject o = new JSONObject(resp);
                        transcript = o.optString("transcript", "");
                        reply = o.optString("reply", "");
                    }
                } catch (Exception ignored) {}
                final String t = transcript.isEmpty() ? "(не розпізнано)" : transcript;
                final String r = reply.isEmpty() ? "—" : reply;
                runOnUiThread(new Runnable() { public void run() {
                    rec.setText(t); addBubble(r, false); busy = false;
                } });
            }
        }, "chat-voice").start();
    }

    private TextView addBubble(String text, boolean user) {
        TextView tv = new TextView(this);
        tv.setText(text);
        tv.setTextColor(user ? Color.WHITE : Color.parseColor("#111111"));
        tv.setPadding(dp(12), dp(8), dp(12), dp(8));
        GradientDrawable bg = new GradientDrawable();
        bg.setCornerRadius(dp(16));
        bg.setColor(user ? Color.parseColor("#2C7BE5") : Color.parseColor("#ECECEC"));
        tv.setBackground(bg);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.gravity = user ? Gravity.END : Gravity.START;
        lp.topMargin = dp(6);
        tv.setLayoutParams(lp);
        messages.addView(tv);
        scrollDown();
        return tv;
    }

    private void scrollDown() {
        scroll.post(new Runnable() { public void run() { scroll.fullScroll(View.FOCUS_DOWN); } });
    }

    private void openConsole() {
        startActivity(new Intent(this, MainActivity.class));
    }

    // ---------------- Меню ----------------
    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, 1, 0, "Новий чат");
        menu.add(0, 5, 1, "APK-застосунки");
        menu.add(0, 2, 2, "Веб-консоль");
        menu.add(0, 3, 3, "Контекст / налаштування");
        menu.add(0, 4, 4, "Вийти / змінити сервер");
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        switch (item.getItemId()) {
            case 1:
                if (messages != null) { messages.removeAllViews();
                    addBubble("Новий чат. Слухаю.", false); }
                return true;
            case 5: startActivity(new Intent(this, AppsActivity.class)); return true;
            case 2: openConsole(); return true;
            case 3: startActivity(new Intent(this, SettingsActivity.class)); return true;
            case 4:
                Prefs.get(this).edit().remove(Prefs.KEY_TOKEN).remove(Prefs.KEY_URL).apply();
                showLogin();
                return true;
        }
        return super.onOptionsItemSelected(item);
    }

    // ---------------- helpers ----------------
    private LinearLayout vbox(int pad) {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(pad, pad, pad, pad);
        return l;
    }
    private ScrollView wrapScroll(View v) { ScrollView s = new ScrollView(this); s.addView(v); return s; }
    private Button bigButton(String label) {
        Button b = new Button(this);
        b.setText(label);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(12);
        b.setLayoutParams(lp);
        return b;
    }
    private String normalize(String raw) {
        String u = raw == null ? "" : raw.trim();
        if (u.isEmpty() || u.equals("http://") || u.equals("https://")) return "";
        if (!u.startsWith("http://") && !u.startsWith("https://")) u = "http://" + u;
        return u;
    }
    private void toast(String m) { Toast.makeText(this, m, Toast.LENGTH_SHORT).show(); }
    private int dp(int v) { return (int) (v * getResources().getDisplayMetrics().density + 0.5f); }
}
