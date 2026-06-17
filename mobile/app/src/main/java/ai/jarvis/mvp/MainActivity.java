package ai.jarvis.mvp;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

/**
 * JARVIS MVP-клієнт (Стовп C, CL-3.2/CL-3.3).
 *
 * Тонкий WebView поверх власного JARVIS-сервера: перший запуск питає URL сервера
 * (LAN/tunnel), зберігає в SharedPreferences і відкриває веб-консоль. Жодної
 * бізнес-логіки на клієнті (AGENTS.md S3) — лише представлення + канал-UX.
 */
public class MainActivity extends Activity {

    private static final String PREFS = "jarvis_prefs";
    private static final String KEY_URL = "server_url";
    private static final int MENU_RELOAD = 1;
    private static final int MENU_CHANGE = 2;
    private static final int MENU_SETTINGS = 3;

    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // B2: deeplink jarvis://pair?server=&token= (зі сканованого QR штабу).
        android.net.Uri data = getIntent() != null ? getIntent().getData() : null;
        if (data != null && "jarvis".equals(data.getScheme()) && "pair".equals(data.getHost())) {
            handlePair(data.getQueryParameter("server"), data.getQueryParameter("token"));
            return;
        }
        String url = prefs().getString(KEY_URL, "");
        if (TextUtils.isEmpty(url)) {
            showSetup("");
        } else {
            showWebView(url);
        }
    }

    /** Паруємо у фоні: redeem токен → JWT → відкриваємо веб-консоль. */
    private void handlePair(final String server, final String token) {
        Toast.makeText(this, "Парування з сервером…", Toast.LENGTH_SHORT).show();
        new Thread(new Runnable() {
            public void run() {
                final boolean ok = Pairing.redeem(MainActivity.this, server, token);
                runOnUiThread(new Runnable() {
                    public void run() {
                        if (ok) {
                            showWebView(server + "/app");
                        } else {
                            Toast.makeText(MainActivity.this, "Не вдалося спарувати", Toast.LENGTH_LONG).show();
                            showSetup(server == null ? "" : server);
                        }
                    }
                });
            }
        }, "jarvis-pair").start();
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    /** Екран налаштування сервера (перший запуск або «Змінити сервер»). */
    private void showSetup(String current) {
        webView = null;
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(20);
        root.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("JARVIS");
        title.setTextSize(28);
        root.addView(title);

        TextView hint = new TextView(this);
        hint.setText("Адреса твого JARVIS-сервера (LAN або tunnel):");
        hint.setPadding(0, dp(12), 0, dp(8));
        root.addView(hint);

        final EditText input = new EditText(this);
        input.setHint("http://192.168.0.100:8000/app");
        input.setSingleLine(true);
        input.setText(TextUtils.isEmpty(current) ? "http://" : current);
        input.setSelection(input.getText().length());
        root.addView(input);

        Button save = new Button(this);
        save.setText("Зберегти й відкрити");
        save.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        save.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                String url = normalize(input.getText().toString());
                if (TextUtils.isEmpty(url)) {
                    Toast.makeText(MainActivity.this, "Вкажи коректну адресу", Toast.LENGTH_SHORT).show();
                    return;
                }
                prefs().edit().putString(KEY_URL, url).apply();
                showWebView(url);
            }
        });
        root.addView(save);

        TextView tip = new TextView(this);
        tip.setText("Підказка: для Telegram Mini App відкрий <сервер>/app, "
                + "для веб-консолі — <сервер>/platform.");
        tip.setPadding(0, dp(16), 0, 0);
        tip.setTextSize(12);
        root.addView(tip);

        setContentView(root);
    }

    /** Основний екран — WebView на сервер JARVIS. */
    private void showWebView(String url) {
        webView = new WebView(this);
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                // Голос/медіа з веб-консолі (CL-3.4) — віддаємо запитані ресурси.
                request.grant(request.getResources());
            }
        });
        setContentView(webView);
        webView.loadUrl(url);
        // Якщо колектори контексту увімкнені — переконатися, що upload запланований.
        CollectorScheduler.ensurePeriodic(this);
        NtfyService.apply(this); // F1: старт push-сервісу, якщо увімкнено
        // A5: тиха перевірка оновлень (нову версію качати з <сервер>/platform/apk).
        new Thread(new Runnable() {
            public void run() {
                final String newer = UpdateChecker.newerVersion(MainActivity.this);
                if (newer != null) {
                    runOnUiThread(new Runnable() {
                        public void run() {
                            Toast.makeText(MainActivity.this,
                                    "Доступна версія " + newer + " — завантаж із /platform/apk",
                                    Toast.LENGTH_LONG).show();
                        }
                    });
                }
            }
        }, "jarvis-update").start();
    }

    /** Нормалізує введену адресу: додає схему, відкидає порожні. */
    private String normalize(String raw) {
        if (raw == null) {
            return "";
        }
        String url = raw.trim();
        if (url.isEmpty() || url.equals("http://") || url.equals("https://")) {
            return "";
        }
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "http://" + url;
        }
        return url;
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, MENU_RELOAD, 0, "Оновити");
        menu.add(0, MENU_CHANGE, 1, "Змінити сервер");
        menu.add(0, MENU_SETTINGS, 2, "Контекст / налаштування");
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        int id = item.getItemId();
        if (id == MENU_RELOAD) {
            if (webView != null) {
                webView.reload();
            }
            return true;
        }
        if (id == MENU_CHANGE) {
            showSetup(prefs().getString(KEY_URL, ""));
            return true;
        }
        if (id == MENU_SETTINGS) {
            startActivity(new android.content.Intent(this, SettingsActivity.class));
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
