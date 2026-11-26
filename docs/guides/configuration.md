# Configuração Avançada

## Arquivo `.env` completo

```ini
# ============================================================
# WHISPER FREE - CONFIGURAÇÃO
# ============================================================
# Copie .env.example para .env e ajuste.
# Variáveis de ambiente reais têm precedência sobre o arquivo.

# ------------------------------------------------------------
# RAIZ / LOGS
# ------------------------------------------------------------
WHISPER_FREE_LOG_LEVEL=INFO
WHISPER_FREE_SINGLE_INSTANCE=true
# WHISPER_FREE_HOME=C:\caminho\para\dados

# ------------------------------------------------------------
# MODELO WHISPER (STT)
# ------------------------------------------------------------
# tiny, base, small, medium, large-v2, large-v3, large-v3-turbo, distil-large-v3
WHISPER_FREE_WHISPER__MODEL_SIZE=large-v3-turbo

# cuda | cpu | auto
WHISPER_FREE_WHISPER__DEVICE=cuda

# int8_float16 | float16 | int8 | float32 | auto
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8_float16

# pt | en | vazio (detecção automática)
WHISPER_FREE_WHISPER__LANGUAGE=pt

WHISPER_FREE_WHISPER__BEAM_SIZE=5
WHISPER_FREE_WHISPER__VAD_FILTER=true
WHISPER_FREE_WHISPER__CONDITION_ON_PREVIOUS_TEXT=false
WHISPER_FREE_WHISPER__CPU_THREADS=0

# Fallback e ciclo de vida do modelo
WHISPER_FREE_WHISPER__FALLBACK_TO_CPU=true
WHISPER_FREE_WHISPER__UNLOAD_AFTER_USE=true
WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS=60

# Cache de modelos (vazio usa <PROJECT_ROOT>/models)
# WHISPER_FREE_WHISPER__MODEL_DIR=D:\models

# ------------------------------------------------------------
# ÁUDIO
# ------------------------------------------------------------
WHISPER_FREE_AUDIO__SAMPLE_RATE=16000
WHISPER_FREE_AUDIO__CHANNELS=1
WHISPER_FREE_AUDIO__BLOCKSIZE=1024
# Índice (ex.: 2) ou trecho do nome; vazio = padrão do Windows
WHISPER_FREE_AUDIO__DEVICE=

# ------------------------------------------------------------
# HOTKEYS
# ------------------------------------------------------------
WHISPER_FREE_HOTKEY__MODE=hold
WHISPER_FREE_HOTKEY__TRIGGER=ctrl+shift+space
WHISPER_FREE_HOTKEY__CLOUD_TRIGGER=ctrl+alt+space
WHISPER_FREE_HOTKEY__TOGGLE_ENABLED=ctrl+shift+f12
WHISPER_FREE_HOTKEY__SUPPRESS=true

# ------------------------------------------------------------
# GRAMÁTICA (LANGUAGETOOL)
# ------------------------------------------------------------
WHISPER_FREE_GRAMMAR__ENABLED=true
WHISPER_FREE_GRAMMAR__LANGUAGE=pt-BR
WHISPER_FREE_GRAMMAR__AUTO_DOWNLOAD_JAVA=true
WHISPER_FREE_GRAMMAR__MAX_MATCHES=5
WHISPER_FREE_GRAMMAR__TIMEOUT_SECONDS=15

# ------------------------------------------------------------
# OVERLAY
# ------------------------------------------------------------
WHISPER_FREE_OVERLAY__ENABLED=true
# top-center | center | bottom-center | mouse
WHISPER_FREE_OVERLAY__POSITION=bottom-center
WHISPER_FREE_OVERLAY__ALWAYS_SHOW_ON_SUCCESS_MS=1200

# ------------------------------------------------------------
# INJEÇÃO DE TEXTO
# ------------------------------------------------------------
# paste (clipboard + Ctrl+V) | type (SendInput Unicode)
WHISPER_FREE_INJECTOR__MODE=paste
WHISPER_FREE_INJECTOR__RESTORE_CLIPBOARD=true
WHISPER_FREE_INJECTOR__FALLBACK_TO_TYPE=true
WHISPER_FREE_INJECTOR__CHAR_INTERVAL_S=0.001
WHISPER_FREE_INJECTOR__PRE_INJECT_DELAY_S=0.05

# ------------------------------------------------------------
# OPENAI (TRANSCRIÇÃO VIA API)
# ------------------------------------------------------------
WHISPER_FREE_OPENAI__ENABLED=true
WHISPER_FREE_OPENAI__API_KEY=
WHISPER_FREE_OPENAI__MODEL=gpt-4o-transcribe
WHISPER_FREE_OPENAI__BASE_URL=https://api.openai.com/v1
WHISPER_FREE_OPENAI__LANGUAGE=pt
WHISPER_FREE_OPENAI__PROMPT=
WHISPER_FREE_OPENAI__TIMEOUT_SECONDS=60

# ------------------------------------------------------------
# INICIALIZAÇÃO COM WINDOWS
# ------------------------------------------------------------
WHISPER_FREE_STARTUP__AUTO_START=false
```

---

## Perfis de configuração

### Máxima velocidade (RTX 3060)

```ini
WHISPER_FREE_WHISPER__MODEL_SIZE=large-v3-turbo
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8_float16
WHISPER_FREE_WHISPER__LANGUAGE=pt
WHISPER_FREE_WHISPER__BEAM_SIZE=1
WHISPER_FREE_GRAMMAR__ENABLED=false
WHISPER_FREE_AUDIO__BLOCKSIZE=512
WHISPER_FREE_INJECTOR__PRE_INJECT_DELAY_S=0
```

### Máxima precisão

```ini
WHISPER_FREE_WHISPER__MODEL_SIZE=large-v3
WHISPER_FREE_WHISPER__COMPUTE_TYPE=float16
WHISPER_FREE_WHISPER__LANGUAGE=
WHISPER_FREE_WHISPER__BEAM_SIZE=5
WHISPER_FREE_GRAMMAR__ENABLED=true
WHISPER_FREE_GRAMMAR__MAX_MATCHES=10
```

### GPU 8 GB (RTX 3070/4060)

```ini
WHISPER_FREE_WHISPER__MODEL_SIZE=medium
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8_float16
WHISPER_FREE_WHISPER__FALLBACK_TO_CPU=true
WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS=30
```

### Somente CPU

```ini
WHISPER_FREE_WHISPER__MODEL_SIZE=small
WHISPER_FREE_WHISPER__DEVICE=cpu
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8
WHISPER_FREE_WHISPER__FALLBACK_TO_CPU=false
WHISPER_FREE_WHISPER__CPU_THREADS=4
```

### Desenvolvimento/debug

```ini
WHISPER_FREE_LOG_LEVEL=DEBUG
WHISPER_FREE_WHISPER__MODEL_SIZE=tiny
WHISPER_FREE_WHISPER__DEVICE=cpu
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8
WHISPER_FREE_GRAMMAR__ENABLED=false
WHISPER_FREE_HOTKEY__TRIGGER=ctrl+shift+f1
```

---

## Variáveis de ambiente

```powershell
# PowerShell (temporário)
$env:WHISPER_FREE_WHISPER__MODEL_SIZE="medium"
$env:WHISPER_FREE_WHISPER__DEVICE="cpu"
.venv\Scripts\python -m whisper_free
```

```cmd
:: CMD
set WHISPER_FREE_GRAMMAR__ENABLED=false
.venv\Scripts\python -m whisper_free
```

---

## Validação

```bash
.venv\Scripts\python -m whisper_free --check
```

ou:

```bash
.venv\Scripts\python -c "
from whisper_free.config.settings import load_settings
s = load_settings()
print(s.whisper.model_size, s.whisper.device, s.whisper.compute_type)
print(s.hotkey.trigger, s.hotkey.mode)
print(s.overlay.position)
"
```

---

## Recarregar configuração

O app lê o `.env` no startup. Alterações exigem reiniciar o processo:

```bash
# encerre pelo tray e inicie novamente
.venv\Scripts\python -m whisper_free
```

Não existe hot reload de settings.

---

## Migração de versões

Configurações antigas com prefixo `WHISPER__`/`APP__` **não são lidas**. Migre para `WHISPER_FREE_WHISPER__...`, `WHISPER_FREE_HOTKEY__...`, etc.

Campos removidos/inexistentes: `GPU__UNLOAD_DELAY_S`, `GPU__MEMORY_FRACTION`, `GPU__ENABLE_TF32`, `OVERLAY__OPACITY`, `LOGGING__*`, `PIPELINE__THREAD_POOL_SIZE`.

Equivalentes atuais:
- `GPU__UNLOAD_DELAY_S` → `WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS`
- `LOGGING__LEVEL` → `WHISPER_FREE_LOG_LEVEL`
- `OVERLAY__AUTO_HIDE_DELAY_MS` → `WHISPER_FREE_OVERLAY__ALWAYS_SHOW_ON_SUCCESS_MS`

---

## Troubleshooting de configuração

### Configuração não carrega

```bash
# 1. O .env está na raiz do projeto (ou em WHISPER_FREE_HOME)?
dir .env

# 2. Encoding UTF-8
# 3. Teste direto
.venv\Scripts\python -c "from whisper_free.config.settings import load_settings; print(load_settings().model_dump())"
```

### Valores não aplicados

- Use `WHISPER_FREE_` + `SECTION__FIELD` (dois underscores).
- Não deixe espaços ao redor do `=`.
- Reinicie o app após editar o `.env`.
- Variáveis de ambiente reais sobrescrevem o arquivo.

### Conflito de hotkey

```python
import keyboard

handle = keyboard.add_hotkey("ctrl+shift+space", lambda: print("OK"))
keyboard.remove_hotkey(handle)
```
