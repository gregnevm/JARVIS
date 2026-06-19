---
name: self-improve
description: >-
  JARVIS-профіль рушія самопокращення. Тонкий shim → делегує у скіл `kaizen` з `profile:jarvis`.
  Використовуй коли користувач каже (legacy-тригери): "запусти рутину", "самопокращення репо",
  "прокачай репозиторій", "self-improve", "автономний прогон roadmap", "ганяй цикл покращень".
  Уся логіка лупа живе в kaizen; тут лише маршрутизація на JARVIS-профіль. Не для разових правок.
---

# self-improve → kaizen (profile: jarvis)

> **Shim, не форк.** Двигун самопокращення тепер портативний скіл **`kaizen`** (Ports & Adapters);
> усе JARVIS-специфічне — у декораторі-профілі `jarvis`. Цей файл лише маршрутизує й **не повторює**
> жодної механіки лупа/CI/passport (інакше — другий source of truth, DR6).

## Що робити при `/self-improve …`

Виклич скіл **`kaizen`** з профілем **jarvis**:

| Намір користувача | Дія в kaizen |
|---|---|
| `/self-improve` (без аргументів) | `kaizen run --profile jarvis` (дефолтна рутина `kaizen-loop`, 1 ітерація) |
| `/self-improve run [iters=N]` | `kaizen run --profile jarvis --iters N` |
| `/self-improve report` | `kaizen report` (щоденний дайджест) |
| `/self-improve status` | `kaizen status` |
| «прокачай репо / автономний прогон» | `kaizen run --profile jarvis`, спитай N якщо неясно |

## Куди дивитися
- Рушій + контракт лупа: [`../kaizen/SKILL.md`](../kaizen/SKILL.md), [`../kaizen/engine/`](../kaizen/engine/).
- JARVIS-прив'язки (8 портів, verified reuse, CI-матриця, blast-radius, synthetic-UID):
  [`../kaizen/profiles/jarvis/profile.md`](../kaizen/profiles/jarvis/profile.md).
- Артефакти прогонів (back-compat): `data/artifacts/self-improve/` (passports / window.json / resume.json / runs/).

> Конституція JARVIS ([`AGENTS.md`](../../../AGENTS.md)) читається першою через порт `constitution`;
> S1–S5/P1–P10/C1/D1/§6 діють як завжди.
