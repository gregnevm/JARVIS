# Adapter `sparrow-avia` — як в'яжуться порти

Єдине місце ERP-конкретики. Engine (`../../engine`) лишається generic; тут — прив'язка до Sparrow-Avia.

| Порт engine | Прив'язка Sparrow-Avia |
|---|---|
| `locate` | `manifest.route_map`: тип документа → import-підсторінка. Реальні маршрути — через `inspect_form`. |
| `map` | `manifest.field_aliases`: канонічне поле engine → синоніми лейблів/`name`-атрибутів форми ERP (укр/en). |
| `fill` | `manifest.allowlist`: патерни URL, де дозволено діяти. Поза ними — відмова (blast-radius, deny-wins). |
| `recognize` | `manifest.recognize`: який шлях під який ввід (text/digital/scan) + яка vision-модель. |
| `confirm_gate` | `manifest.confirm.final_submit = human-only`: submit тисне людина/`confirm_approve`. |

## Як зняти реальну form-schema (закриває `_seed`)
1. Відкрий у браузері (за VPN) [erp.sparrow-avia.tech/import/index](https://erp.sparrow-avia.tech/import/index),
   переконайся, що extension опитує `/chrome/poll`.
2. Виклич `erp_sa.inspect_form` → отримаєш `[{selector, name, id, label, type}]` живих полів.
3. Онови `field_aliases` (канонічне поле → реальні `name`/`id`) і `route_map` у `manifest.json`.
4. Drift adapter↔engine лишається під `engine/tests/` — новий тип документа = новий рядок тут, без зміни engine.

## Інваріанти
- **DR2:** engine не згадує «Sparrow»; уся конкретика — у цьому каталозі.
- **S4:** `final_submit = human-only` — не змінювати без явного рішення (концепт §5.4).
- **Blast-radius:** розширювати `allowlist` лише свідомо; кожен новий патерн — окремий ризик.
