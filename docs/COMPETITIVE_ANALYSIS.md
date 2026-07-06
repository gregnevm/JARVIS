# Конкурентний аналіз: JARVIS vs відкриті аналоги (липень 2026)

> Власне дослідження, липень 2026. Метод: фактчек стану цього репо по коду/доках +
> multi-source веб-розвідка з адверсарною верифікацією тверджень (первинні джерела:
> репозиторії, доки, release notes). Стан JARVIS описано **чесно по коду**, не по
> аспіраційній лексиці аудиту з `ARCHITECTURE_OPTIMIZATION_PLAN.md`.
>
> Роль документа: аналіз (як `GAP_ANALYSIS.md`). Без статусів і чекбоксів — висновки
> конвертуються в задачі трек-roadmap-ів окремими PR.

---

## 1. Карта поля

**Однойменні «Jarvis»-проєкти (найближчі концептуально):**

| Проєкт | Суть | Стан (07.2026) |
|---|---|---|
| [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) (Stanford, Hazy Research / Scaling Intelligence Lab) | Local-first фреймворк «Personal AI on personal devices»: композовані шари, Ollama/vLLM/SGLang/llama.cpp, скіли за стандартом agentskills.io (~150 з Hermes, ~13,7k з OpenClaw), 8 вбудованих агентів, learning loop на локальних трейсах, eval з energy/FLOPs/cost як first-class метриками | Активний, академічний бекінг |
| [vierisid/jarvis](https://github.com/vierisid/jarvis) | Always-on демон: бачить екран, діє в межах authority limits; soft-gate approvals через chat/Telegram/Discord, повний аудит-трейл, emergency pause/kill, **consecutive-approval learning** (сам пропонує auto-approve правила); сервер 24/7 + sidecars на інших машинах | Активний, продуктизований |
| [isair/jarvis](https://github.com/isair/jarvis) | 100% локальний голосовий асистент: читає екран, керує Chrome, необмежені MCP без context rot, авторедакція чутливих даних перед записом на диск. macOS/**Windows**/Linux (не macOS-only) | Активний |
| [ethanplusai/jarvis](https://github.com/ethanplusai/jarvis) | Voice-first macOS: Claude + Fish Audio TTS, AppleScript-мости, спавнить Claude Code сесії; памʼять SQLite FTS5 | Активний, нішевий |

**Персональні асистенти-платформи:**

| Проєкт | Суть | Чому важливий |
|---|---|---|
| [QwenPaw](https://github.com/agentscope-ai/QwenPaw) (AgentScope) | Personal AI assistant: kernel-level sandbox за замовчуванням (Seatbelt/Bubblewrap+Landlock/AppContainer), Tool Guard (YAML rule engine проти injection/traversal/reverse shell), File Guard, Skill Scanner, approval-рівні STRICT/SMART/AUTO/OFF, Tauri-інсталери, мульти-чат-канали | **Еталон security-обвʼязки** для персонального демона |
| [Khoj](https://github.com/khoj-ai/khoj) (34k⭐, YC W24) | Self-hosted «другий мозок»: RAG, кастомні агенти, автоматизації за розкладом, deep research | Бенчмарк тракшену; стек майже наш (FastAPI+pgvector+Ollama), але без OS-control |
| [Leon AI](https://github.com/leon-ai/leon) | Ветеран self-hosted асистентів, tiered memory у нових версіях | Довгожитель ніші |
| [Agent Zero](https://github.com/agent0ai/agent-zero), AnythingLLM, LocalAGI | Self-hosted агент-фреймворки загального призначення | Фон поля |
| Home Assistant voice/LLM stack | Локальний голос + LLM-інтеграції поверх smart-home | Найбільша інсталяційна база local-first асистентів |

**Агенти-виконавці та computer-use:**

| Проєкт | Суть | Чому важливий |
|---|---|---|
| [OpenHands](https://github.com/OpenHands/openhands) (~74k⭐, $18.8M Series A) | Автономний coding-агент: CodeAct loop, 72% SWE-bench Verified (зі Claude Sonnet 4.5; 32% на відкритих моделях), LiteLLM 100+ провайдерів, Docker-sandbox як базлайн, Planning Mode | Еталон eval-дисципліни й sandbox-базлайну |
| [Open Interpreter](https://github.com/openinterpreter/open-interpreter) (Rust-rewrite) | Локальний code-exec агент: **native sandbox за замовчуванням** (fail-closed: «краще впасти, ніж мовчки виконати поза пісочницею»), approval-політики untrusted/on-request/never | Еталон fail-closed exec |
| [UI-TARS](https://github.com/bytedance/UI-TARS-desktop) (ByteDance, 32k⭐) | Pure-vision GUI-агент: скріншот → дія, без DOM/accessibility | Сильна ланка для «сирих» UI без UIA |
| [Agent S](https://github.com/simular-ai/Agent-S) | Agentic framework «uses computers like a human» | Дослідницький фронт computer-use |
| [Letta](https://docs.letta.com/letta-agent/memory) (ex-MemGPT) | Агент-памʼять: MemFS (git-backed markdown памʼять з історією комітів), sleep-time compute (фоновий агент консолідує памʼять між сесіями, memory-subагенти в git worktrees) | **Еталон памʼяті** |
| [Mem0](https://mem0.ai/blog/state-of-ai-agent-memory-2026) | Memory-шар: salience extraction (дистиляція фактів із діалогу замість збереження сирих транскриптів) | Еталон дистиляції памʼяті |

---

## 2. Порівняльна матриця (чесний стан JARVIS)

| Вісь | **JARVIS (по коду)** | OpenJarvis | QwenPaw | vierisid/jarvis | OpenHands | Letta |
|---|---|---|---|---|---|---|
| Провайдери LLM | Свій `LLMInterface` (Ollama/Kobold); хмара не підключена (S1 opt-in) | 4+ движки нативно | Qwen + локальні | Кілька | LiteLLM 100+ | Будь-який |
| Скіли/плагіни | Свій формат (`data/skills/`), без стандарту | **agentskills.io**, ~13,7k імпорт | SKILL.md + **Skill Scanner** | Ноди воркфлоу | Marketplace | Tools |
| Памʼять | pgvector 768D HNSW + Context Passport (P9/P10) — один шар | memory index | сесійна | персона | repo-контекст | **3 tier + MemFS + sleep-time** |
| Authority/HITL | confirm/double-confirm, blast_radius fail-closed, T0–T4 | політики агентів | **STRICT/SMART/AUTO/OFF** + Tool Guard | soft-gate + **auto-approve learning** + kill switch | sandbox-договір | — |
| Sandbox exec | `subprocess -I`, default-off; **не sandbox** (визнано в guardrails) | частково | **kernel-level за замовчуванням** | container | Docker-базлайн | — |
| Computer-use | hostagent: PowerShell/UIA/screen, драбина T0–T4, C0–C5 done | тули | — | екран + міжмашинні дії | shell/браузер | — |
| Evals | `training/eval/`: формат/стиль, gate ≥0.85; **без task-success** | **energy/FLOPs/cost first-class** | pre-commit CI | — | **SWE-bench 72%** | LongMemEval-сумісна |
| Персоналізація | LoRA-пайплайн (Unsloth/RunPod), human-gated (ADR-007/008); ще не автономний | **learning loop на локальних трейсах** | — | персона-памʼять | — | sleep-time консолідація |
| Пакування | docker-compose + PS-інсталери + APK | Tauri + CLI | **Tauri setup.exe zero-config** | managed hosting | Docker/K8s | Cloud+self-host |
| Мульти-нод | Twin (сервер) + hostagent (Windows) + Edge (USB) + APK + Telegram | desktop+backend | чат-канали | **сервер 24/7 + sidecars** | Agent Server | — |

**Висновок з матриці.** Архітектурна форма JARVIS (local-first демон + tier-драбина
computer-use + HITL + мульти-нод) — це **конвергентний мейнстрім 2026**, не унікальність.
Реальні відмінності JARVIS: Context Passport культура (P9/P10/C1), OKR-автопілот kaizen,
три-стовпова амбіція (API-платформа + coding agent + клієнти), Telegram-first. Реальні
відставання: sandbox, рівнева памʼять, task-success eval, стандарт скілів.

---

## 3. Best practices по осях

### 3.1 Провайдери LLM і роутинг
**Best-in-class:** first-class локальні бекенди + opt-in хмара (OpenJarvis: Ollama/vLLM/
SGLang/llama.cpp за одним інтерфейсом; OpenHands: LiteLLM для 100+ провайдерів).
**Для JARVIS:** свій `LLMInterface` — правильний вибір за наших guardrails (заборона
framework-переписувань). Прогалина не «LiteLLM відсутній», а **жодного хмарного адаптера
взагалі**: cascade (`routing/cascade.py`) — regex-класифікатор без цінового/якісного
роутингу. Паттерн для адаптації: один `CloudAdapter` за нашим же `LLMInterface`, за
прапором, вимкнений за замовчуванням (S1 не порушується) — без залежності від LiteLLM.

### 3.2 Скіли та стандарти
**Best-in-class:** [SKILL.md / agentskills.io](https://agentskills.io/home) — відкритий
стандарт Anthropic, 32 адоптери (Microsoft, OpenAI, Google, Cursor…); OpenJarvis імпортує
~13,7k community-скілів. **Security-практика:** QwenPaw Skill Scanner — сканування скіла
*до активації* (block/warn/off + whitelist).
**Для JARVIS:** `data/skills/*` вже структурно близькі до SKILL.md. Конверсія у
стандарт = безкоштовна екосистема + переносимість. Pre-activation скан — маленький крок
поверх наявного blast_radius.

### 3.3 Памʼять
**Best-in-class:** усі лідери пішли від плаского vector-RAG до **3 рівнів**: (1) закріплений
робочий контекст (pinned core blocks), (2) дослівний архів, (3) дистильоване знання.
[Letta MemFS](https://docs.letta.com/letta-code/memfs): git-backed markdown-памʼять
(кожна правка — коміт, memory-subагенти в worktrees);
[sleep-time compute](https://www.letta.com/blog/sleep-time-compute/): фонова консолідація
між сесіями (~5x менше test-time compute, ~2.5x менша вартість запиту). Mem0: salience
extraction замість сирих транскриптів.
**Для JARVIS:** Context Passport — це вже рівень (3) у зародку. Бракує: pinned-блоки
(рівень 1) і фоновий consolidation-job (наш `context_retention` bg-job — природне місце
для «sleep-time» дистиляції). Це еволюція Context GC v2, не переписування.

### 3.4 Автономія та authority
**Best-in-class:** іменовані градуйовані драбини затвердження — QwenPaw
STRICT/SMART/AUTO/OFF; Open Interpreter untrusted/on-request/never (default on-request);
vierisid: soft-gate + мультиканальна доставка затверджень + **consecutive-approval
learning** (система сама пропонує auto-approve правило після N однакових ручних
підтверджень) + повний аудит-трейл + emergency kill.
**Для JARVIS:** confirm/double-confirm + T0–T4 + blast_radius — правильні інгредієнти,
але не зведені в одну іменовану політику. Паттерн: єдиний approval-policy рівень у конфіг
(fail-closed default), і consecutive-approval learning поверх наявного `computer.jsonl`
аудит-логу — лог уже містить усі дані для цього.

### 3.5 Sandbox виконання
**Best-in-class 2026 — зсув від opt-in Docker до OS-native sandbox за замовчуванням:**
QwenPaw — Seatbelt (macOS) / Bubblewrap+Landlock (Linux) / AppContainer (Windows) + Tool
Guard (YAML-правила проти command injection / path traversal / reverse shell, перевірка
*кожного* tool call до виконання) + File Guard (`~/.ssh` тощо заблоковані за
замовчуванням). Open Interpreter (Rust): native sandbox, **fail-closed** («впасти, а не
мовчки виконати без пісочниці»). OpenHands: Docker як базлайн і явне попередження, що
без нього агент має повний доступ до ФС.
**Для JARVIS:** найкритичніша прогалина (визнана в guardrails). Мінімальний крок:
`bwrap` навколо code-exec у tools-контейнері (він Linux) + YAML pre-exec guard. hostagent
(Windows-хост) — окрема історія: там межа — whitelists+confirm; AppContainer — дальній
орієнтир.

### 3.6 Computer-use
**Best-in-class:** гібридна драбина. Structured-first (accessibility/DOM/CLI) — швидше,
дешевше, **безпечніше** (у хмарну модель іде структурований текст, не скріншоти); pure
vision ([UI-TARS](https://arxiv.org/html/2501.12326v1)) — фолбек для UI без automation-API
(на Windows підтримка UIA нерівна між фреймворками).
**Для JARVIS:** наша драбина T0 (PowerShell) → T1 (DOM) → T2 (UIA) → T4 (pixel/vision) —
**це і є best practice**; підтверджено зовнішнім полем. Тримати vision останнім щаблем
(C6) і, коли дійде черга, дивитись на UI-TARS-1.5-7B як локальну vision-модель.

### 3.7 Evals
**Best-in-class:** task-success з перевіркою кінцевого стану середовища —
[Terminal-Bench 2.0](https://www.tbench.ai/) (ізольовані Docker-таски, є категорія
«personal assistant»); для памʼяті —
[LongMemEval](https://github.com/xiaowu0162/longmemeval) (6 типів питань: recall /
knowledge update / temporal reasoning / multi-session…); для персоналізації —
[MyPCBench](https://arxiv.org/html/2606.16748); OpenJarvis міряє energy/FLOPs/cost/latency
нарівні з accuracy.
**Для JARVIS:** наш eval міряє формат/стиль (чесно визнано в DESIGN §9.3) — LoRA-gate
≥0.85 промоутить *стиль*, не *користь*. Паттерн: ~20 власних task-success сценаріїв
(Telegram-команда → перевірка кінцевого стану: файл створено, паспорт записано, процес
дійшов до terminal-степу) + LongMemEval-подібні питання поверх `context_events` + колонки
cost/latency. Це якорить і kaizen-автопілот, і LoRA-промоушен.

### 3.8 Персоналізація
**Best-in-class:** OpenJarvis — learning loop на локальних трейсах як заявлена мета
фреймворку; Letta — sleep-time агенти, що вчаться між сесіями.
**Для JARVIS:** наш LoRA-пайплайн (ShareGPT-експорт кращих діалогів, human-gated
кураторство ADR-008, RunPod cloud-burst ADR-007) — архітектурно на рівні поля і навіть
попереду більшості (мало хто реально файнтюнить). Слабка ланка — не пайплайн, а
**eval-гейт** (див. 3.7): промоушен адаптера має залежати від task-success, інакше
петля самовдосконалення оптимізує не те.

### 3.9 Пакування та self-hosting DX
**Best-in-class:** QwenPaw — Tauri `setup.exe` zero-config (без Python/env для юзера);
docker-compose-стартер-кіти як норма ніші.
**Для JARVIS:** compose + `Install-JARVIS.ps1`/`FirstSetup` — адекватно для
single-operator. Дешеве запозичення: `doctor`-команда (діагностика env/портів/моделей
одним запуском) поверх наявних `scripts/lib/*` перевірок. Tauri — тільки якщо колись
зʼявиться зовнішній adoption-трек.

### 3.10 Мульти-нод топології
**Best-in-class:** vierisid — сервер 24/7 + легкі sidecars на робочих машинах, з
per-node authority і крос-нодовим аудитом.
**Для JARVIS:** Twin+hostagent+Edge+APK — та сама топологія. Прогалина: authority
зараз глобальна (admin/user), не **per-node**; крос-нодові дії (Twin→hostagent) варто
маркувати в аудит-паспортах як окремий клас.

---

## 4. Шортлист до адаптації (пріоритезовано, під наші guardrails)

Усі пункти інкрементальні: без framework-rewrite (заборонено AGENTS.md), зовнішні API
лишаються opt-in (S1), кожен — за прапором із безпечним дефолтом.

| # | Практика | Джерело паттерну | Зусилля | Куди в репо |
|---|---|---|---|---|
| 1 | **bwrap+Landlock навколо code-exec** + YAML pre-exec guard (injection/traversal) | QwenPaw, Open Interpreter (fail-closed) | S–M | tools-контейнер; закриває guardrail-борг «subprocess -I не sandbox» |
| 2 | **Іменована approval-драбина** (STRICT/SMART/AUTO/OFF) поверх confirm/double-confirm + consecutive-approval learning з `computer.jsonl` | QwenPaw, vierisid | S | `jarvis_core/safety/`, конфіг-рівень |
| 3 | **Памʼять у 3 рівні**: pinned-блоки + sleep-time консолідація в `context_retention` bg-job (Mem0-style salience → паспорти) | Letta, Mem0 | M | еволюція Context GC v2 (AO-план) |
| 4 | **Task-success eval**: ~20 сценаріїв end-state + LongMemEval-подібні memory-питання + cost/latency; підключити як гейт kaizen і LoRA-промоушену | Terminal-Bench, LongMemEval, OpenJarvis | M | `training/eval/` розширення |
| 5 | **SKILL.md-формат** для `data/skills/*` + pre-activation Skill Scanner | agentskills.io, QwenPaw | S | сумісність з екосистемою ~13,7k скілів |
| 6 | (опц.) `doctor`-команда; CloudAdapter за прапором; per-node authority | QwenPaw; OpenHands; vierisid | S / S / M | scripts / llm/adapters / safety |

**Стратегічна рамка.** Generic-шар «sovereign AI daemon» комодитизований (Stanford,
ByteDance, AgentScope, YC- і VC-funded команди). Виграшна позиція для solo-dev: не
конкурувати шаром, а (а) підтягнути 4 системні відставання зі шортлиста до рівня поля
малими кроками, (б) диференціюватись тим, чого поле не має: Context Passport культура,
OKR-автопілот, персональний LoRA-цикл із чесним task-success гейтом — і доменні скіли
під власні операції (яких у відкритому полі нема, але їх ще треба збудувати).

---

## 5. Джерела

Первинні: [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) ·
[Stanford blog](https://scalingintelligence.stanford.edu/blogs/openjarvis/) ·
[QwenPaw](https://github.com/agentscope-ai/QwenPaw) ·
[vierisid/jarvis](https://github.com/vierisid/jarvis) ·
[isair/jarvis](https://github.com/isair/jarvis) ·
[ethanplusai/jarvis](https://github.com/ethanplusai/jarvis) ·
[Khoj](https://github.com/khoj-ai/khoj) ·
[OpenHands](https://github.com/OpenHands/openhands) ·
[Open Interpreter](https://github.com/openinterpreter/open-interpreter) ·
[UI-TARS](https://github.com/bytedance/UI-TARS-desktop) ·
[Letta MemFS](https://docs.letta.com/letta-code/memfs) ·
[Letta sleep-time](https://www.letta.com/blog/sleep-time-compute/) ·
[agentskills.io](https://agentskills.io/home) ·
[LongMemEval](https://github.com/xiaowu0162/longmemeval) ·
[Terminal-Bench](https://www.tbench.ai/) ·
[MyPCBench](https://arxiv.org/html/2606.16748).
Вторинні: [MarkTechPost про OpenJarvis](https://www.marktechpost.com/2026/06/03/meet-openjarvis-a-local-first-framework-for-on-device-personal-ai-agents-with-tools-memory-and-learning/) ·
[AgentMarketCap про OpenHands Series A](https://agentmarketcap.ai/blog/2026/04/06/openhands-open-source-coding-agent-allhands-ai-series-a-swe-bench) ·
[Anthropic Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) ·
[Mem0 State of Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026) ·
[Fazm: computer-use agents on Windows](https://fazm.ai/blog/best-open-source-computer-use-agent-windows-2026).
