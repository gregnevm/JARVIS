package ai.jarvis.mvp;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * On-device редакція (перший рівень, дзеркало jarvis_core.passport.redaction):
 * вирізає картки/IBAN/секрети/OTP ДО черги — менше чутливого покидає пристрій.
 */
public final class Redactor {
    private static final Pattern CARD = Pattern.compile("\\b\\d{4}(?:[ -]?\\d{4}){2,4}\\b");
    private static final Pattern IBAN = Pattern.compile("\\b[A-Z]{2}\\d{2}[A-Z0-9]{10,30}\\b");
    private static final Pattern SECRET =
            Pattern.compile("\\b(?:sk|pk|ghp|xox[bp])[-_][A-Za-z0-9]{16,}\\b");
    private static final Pattern OTP = Pattern.compile(
            "(?i)(otp|code|код|пароль|password|verification|підтвердж\\w*)(\\D{0,20}?)(\\d{4,8})\\b");

    private Redactor() {}

    public static String redact(String text) {
        if (text == null || text.isEmpty()) return text == null ? "" : text;
        String out = text;
        out = CARD.matcher(out).replaceAll("[REDACTED:card]");
        out = IBAN.matcher(out).replaceAll("[REDACTED:iban]");
        out = SECRET.matcher(out).replaceAll("[REDACTED:secret]");
        Matcher m = OTP.matcher(out);
        StringBuffer sb = new StringBuffer();
        while (m.find()) {
            m.appendReplacement(sb, Matcher.quoteReplacement(m.group(1) + m.group(2) + "[REDACTED:otp]"));
        }
        m.appendTail(sb);
        return sb.toString();
    }
}
