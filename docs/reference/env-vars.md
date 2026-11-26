# Referência - Variáveis de Ambiente (.env)

## Visão Geral

Todas as configurações podem ser definidas no `.env` da raiz do projeto ou em variáveis de ambiente reais. O prefixo é **`WHISPER_FREE_`** e o separador de seções é **`__`** (duplo underscore).

```bash
WHISPER_FREE_WHISPER__MODEL_SIZE=large-v3-turbo
WHISPER_FREE_HOTKEY__TRIGGER=ctrl+shift+space
```

> Variáveis de ambiente têm precedência sobre o `.env`. Nomes são case-insensitive.

## Raiz

| Variável | Tipo | Padrão | Descrição |
|----------|------|--------|-----------|
| `WHISPER_FREE_VERSION` | str | `0.1.0` | Versão reportada |
| `WHISPER_FREE_LOG_LEVEL` | str | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `WHISPER_FREE_SINGLE_INSTANCE` | bool | `true` | Impede múltiplas instâncias |
| `WHISPER_FREE_HOME` | path | — | Sobrescreve a raiz de dados (`.env`, `models/`, `logs/`, `runtime/`) |

## Whisper (`WHISPER_FREE_WHISPER__*`)

| Variável | Tipo | Padrão | Descrição |
|----------|------|--------|-----------|
| `MODEL_SIZE` | str | `large-v3-turbo` | Nome do modelo ou caminho local |
| `DEVICE` | str | `cuda` | `cuda`, `cpu`, `auto` |
| `COMPUTE_TYPE` | str | `int8_float16` | `int8_float16`, `float16`, `int8`, `float32`, `auto` |
| `LANGUAGE` | str | `pt` | Código do idioma; vazio = automático |
| `BEAM_SIZE` | int | `5` | 1–10 |
| `VAD_FILTER` | bool | `true` | Filtro de voz do faster-whisper |
| `CONDITION_ON_PREVIOUS_TEXT` | bool | `false` | Contexto entre segmentos |
| `MODEL_DIR` | path | `models/` | Cache de modelos |
| `CPU_THREADS` | int | `0` | 0 = automático |
| `FALLBACK_TO_CPU` | bool | `true` | Recria em CPU/int8 se CUDA falhar |
| `UNLOAD_AFTER_USE` | bool | `true` | Descarrega o modelo ao fim de cada ditado |
| `IDLE_UNLOAD_SECONDS` | int | `60` | Usado só com `UNLOAD_AFTER_USE=false`; `0` = nunca |

Modelos aceitos: `tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3`, `large-v3-turbo`, `distil-large-v3`.

## Gramática (`WHISPER_FREE_GRAMMAR__*`)

| Variável | Tipo | Padrão | Descrição |
|----------|------|--------|-----------|
| `ENABLED` | bool | `true` | Habilita LanguageTool |
| `LANGUAGE` | str | `pt-BR` | Idioma do LanguageTool |
| `AUTO_DOWNLOAD_JAVA` | bool | `true` | Baixa JRE 17 portátil se necessário |
| `MAX_MATCHES` | int | `5` | Máximo de sugestões aplicadas (1–50) |
| `TIMEOUT_SECONDS` | float | `15.0` | Reservado (não usado pelo corretor atual) |

## Áudio (`WHISPER_FREE_AUDIO__*`)

| Variável | Tipo | Padrão | Descrição |
|----------|------|--------|-----------|
| `SAMPLE_RATE` | int | `16000` | 8000–48000 Hz |
| `CHANNELS` | int | `1` | 1 (mono) ou 2 |
| `DEVICE` | str | `""` | Índice (`2`) ou trecho do nome; vazio = padrão |
| `BLOCKSIZE` | int | `1024` | Frames por callback (128–8192) |

## Hotkeys (`WHISPER_FREE_HOTKEY__*`)

| Variável | Tipo | Padrão | Descrição |
|----------|------|--------|-----------|
| `MODE` | str | `hold` | `hold` ou `toggle` |
| `TRIGGER` | str | `ctrl+shift+space` | Hotkey de gravação |
| `TOGGLE_ENABLED` | str | `ctrl+shift+f12` | Liga/desliga o assistente |
| `CLOUD_TRIGGER` | str | `ctrl+alt+space` | Hotkey da transcrição via API OpenAI |
| `SUPPRESS` | bool | `true` | Impede que o app focado receba a combinação |

## Overlay (`WHISPER_FREE_OVERLAY__*`)

| Variável | Tipo | Padrão | Descrição |
|----------|------|--------|-----------|
| `ENABLED` | bool | `true` | Mostra o overlay |
| `POSITION` | str | `bottom-center` | `top-center`, `center`, `bottom-center`, `mouse` |
| `ALWAYS_SHOW_ON_SUCCESS_MS` | int | `1200` | Tempo visível de sucesso/erro (0–10000) |

## Injeção (`WHISPER_FREE_INJECTOR__*`)

| Variável | Tipo | Padrão | Descrição |
|----------|------|--------|-----------|
| `MODE` | str | `paste` | `paste` (clipboard) ou `type` (SendInput) |
| `RESTORE_CLIPBOARD` | bool | `true` | Restaura o clipboard após colar |
| `FALLBACK_TO_TYPE` | bool | `true` | Digita diretamente se o clipboard falhar |
| `CHAR_INTERVAL_S` | float | `0.001` | Intervalo entre caracteres no modo `type` |
| `PRE_INJECT_DELAY_S` | float | `0.05` | Espera antes de injetar |

## Startup (`WHISPER_FREE_STARTUP__*`)

| Variável | Tipo | Padrão | Descrição |
|----------|------|--------|-----------|
| `AUTO_START` | bool | `false` | Registra/remove `HKCU\Run` ao iniciar |

## OpenAI (`WHISPER_FREE_OPENAI__*`)

Usado pelo segundo atalho (`CLOUD_TRIGGER`) para transcrições via API.

| Variável | Tipo | Padrão | Descrição |
|----------|------|--------|-----------|
| `ENABLED` | bool | `true` | Habilita o modo cloud |
| `API_KEY` | str | `""` | Chave da API; vazio desativa o atalho cloud |
| `MODEL` | str | `gpt-4o-transcribe` | Modelo de transcrição |
| `BASE_URL` | str | `https://api.openai.com/v1` | Endpoint base |
| `LANGUAGE` | str | `pt` | Código do idioma |
| `PROMPT` | str | `""` | Dica de vocabulário/estilo |
| `TIMEOUT_SECONDS` | float | `60` | Timeout da requisição (1–300) |

A chave pode ser configurada pelo menu do tray (**Configurar API OpenAI**) ou diretamente no `.env`; ela nunca é gravada nos logs.

## Exemplos

### PowerShell (temporário)

```powershell
$env:WHISPER_FREE_WHISPER__MODEL_SIZE="medium"
.venv\Scripts\python -m whisper_free
```

### CMD

```cmd
set WHISPER_FREE_WHISPER__DEVICE=cpu
.venv\Scripts\python -m whisper_free
```

### `.env` persistente

```ini
WHISPER_FREE_WHISPER__MODEL_SIZE=large-v3-turbo
WHISPER_FREE_WHISPER__DEVICE=cuda
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8_float16
WHISPER_FREE_WHISPER__FALLBACK_TO_CPU=true
WHISPER_FREE_WHISPER__UNLOAD_AFTER_USE=true
WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS=60

WHISPER_FREE_HOTKEY__TRIGGER=ctrl+shift+space
WHISPER_FREE_HOTKEY__CLOUD_TRIGGER=ctrl+alt+space
WHISPER_FREE_OPENAI__MODEL=gpt-4o-transcribe
WHISPER_FREE_GRAMMAR__ENABLED=true
WHISPER_FREE_OVERLAY__POSITION=bottom-center
WHISPER_FREE_INJECTOR__MODE=paste
WHISPER_FREE_LOG_LEVEL=INFO
```

### Validação

```bash
.venv\Scripts\python -m whisper_free --check
```

ou:

```bash
.venv\Scripts\python -c "
from whisper_free.config.settings import load_settings
s = load_settings()
print(s.model_dump_json(indent=2))
"
```
