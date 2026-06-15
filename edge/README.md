# PortableAI Edge (USB layout template — DESIGN §10)

## Структура

```
edge/
├── models/          # qwen2.5-7b-instruct-q4_k_m.gguf (не в git)
├── engines/win|linux/
├── lora/active/     # symlink → versioned/
├── data/            # context_log.jsonl, rag.db, sync_state.json
├── personas/
├── config.yaml
├── run_win.bat
├── run_linux.sh
├── edge_sync.py
├── edge_chat.py
└── rag.py
```

## Швидкий старт (dev з репо)

1. KoboldCPP на `:5001` з GGUF моделлю.
2. Twin SyncServer: `docker compose up -d twin`
3. `copy config.yaml.example config.yaml` — вкажи `twin_url`.
4. Sync один раз: `python edge/edge_sync.py --once`
5. Чат: `python edge/edge_chat.py`

## RAG (офлайн)

```python
from edge.rag import EdgeRAG
rag = EdgeRAG("edge/data/rag.db")
rag.store("JARVIS — персональний AI на USB")
print(rag.search("USB AI"))
```

На LAN можна передати `embed_fn` що викликає Twin Memory `/embed`.

## Залежності

```bash
pip install httpx pyyaml
```

`edge_chat.py` / `edge_sync.py` додають корінь репо в `PYTHONPATH` для `jarvis_core`.
