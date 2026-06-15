"""Конфігурація Tools service (інструменти + агент-луп)."""
from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Ollama (на ХОСТІ) + дві моделі
    ollama_host: str = "http://host.docker.internal:11434"
    ollama_model_chat: str = "gemma3:4b"
    ollama_model_agent: str = "qwen2.5:7b-instruct"
    # LLM_BACKEND=kobold — chat через KoboldAdapter (Edge/Twin CPU inference).
    llm_backend: Literal["ollama", "kobold"] = "ollama"
    kobold_host: str = "http://host.docker.internal:5001"
    # Vision-модель для розпізнавання зображень (напр. "llava:7b", "qwen2.5vl:7b").
    # Порожньо = describe_image вимкнено.
    ollama_model_vision: str = ""
    # C6.1: перед describe_image/see_screen вивантажити chat+agent з VRAM; vision keep_alive=0.
    ollama_vision_on_demand: bool = False

    # Генерація зображень (опційно):
    #   pollinations — IMAGE_GEN_URL=pollinations (хмара, без ключа; Windows OK)
    #   ollama — IMAGE_GEN_URL=ollama + IMAGE_GEN_MODEL (лише macOS поки що)
    #   Forge/A1111 — http://host.docker.internal:7860
    #   OpenAI-сумісний — http://.../v1 + IMAGE_GEN_MODEL
    # Порожній URL і модель = generate_image вимкнено.
    image_gen_url: str = ""
    image_gen_model: str = ""  # модель Ollama-image / dall-e-3 тощо
    image_gen_timeout: float = 180.0
    # Stable Horde (IMAGE_GEN_URL=horde). Анонім: 0000000000; краще ключ з aihorde.net
    horde_api_key: str = "0000000000"
    # Режим: hybrid (евристика) | chat (завжди CHAT без тулів) | agent (завжди тул-луп)
    agent_mode: str = "hybrid"

    # Сусідні сервіси
    memory_url: str = "http://memory:8100"
    twin_url: str = "http://twin:8765"
    # Redis — спільний із gateway: tool set_reminder пише у ZSET, gateway-поллер шле.
    redis_url: str = "redis://redis:6379/0"

    # Шлях до даних (персональні нотатки тощо) — том ./data:/data у compose.
    data_dir: str = "/data"

    # Безпека / ліміти
    enable_code_exec: bool = False
    # Telegram ID з доступом до Computer Use (скріншот, PS, FS). Порожньо → ADMIN → ALLOWED (.env).
    computer_owner_user_ids: str = ""
    # Режим computer лише для ADMIN_USER_IDS (застарілий прапор; краще COMPUTER_OWNER_USER_IDS).
    computer_mode_admins_only: bool = False
    allowed_user_ids: str = ""
    admin_user_ids: str = ""
    # Computer Use — керування Windows-хостом через host-agent (поза Docker).
    enable_computer_use: bool = False
    computer_allow_admin: bool = False
    hostagent_url: str = "http://host.docker.internal:8400"
    hostagent_token: str = ""
    ps_whitelist: str = ""
    cli_whitelist: str = ""
    computer_timeout: float = 30.0
    computer_require_confirm: bool = True
    # Після ✅ додати cmdlet/exe у data/computer_learned.json; повтор — без підтвердження.
    computer_auto_learn_whitelist: bool = True
    computer_auto_trust_learned: bool = True
    enable_browser: bool = False
    # Мутуючі computer-дії на user_id за годину; 0 = без ліміту.
    computer_rate_limit_per_hour: int = 120
    computer_auto_vision: bool = True
    computer_allow_power: bool = False
    hostagent_drop_dir: str = ""
    remote_file_max_bytes: int = 48 * 1024 * 1024
    http_timeout: float = 20.0          # web_fetch / web_search
    ollama_timeout: float = 180.0       # CPU-інференс може бути повільним
    max_agent_iters: int = 5            # стеля ітерацій тул-лупа
    computer_max_iters: int = 12        # окремо для AGENT_MODE=computer (багатокрокові задачі)
    # safe | standard | full — які tier computer-tools доступні (див. computer_profile.py).
    computer_profile: str = "safe"
    # Після ✅ — session trust: без confirm для T0/T1 (хв; 0 = вимкнено). cmp:YT = full trust.
    computer_session_trust_minutes: int = 10
    fetch_max_chars: int = 6000         # обрізаємо сторінку, щоб не рознести контекст
    code_exec_timeout: float = 8.0
    # Circuit breaker Ollama: N підряд помилок → пауза cooldown секунд (fail-fast).
    ollama_fail_threshold: int = 3
    ollama_cooldown: float = 60.0
    # D.4: retrain коли +N кураційних turns після останнього export (0 = вимкнено).
    train_retrain_min_curated: int = 200

    # P4 Deep Research
    research_max_hops: int = 3
    research_max_urls: int = 5
    research_max_chars: int = 40000

    # P5 MCP Gateway — JSON array of {name, command, args, env?}
    mcp_servers_json: str = ""

    # P6 Connectors (integration tokens via .env)
    notion_token: str = ""
    notion_database_id: str = ""
    slack_bot_token: str = ""
    slack_default_channel: str = ""
    calendar_ics_url: str = ""

    # P7 Skills
    skills_max_chars: int = 4000

    # P8 Subagents
    subagent_default_budget: int = 3
    subagent_max_budget: int = 8

    # Phase 7.1 Orchestrator + Critic
    orchestrator_enabled: bool = True
    orchestrator_worker_budget: int = 5
    orchestrator_max_revisions: int = 1

    # Phase 7.2 Self-improving loop (judge → human gate → export)
    self_improve_enabled: bool = True
    self_improve_judge_model: str = ""  # порожньо → ollama_model_chat
    self_improve_scan_limit: int = 50

    # P10 Hooks
    hooks_enabled: bool = True

    # LoRA deploy (Phase 3.2): promote/rollback → Ollama live
    lora_deploy_enabled: bool = True
    lora_base_model: str = ""
    lora_ollama_model: str = "jarvis-lora"
    lora_active_dir: str = ""

    # Cursor IDE tasks (Telegram /cursor + tool cursor_task)
    cursor_tasks_enabled: bool = True
    cursor_runtime: str = "local"  # local | cloud
    cursor_api_key: str = ""
    cursor_api_base: str = "https://api.cursor.com"
    cursor_model: str = "composer-2.5"
    cursor_repo_url: str = ""
    cursor_repo_ref: str = "main"
    cursor_auto_create_pr: bool = False
    cursor_host_workspace: str = ""  # O:\JARVIS на хості
    cursor_host_script: str = ""  # O:\JARVIS\scripts\cursor_run_task.py
    cursor_python_exe: str = "python"
    cursor_timeout: float = 900.0
    cursor_fallback_inbox: bool = True

    # Continue.dev — VS Code + local agent API (tool continue_dev, Computer Use mode)
    enable_continue_dev: bool = False
    continue_dev_url: str = "http://host.docker.internal:65432"
    continue_dev_timeout: float = 300.0
    continue_vscode_cli: str = "code"

    # Native coding-agent tools (Стовп B / CODING_AGENT_ROADMAP CA-1.4, CA-2.1, CA-2.2).
    # Read-only repo intelligence (repo_tree/repo_grep/code_read) поверх host-agent FS —
    # рідуть на ENABLE_COMPUTER_USE + owner gate. Дефолт false (нова фіча за прапором).
    enable_coding_tools: bool = False
    # Стелі для repo-інструментів (захист контексту/хоста).
    coding_tree_max_entries: int = 300
    coding_grep_max_results: int = 60
    # CA-3.4 stop-condition: N однакових поспіль fail від run_tests/run_lint → no-progress,
    # агент зупиняє fix-цикл і чесно звітує (замість крутитися до max_agent_iters). 0 = вимкнено.
    coding_no_progress_repeats: int = 2


settings = Settings()
