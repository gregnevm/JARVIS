@echo off
REM JARVIS PortableAI — one-click Edge (Windows)
cd /d %~dp0

if not exist engines\win\koboldcpp.exe (
  echo Place koboldcpp.exe in engines\win\
  echo Download: https://github.com/LostRuins/koboldcpp/releases
  exit /b 1
)
if not exist models\qwen2.5-7b-instruct-q4_k_m.gguf (
  echo Place GGUF model in models\qwen2.5-7b-instruct-q4_k_m.gguf
  exit /b 1
)

set LORA_ARG=
if exist lora\active\jarvis.gguf set LORA_ARG=--lora lora\active\jarvis.gguf

start "" engines\win\koboldcpp.exe ^
  --model models\qwen2.5-7b-instruct-q4_k_m.gguf ^
  %LORA_ARG% ^
  --contextsize 4096 ^
  --threads 8 ^
  --port 5001 ^
  --launch

if not exist config.yaml copy config.yaml.example config.yaml
start "" python edge_sync.py --loop
