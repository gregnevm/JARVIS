package ai.jarvis.mvp;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.text.TextUtils;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

/**
 * Налаштування контексту (D1/E1/E4/E5): per-source toggles (default OFF), логін,
 * пауза-паніка, дозволи, «синхронізувати зараз», журнал прозорості, стерти все.
 */
public class SettingsActivity extends Activity {
    private EditText url, user, pass, token, exclude, ntfyUrl, ntfyTopic;
    private Switch swNotif, swSms, swCalls, swPause, swPush;
    private TextView status;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        SharedPreferences p = Prefs.get(this);
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(16);
        root.setPadding(pad, pad, pad, pad);
        scroll.addView(root);

        addTitle(root, "Контекст JARVIS");
        addHint(root, "Усі джерела вимкнені за замовчуванням. Дані йдуть ЛИШЕ на твій сервер.");

        url = addField(root, "Сервер (LAN/tunnel)", p.getString(Prefs.KEY_URL, "http://"), false);
        user = addField(root, "Користувач", p.getString(Prefs.KEY_USER, "admin"), false);
        pass = addField(root, "Пароль (PLATFORM_PASSWORD)", p.getString(Prefs.KEY_PASS, ""), true);
        token = addField(root, "JWT-токен (опційно)", p.getString(Prefs.KEY_TOKEN, ""), false);

        swNotif = addSwitch(root, "Збирати сповіщення", Prefs.collect(this, Prefs.KEY_COLLECT_NOTIF));
        swSms = addSwitch(root, "Збирати SMS", Prefs.collect(this, Prefs.KEY_COLLECT_SMS));
        swCalls = addSwitch(root, "Збирати дзвінки (метадані)", Prefs.collect(this, Prefs.KEY_COLLECT_CALLS));
        swPause = addSwitch(root, "⏸ Пауза (стоп усього збору)", Prefs.paused(this));

        addHint(root, "Дзвінки/SMS можуть містити дані інших людей — використовуй для особистого вжитку.");
        // E7: disclaimer згоди третіх сторін при ввімкненні calls/SMS.
        swSms.setOnCheckedChangeListener(thirdPartyGuard());
        swCalls.setOnCheckedChangeListener(thirdPartyGuard());

        // E6: per-contact/app exclude (нічого від цих не збираємо).
        exclude = addField(root, "Виключити (номери/імена/застосунки, через кому)",
                p.getString(Prefs.KEY_EXCLUDE, ""), false);

        // F1: приймати push (ntfy / UnifiedPush) — daily-дайджест, пропозиції.
        swPush = addSwitch(root, "🔔 Отримувати push (ntfy)", p.getBoolean(Prefs.KEY_PUSH_ON, false));
        ntfyUrl = addField(root, "ntfy URL", p.getString(Prefs.KEY_NTFY_URL, "https://ntfy.sh"), false);
        ntfyTopic = addField(root, "ntfy топік (унікальний)", p.getString(Prefs.KEY_NTFY_TOPIC, ""), false);

        addButton(root, "Дозвіл: доступ до сповіщень", new View.OnClickListener() {
            public void onClick(View v) {
                startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));
            }
        });
        addButton(root, "Дозволи: SMS + дзвінки", new View.OnClickListener() {
            public void onClick(View v) {
                requestPermissions(new String[]{
                        "android.permission.READ_SMS",
                        "android.permission.READ_CALL_LOG"}, 1);
            }
        });
        addButton(root, "💾 Зберегти", new View.OnClickListener() {
            public void onClick(View v) { save(); }
        });
        addButton(root, "🔄 Синхронізувати зараз", new View.OnClickListener() {
            public void onClick(View v) {
                save();
                CollectorScheduler.runNow(SettingsActivity.this);
                toast("Запущено синхронізацію…");
            }
        });
        addButton(root, "📋 Журнал (що зібрано)", new View.OnClickListener() {
            public void onClick(View v) { loadLedger(); }
        });
        addButton(root, "🎤 Голос (4с → агент)", new View.OnClickListener() {
            public void onClick(View v) { recordVoice(); }
        });
        addButton(root, "🗑 Стерти весь контекст на сервері", new View.OnClickListener() {
            public void onClick(View v) { purge(); }
        });

        status = new TextView(this);
        status.setPadding(0, dp(12), 0, 0);
        root.addView(status);

        setContentView(scroll);
    }

    private void save() {
        Prefs.get(this).edit()
                .putString(Prefs.KEY_URL, url.getText().toString().trim())
                .putString(Prefs.KEY_USER, user.getText().toString().trim())
                .putString(Prefs.KEY_PASS, pass.getText().toString())
                .putString(Prefs.KEY_TOKEN, token.getText().toString().trim())
                .putBoolean(Prefs.KEY_COLLECT_NOTIF, swNotif.isChecked())
                .putBoolean(Prefs.KEY_COLLECT_SMS, swSms.isChecked())
                .putBoolean(Prefs.KEY_COLLECT_CALLS, swCalls.isChecked())
                .putBoolean(Prefs.KEY_PAUSED, swPause.isChecked())
                .putString(Prefs.KEY_EXCLUDE, exclude.getText().toString().trim())
                .putString(Prefs.KEY_NTFY_URL, ntfyUrl.getText().toString().trim())
                .putString(Prefs.KEY_NTFY_TOPIC, ntfyTopic.getText().toString().trim())
                .putBoolean(Prefs.KEY_PUSH_ON, swPush.isChecked())
                .apply();
        CollectorScheduler.ensurePeriodic(this);
        NtfyService.apply(this); // F1: старт/стоп push-сервісу
        toast("Збережено");
    }

    /** E7: при першому ввімкненні SMS/дзвінків — disclaimer згоди третіх сторін. */
    private android.widget.CompoundButton.OnCheckedChangeListener thirdPartyGuard() {
        return new android.widget.CompoundButton.OnCheckedChangeListener() {
            public void onCheckedChanged(final android.widget.CompoundButton btn, boolean checked) {
                if (!checked || Prefs.get(SettingsActivity.this).getBoolean(Prefs.KEY_TP_ACK, false)) {
                    return;
                }
                new android.app.AlertDialog.Builder(SettingsActivity.this)
                        .setTitle("Дані третіх сторін")
                        .setMessage("Збір SMS/дзвінків може містити дані інших людей. Використовуй "
                                + "лише для особистого вжитку; усе йде ЛИШЕ на твій сервер.")
                        .setPositiveButton("Розумію", new android.content.DialogInterface.OnClickListener() {
                            public void onClick(android.content.DialogInterface d, int w) {
                                Prefs.get(SettingsActivity.this).edit()
                                        .putBoolean(Prefs.KEY_TP_ACK, true).apply();
                            }
                        })
                        .setNegativeButton("Скасувати", new android.content.DialogInterface.OnClickListener() {
                            public void onClick(android.content.DialogInterface d, int w) {
                                btn.setChecked(false);
                            }
                        })
                        .setCancelable(false)
                        .show();
            }
        };
    }

    private void loadLedger() {
        status.setText("Завантаження журналу…");
        new Thread(new Runnable() {
            public void run() {
                final String resp = IngestClient.post(SettingsActivity.this,
                        "/api/v1/context/ledger", new JSONObject());
                runOnUiThread(new Runnable() {
                    public void run() {
                        if (resp == null) { status.setText("Сервер недоступний."); return; }
                        try {
                            JSONObject o = new JSONObject(resp);
                            status.setText("Усього паспортів: " + o.optInt("total", 0)
                                    + "\nПо типах: " + o.optJSONObject("by_kind")
                                    + "\nПо джерелах: " + o.optJSONObject("by_source"));
                        } catch (Exception e) {
                            status.setText("Журнал: " + resp);
                        }
                    }
                });
            }
        }).start();
    }

    private void purge() {
        status.setText("Стираю…");
        new Thread(new Runnable() {
            public void run() {
                final String resp = IngestClient.post(SettingsActivity.this,
                        "/api/v1/context/purge", new JSONObject());
                runOnUiThread(new Runnable() {
                    public void run() {
                        status.setText(resp == null ? "Не вдалося стерти." : "Стерто: " + resp);
                    }
                });
            }
        }).start();
    }

    private void recordVoice() {
        if (checkSelfPermission("android.permission.RECORD_AUDIO")
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.RECORD_AUDIO"}, 2);
            toast("Дай дозвіл на мікрофон і повтори");
            return;
        }
        save();
        status.setText("🎤 Запис 4с…");
        new Thread(new Runnable() {
            public void run() {
                String out;
                try {
                    byte[] audio = Voice.record(SettingsActivity.this, 4000);
                    String resp = Voice.send(SettingsActivity.this, audio);
                    if (resp == null) {
                        out = "Сервер недоступний / порожньо.";
                    } else {
                        JSONObject o = new JSONObject(resp);
                        out = "Ти: " + o.optString("transcript", "—")
                                + "\nJARVIS: " + o.optString("reply", "—");
                    }
                } catch (Exception e) {
                    out = "Помилка запису: " + e.getMessage();
                }
                final String text = out;
                runOnUiThread(new Runnable() {
                    public void run() { status.setText(text); }
                });
            }
        }, "jarvis-voice").start();
    }

    // ---- UI helpers ----
    private void addTitle(LinearLayout root, String t) {
        TextView tv = new TextView(this);
        tv.setText(t); tv.setTextSize(24); tv.setPadding(0, 0, 0, dp(8));
        root.addView(tv);
    }
    private void addHint(LinearLayout root, String t) {
        TextView tv = new TextView(this);
        tv.setText(t); tv.setTextSize(12); tv.setPadding(0, dp(4), 0, dp(8));
        root.addView(tv);
    }
    private EditText addField(LinearLayout root, String hint, String value, boolean password) {
        TextView label = new TextView(this);
        label.setText(hint); label.setPadding(0, dp(8), 0, 0);
        root.addView(label);
        EditText e = new EditText(this);
        e.setSingleLine(true);
        if (password) e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        if (!TextUtils.isEmpty(value)) e.setText(value);
        root.addView(e);
        return e;
    }
    private Switch addSwitch(LinearLayout root, String label, boolean checked) {
        Switch s = new Switch(this);
        s.setText(label); s.setChecked(checked); s.setPadding(0, dp(10), 0, 0);
        root.addView(s);
        return s;
    }
    private void addButton(LinearLayout root, String label, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(label);
        b.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        b.setOnClickListener(l);
        root.addView(b);
    }
    private void toast(String m) { Toast.makeText(this, m, Toast.LENGTH_SHORT).show(); }
    private int dp(int v) { return (int) (v * getResources().getDisplayMetrics().density + 0.5f); }
}
