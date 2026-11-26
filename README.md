# Whisper Free — Speech-to-Text com IA Local

[![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.12-blue?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-221%20passing-brightgreen)](#testes)
[![GPU](https://img.shields.io/badge/GPU-RTX%203060%20optimized-76b900?logo=nvidia)](https://nvidia.com)

Aplicação desktop **Windows** para ditado por voz com correção gramatical/ortográfica via IA **100% local**. Otimizada para **RTX 3060 12GB**, mas funciona também em CPU (mais lenta) graças ao fallback automático.

> Transcrição local com `faster-whisper` (CTranslate2), correção pt-BR com LanguageTool e injeção de texto no campo focado — sem enviar áudio ou texto para a nuvem.

---

## ✨ Funcionalidades Principais

| Feature | Descrição |
|---------|-----------|
| 🎙️ **Push-to-talk global** | `Ctrl+Shift+Espaço` (configurável) — funciona na maioria das janelas |
| ☁️ **Transcrição via API OpenAI** | `Ctrl+Alt+Espaço` para textos mais elaborados; chave/modelo configuráveis no tray |
| ⚡ **Transcrição rápida** | `faster-whisper` + CUDA `int8_float16`; carrega no atalho e libera a VRAM ao terminar |
| 📝 **Correção pt-BR** | LanguageTool local (Java 17+; JRE portátil opcional) |
| 🎨 **Overlay compacto** | Pílula escura `216×44` na parte inferior da tela, com waveform, cronômetro e badges |
| 🔧 **Inicialização com Windows** | Registro `HKCU\Run` — opcional, controlado pelo tray ou CLI |
| 🖱️ **Injeção universal** | Clipboard + `Ctrl+V` por padrão; fallback para `SendInput` Unicode |
| 💤 **GPU sob demanda** | Carrega automaticamente no atalho e descarrega ao fim de cada ditado |
| 🛟 **Fallbacks** | CUDA → CPU e clipboard → digitação direta |
| 📦 **Portable / Instalável** | PyInstaller one-file ou Inno Setup |

---

## 🖥️ Requisitos de Sistema

| Componente | Mínimo | Recomendado |
|------------|--------|-------------|
| **OS** | Windows 10 1909+ | Windows 11 22H2+ |
| **GPU** | Opcional (CPU funciona) | NVIDIA 8 GB+ / **RTX 3060 12 GB** |
| **RAM** | 8 GB | 16 GB+ |
| **CPU** | 4 cores (AVX2) | 8+ cores |
| **Disco** | 6 GB livres (modelos + runtime CUDA + JRE) | SSD NVMe |
| **Python (dev)** | 3.11 | 3.12 |
| **CUDA (opcional)** | 12.x (para GPU) | 12.4+ |

> ⚠️ **CUDA**: o extra `[gpu]` instala cuBLAS/cuDNN 12 via wheels da NVIDIA — não é preciso instalar o CUDA Toolkit no sistema. Se as DLLs faltarem, o app cai automaticamente para CPU/`int8`.

---

## 🚀 Instalação Rápida

### Opção A — Instalador (usuário final)
```bash
# Baixe o instalador mais recente do GitHub Releases e execute.
# O auto-start usa HKCU\Run (não exige privilégios de administrador).
```

### Opção B — Código-fonte (desenvolvimento)
```bash
git clone https://github.com/thierry-moreira/Whisper.git
cd Whisper

# 1. Ambiente virtual (Python 3.11 ou 3.12)
py -3.12 -m venv .venv

# 2. Instale o pacote, as dependências de desenvolvimento e o runtime CUDA
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[gpu,dev]"

# 3. Verifique o ambiente
.venv\Scripts\python -m whisper_free --check

# 4. Execute
.venv\Scripts\python -m whisper_free
```

Atalho equivalente (instala no `.venv`):
```bash
.venv\Scripts\python scripts\install.py --dev
```

Os modelos Whisper são baixados automaticamente no primeiro uso. Para pré-baixar:
```bash
.venv\Scripts\python scripts/download_models.py
```

---

## ⌨️ Como Usar

1. **Inicie a aplicação** — o ícone 🎤 aparece na *system tray*.
2. **Segure `Ctrl+Shift+Espaço`** — a pílula inferior mostra **"Ouvindo"**, waveform e cronômetro.
3. **Fale naturalmente** — solte a tecla para transcrever.
4. **Aguarde** — o overlay mostra **"Processando…"** e depois um check verde com o texto inserido no campo ativo.

### Atalhos Padrão
| Ação | Tecla |
|------|-------|
| Gravar (hold) | `Ctrl+Shift+Espaço` |
| Gravar via API OpenAI (hold) | `Ctrl+Alt+Espaço` |
| Ativar/Desativar app | `Ctrl+Shift+F12` |
| Configurações / logs | Menu do tray |

---

## ⚙️ Configuração (`.env`)

Copie `.env.example` para `.env`. O prefixo é **`WHISPER_FREE_`** e o separador de seções é **`__`** (duplo underscore):

```ini
# --- Modelo Whisper ---
WHISPER_FREE_WHISPER__MODEL_SIZE=large-v3-turbo   # tiny | base | small | medium | large-v3 | large-v3-turbo | distil-large-v3
WHISPER_FREE_WHISPER__DEVICE=cuda                 # cuda | cpu | auto
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8_float16   # int8_float16 | float16 | int8 | float32 | auto
WHISPER_FREE_WHISPER__LANGUAGE=pt                 # vazio = detecção automática
WHISPER_FREE_WHISPER__FALLBACK_TO_CPU=true
WHISPER_FREE_WHISPER__UNLOAD_AFTER_USE=true       # libera a VRAM ao fim de cada ditado
WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS=60      # usado só se UNLOAD_AFTER_USE=false

# --- Áudio ---
WHISPER_FREE_AUDIO__SAMPLE_RATE=16000
WHISPER_FREE_AUDIO__CHANNELS=1
WHISPER_FREE_AUDIO__BLOCKSIZE=1024
WHISPER_FREE_AUDIO__DEVICE=                        # índice ou trecho do nome; vazio = padrão

# --- Hotkeys ---
WHISPER_FREE_HOTKEY__MODE=hold                     # hold | toggle
WHISPER_FREE_HOTKEY__TRIGGER=ctrl+shift+space
WHISPER_FREE_HOTKEY__CLOUD_TRIGGER=ctrl+alt+space
WHISPER_FREE_HOTKEY__TOGGLE_ENABLED=ctrl+shift+f12
WHISPER_FREE_HOTKEY__SUPPRESS=true

# --- Gramática ---
WHISPER_FREE_GRAMMAR__ENABLED=true
WHISPER_FREE_GRAMMAR__LANGUAGE=pt-BR

# --- Injeção ---
WHISPER_FREE_INJECTOR__MODE=paste                  # paste | type
WHISPER_FREE_INJECTOR__RESTORE_CLIPBOARD=true
WHISPER_FREE_INJECTOR__FALLBACK_TO_TYPE=true

# --- Overlay ---
WHISPER_FREE_OVERLAY__ENABLED=true
WHISPER_FREE_OVERLAY__POSITION=bottom-center       # top-center | center | bottom-center | mouse
WHISPER_FREE_OVERLAY__ALWAYS_SHOW_ON_SUCCESS_MS=1200

# --- Inicialização / logs ---
WHISPER_FREE_STARTUP__AUTO_START=false
WHISPER_FREE_LOG_LEVEL=INFO

# --- OpenAI (segundo atalho) ---
WHISPER_FREE_OPENAI__API_KEY=
WHISPER_FREE_OPENAI__MODEL=gpt-4o-transcribe                        # DEBUG | INFO | WARNING | ERROR
```

A lista completa está em [docs/reference/env-vars.md](docs/reference/env-vars.md).

---

## 🏗️ Arquitetura

```
src/whisper_free/
├── config/          # Pydantic Settings + constantes
├── core/            # Controller (state machine), GPUManager, states
├── audio/           # AudioCapture (sounddevice), AudioBuffer
├── transcription/   # WhisperEngine, GrammarCorrector, Pipeline, JavaRuntime
├── ui/              # OverlayWindow (tkinter Canvas), TrayIcon (pystray)
├── input/           # HotkeyManager (keyboard), TextInjector (ctypes/pyperclip)
├── startup/         # WindowsStartup (Registry Run key)
├── utils/           # Logging (loguru), helpers
└── main.py          # CLI, bootstrap, single instance, --check/--warmup
```

### Fluxo de Dados (hold mode)

```
[Hotkey Press] → LISTENING → [AudioCapture] → [AudioBuffer]
                                              ↓
[Hotkey Release] → PROCESSING → [worker] Whisper → Grammar → cleanup
                                              ↓
                         INJECTING → [TextInjector] → IDLE
```

- O pipeline é **síncrono** e roda em um único `ThreadPoolExecutor(max_workers=1)`.
- A UI usa **tkinter** (overlay) e **pystray** (tray); não há PyQt6 nem asyncio.
- Cada ditado recebe um **token de geração**; se o assistente for desativado durante `PROCESSING`, o resultado é descartado em vez de injetado.

---

## 🧪 Testes

```bash
# Suite padrão (integração/GPU são excluídas via addopts)
.venv\Scripts\python -m pytest -v

# Cobertura
.venv\Scripts\python -m pytest --cov=whisper_free --cov-report=term-missing

# Testes que tocam o desktop real (SendInput)
.venv\Scripts\python -m pytest -m integration -v

# Apenas GPU (se houver marcados)
.venv\Scripts\python -m pytest -m gpu -v
```

**Métricas atuais:**
- ✅ **221 testes passando**, 2 deselected (integração)
- 📊 Cobertura global **~64%**; núcleo (controller, pipeline, GPU, injector, hotkey, OpenAI) **84–94%**
- ⏱️ Execução < 2 s

> A cobertura global é menor porque `main.py`, `ui/` e `audio/capture.py` dependem de APIs do Windows/Tk e são exercitados manualmente ou por testes de integração.

---

## 📦 Build / Distribuição

### Portable (PyInstaller)
```bash
.venv\Scripts\python -m pip install pyinstaller
.venv\Scripts\pyinstaller --clean --noconfirm build/whisper_free.spec
# Gera: dist/WhisperFree.exe
```

### Instalador (Inno Setup)
```bash
iscc build/whisper_free.iss
# Gera: dist/WhisperFree-Setup-0.1.0.exe
```

Os ícones podem ser regenerados com:
```bash
.venv\Scripts\python scripts/make_icon.py
```

---

## 🛠️ Desenvolvimento

```bash
# Formatação + lint
.venv\Scripts\ruff check --fix src tests scripts
.venv\Scripts\black src tests scripts

# Type checking
.venv\Scripts\mypy src

# Pre-commit hooks (ruff + black + checks básicos)
.venv\Scripts\pre-commit install
```

O CI roda em `windows-latest` com Python 3.11 e 3.12: Ruff, Black, MyPy e pytest com cobertura.

---

## 📋 Roadmap

- [x] Core STT + Grammar pipeline
- [x] Overlay + Tray + Hotkeys + Startup
- [x] Fallbacks CUDA→CPU e paste→type
- [x] Testes unitários (221) + CI
- [x] Transcrição via API OpenAI (segundo atalho)
- [ ] Janela de configurações
- [ ] Auto-update (GitHub Releases)
- [ ] Multi-idioma (UI + modelos)
- [ ] Plugins / Webhooks

---

## 🤝 Contribuindo

1. Fork → `feature/minha-feature`
2. `pre-commit run --all-files`
3. `pytest` passa
4. PR com descrição clara + screenshots se UI

---

## 📄 Licença

MIT — veja [LICENSE](LICENSE).  
Modelos Whisper: licença MIT (OpenAI).  
LanguageTool: LGPL 2.1+.

---

## 🙏 Agradecimentos

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — CTranslate2 bindings
- [LanguageTool](https://languagetool.org/) — Gramática open-source
- [Eclipse Temurin](https://adoptium.net/) — JRE portátil
- [zzanehip/The-Old-Reader-Whisper](https://github.com/zzanehip/The-Old-Reader-Whisper) — Inspiração UX

---

**Feito com ❤️ para a comunidade PT-BR que valoriza privacidade e performance local.**
