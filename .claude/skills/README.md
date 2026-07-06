# Skills — індекс і governance

> Портфельний індекс скілів JARVIS + правило, який **тип** скіла обрати (щоб не плодити форки й
> другі джерела істини — узагальнення kaizen DR5/DR6 на весь репо). SSOT принципів — [`AGENTS.md`](../../AGENTS.md).

## Два неймспейси (не плутати)

| Неймспейс | Хто читає | Призначення |
|---|---|---|
| **`.claude/skills/`** (цей каталог) | **харнес Claude Code** (CLI/IDE) | інструменти розробника над репо: луп самопокращення, конектор платформи |
| **`data/skills/`** | **рантайм-агент JARVIS** (`tools/app/agent.py`) | поведінка самого продукту: автокодинг, дайджести, quick-capture |

> Скіл одного неймспейсу **не** виконується іншим. Новий скіл → спершу обери неймспейс за «хто читає».

## `.claude/skills/` (харнес)

| Скіл | Тип | Що | Деталі |
|---|---|---|---|
| [`kaizen`](kaizen/SKILL.md) | **engine** | портативний рушій самопокращення (Ports&Adapters, говорить портами) | [`engine/ports.md`](kaizen/engine/ports.md) |
| [`self-improve`](self-improve/SKILL.md) | **shim** | legacy-тригери → `kaizen` з `profile:jarvis` | — |
| [`jarvis`](jarvis/SKILL.md) | **connector** | вихідний MCP-роз'єм до платформи (connector+adapter+skill) | [`../../docs/JARVIS_CONNECTOR_CONCEPT.md`](../../docs/JARVIS_CONNECTOR_CONCEPT.md) |

## `data/skills/` (рантайм-агент)

| Скіл | Тип | Що |
|---|---|---|
| [`auto-coder`](../../data/skills/auto-coder/SKILL.md) | leaf | автономний OKR-цикл розробки (autopilot) |
| [`code-review`](../../data/skills/code-review/SKILL.md) | leaf | рев'ю дифу (узгодь із [`docs/DIFF_REVIEW.md`](../../docs/DIFF_REVIEW.md)) |
| [`phone-digest`](../../data/skills/phone-digest/SKILL.md) | leaf | дайджест на телефон |
| [`quick-capture`](../../data/skills/quick-capture/SKILL.md) | leaf | швидкий захоплювач нотаток |

## Таксономія типів (який обрати)

| Тип | Коли | Інваріант |
|---|---|---|
| **engine** | generic-логіка, що працює над будь-яким профілем/репо | **нуль** repo-іменників у ядрі; говорить портами (DR1) |
| **profile / adapter** | прив'язка engine до конкретного продукту | єдине місце домену; декоратор, не форк (DR5) |
| **shim** | альтернативні тригери → делегування в engine+profile | **не повторює** механіку (інакше 2-й SSOT, DR6) |
| **connector** | експонувати платформу назовні (MCP/протокол) | ядро generic; домен — в adapter/manifest; I/O, не мозок (S3) |
| **leaf** | самодостатня дія без engine під низом | тригери + safety; не дублюй наявний primitive (grep спершу) |

## Правила (governance)

1. **Спершу неймспейс, потім тип.** Новий скіл декларує і те, й те (у цьому індексі).
2. **Не форкай engine.** Потрібна варіація → новий **profile/adapter** або **routine**, не копія рушія.
3. **Один SSOT механіки.** shim/connector **посилаються** на контракт, не переписують його.
4. **Контракт окремо від статусу.** Контракт портів живе в engine/концепті; статус заповненості — у профілі/adapter.
5. **Реєструй тут.** Новий скіл без рядка в цьому індексі — як артефакт без паспорта (C1): баг.
