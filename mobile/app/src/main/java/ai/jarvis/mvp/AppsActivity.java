package ai.jarvis.mvp;

import android.app.Activity;
import android.os.Bundle;
import android.view.ViewGroup;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * APK-apps: список web-бандлів із сервера + рендер у WebView. Бандл тягнеться з
 * /api/v1/apps/{id}/bundle і вантажиться через loadDataWithBaseURL (auth — нашим
 * IngestClient, не WebView). Оновлення на сервері = миттєве в додатку без перевстановлення.
 */
public class AppsActivity extends Activity {
    private LinearLayout list;
    private WebView web;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        showList();
        loadApps();
    }

    private void showList() {
        ScrollView sv = new ScrollView(this);
        list = new LinearLayout(this);
        list.setOrientation(LinearLayout.VERTICAL);
        int p = dp(16); list.setPadding(p, p, p, p);
        TextView t = new TextView(this); t.setText("APK-застосунки"); t.setTextSize(22);
        list.addView(t);
        sv.addView(list);
        setContentView(sv);
    }

    private void loadApps() {
        new Thread(new Runnable() { public void run() {
            final String resp = IngestClient.get(AppsActivity.this, "/api/v1/apps");
            runOnUiThread(new Runnable() { public void run() { renderApps(resp); } });
        }}, "apps-list").start();
    }

    private void renderApps(String resp) {
        if (resp == null) { addInfo("Сервер недоступний або не авторизовано."); return; }
        try {
            JSONArray arr = new JSONObject(resp).optJSONArray("apps");
            if (arr == null || arr.length() == 0) { addInfo("Поки немає застосунків."); return; }
            for (int i = 0; i < arr.length(); i++) {
                JSONObject a = arr.getJSONObject(i);
                final String id = a.optString("id");
                String label = a.optString("name", id) + "  (v" + a.optString("version", "1") + ")";
                Button btn = new Button(this);
                btn.setText(label);
                btn.setLayoutParams(new LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
                btn.setOnClickListener(v -> openApp(id));
                list.addView(btn);
            }
        } catch (Exception e) { addInfo("Помилка списку: " + e.getMessage()); }
    }

    private void openApp(final String id) {
        Toast.makeText(this, "Завантаження…", Toast.LENGTH_SHORT).show();
        new Thread(new Runnable() { public void run() {
            final String html = IngestClient.get(AppsActivity.this, "/api/v1/apps/" + id + "/bundle");
            runOnUiThread(new Runnable() { public void run() {
                if (html == null) { Toast.makeText(AppsActivity.this, "Не вдалося завантажити", Toast.LENGTH_SHORT).show(); return; }
                web = new WebView(AppsActivity.this);
                WebSettings s = web.getSettings();
                s.setJavaScriptEnabled(true);
                s.setDomStorageEnabled(true);
                // JS-міст: apk-app може звертатися до функцій телефона (розширюється).
                web.addJavascriptInterface(new AppBridge(), "JARVIS");
                web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null);
                setContentView(web);
            }});
        }}, "apps-open").start();
    }

    /** JS-міст у бандл: window.JARVIS.toast(...) тощо (розширюється під apk-функції). */
    public class AppBridge {
        @android.webkit.JavascriptInterface
        public void toast(String msg) {
            runOnUiThread(() -> Toast.makeText(AppsActivity.this, msg, Toast.LENGTH_SHORT).show());
        }
        @android.webkit.JavascriptInterface
        public String version() { return UpdateChecker.currentVersion(AppsActivity.this); }
    }

    @Override
    public void onBackPressed() {
        if (web != null) { web = null; showList(); loadApps(); } else { super.onBackPressed(); }
    }

    private void addInfo(String t) {
        TextView tv = new TextView(this); tv.setText(t); tv.setPadding(0, dp(12), 0, 0);
        list.addView(tv);
    }
    private int dp(int v) { return (int) (v * getResources().getDisplayMetrics().density + 0.5f); }
}
