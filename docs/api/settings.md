# API Reference - Settings (Configuração)

## Visão Geral

O sistema usa **Pydantic Settings v2** com validação, suporte a `.env` e type hints.

```python
from whisper_free.config.settings import load_settings, Settings

settings = load_settings()

model = settings.whisper.model_size       # str
device = settings.whisper.device          # Literal["cuda", "cpu", "auto"]
hotkey = settings.hotkey.trigger          # str normalizada
```

`load_settings()` cria uma instância nova a cada chamada; não há cache global.

## Estrutura raiz

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WHISPER_FREE_",
        env_nested_delimiter="__",
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    version: str = APP_VERSION
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    single_instance: bool = True

    whisper: WhisperSettings = Field(default_factory=WhisperSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    grammar: GrammarSettings = Field(default_factory=GrammarSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    hotkey: HotkeySettings = Field(default_factory=HotkeySettings)
    overlay: OverlaySettings = Field(default_factory=OverlaySettings)
    injector: InjectorSettings = Field(default_factory=InjectorSettings)
    startup: StartupSettings = Field(default_factory=StartupSettings)
```

O arquivo `.env` é procurado em `PROJECT_ROOT/.env`. `PROJECT_ROOT` é o checkout/instalação editável; em bundle congelado ou wheel, fica em `%LOCALAPPDATA%\Whisper Free`. A variável `WHISPER_FREE_HOME` sobrescreve essa raiz.

## Seções

### WhisperSettings

```python
class WhisperSettings(BaseModel):
    model_size: str = "large-v3-turbo"
    device: Literal["cuda", "cpu", "auto"] = "cuda"
    compute_type: Literal["int8_float16", "float16", "int8", "float32", "auto"] = "int8_float16"
    language: str = "pt"                  # vazio = auto
    beam_size: int = 5                    # 1..10
    vad_filter: bool = True
    condition_on_previous_text: bool = False
    model_dir: str = "<PROJECT_ROOT>/models"
    cpu_threads: int = 0                  # 0 = auto
    fallback_to_cpu: bool = True
    unload_after_use: bool = True         # libera a VRAM ao fim do ditado
    idle_unload_seconds: int = 60         # 0..3600; usado só se unload_after_use=false
```

`model_size` aceita os nomes de `WHISPER_MODEL_SIZES` ou um caminho local com `/` ou `\`.

### GrammarSettings

```python
class GrammarSettings(BaseModel):
    enabled: bool = True
    language: str = "pt-BR"
    auto_download_java: bool = True
    max_matches: int = 5                  # 1..50
    timeout_seconds: float = 15.0         # > 0
```

> `timeout_seconds` existe na configuração, mas o `GrammarCorrector` atual não o repassa ao `language_tool_python`; o campo fica reservado para uso futuro.

### AudioSettings

```python
class AudioSettings(BaseModel):
    sample_rate: int = 16000              # 8000..48000
    channels: int = 1                     # 1..2
    device: str = ""                      # índice ou trecho do nome; vazio = padrão
    blocksize: int = 1024                 # 128..8192
```

### HotkeySettings

```python
class HotkeySettings(BaseModel):
    mode: Literal["hold", "toggle"] = "hold"
    trigger: str = "ctrl+shift+space"
    cloud_trigger: str = "ctrl+alt+space"
    toggle_enabled: str = "ctrl+shift+f12"
    suppress: bool = True                 # engole a combinação
```

Os hotkeys são normalizados para minúsculas, sem espaços e com no máximo 4 teclas.
`trigger`, `cloud_trigger` e `toggle_enabled` precisam ser diferentes entre si.

### OpenAISettings

```python
class OpenAISettings(BaseModel):
    enabled: bool = True
    api_key: str = ""                     # nunca aparece nos logs
    model: str = "gpt-4o-transcribe"
    base_url: str = "https://api.openai.com/v1"
    language: str = "pt"
    prompt: str = ""
    timeout_seconds: float = 60.0         # 1..300
```

Usado pelo segundo atalho (`hotkey.cloud_trigger`). A chave pode ser definida no
`.env` ou pelo diálogo **Configurar API OpenAI** do menu do tray.

### OverlaySettings

```python
class OverlaySettings(BaseModel):
    enabled: bool = True
    position: Literal["top-center", "center", "bottom-center", "mouse"] = "bottom-center"
    always_show_on_success_ms: int = 1200  # 0..10000
```

O overlay é uma pílula de `216×44` px desenhada em um `tk.Canvas`. Não há opacidade, blur ou fonte configuráveis.

### InjectorSettings

```python
class InjectorSettings(BaseModel):
    mode: Literal["paste", "type"] = "paste"
    restore_clipboard: bool = True
    fallback_to_type: bool = True
    char_interval_s: float = 0.001        # 0.0..0.1
    pre_inject_delay_s: float = 0.05      # 0.0..1.0
```

### StartupSettings

```python
class StartupSettings(BaseModel):
    auto_start: bool = False
```

## Variáveis de ambiente

```bash
WHISPER_FREE_WHISPER__MODEL_SIZE=large-v3-turbo
WHISPER_FREE_WHISPER__DEVICE=cuda
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8_float16
WHISPER_FREE_WHISPER__LANGUAGE=pt
WHISPER_FREE_WHISPER__FALLBACK_TO_CPU=true
WHISPER_FREE_WHISPER__UNLOAD_AFTER_USE=true
WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS=60

WHISPER_FREE_AUDIO__SAMPLE_RATE=16000
WHISPER_FREE_AUDIO__DEVICE=

WHISPER_FREE_HOTKEY__MODE=hold
WHISPER_FREE_HOTKEY__TRIGGER=ctrl+shift+space
WHISPER_FREE_HOTKEY__CLOUD_TRIGGER=ctrl+alt+space
WHISPER_FREE_HOTKEY__TOGGLE_ENABLED=ctrl+shift+f12

WHISPER_FREE_OPENAI__API_KEY=sk-...
WHISPER_FREE_OPENAI__MODEL=gpt-4o-transcribe
WHISPER_FREE_OPENAI__BASE_URL=https://api.openai.com/v1

WHISPER_FREE_GRAMMAR__ENABLED=true
WHISPER_FREE_GRAMMAR__LANGUAGE=pt-BR

WHISPER_FREE_OVERLAY__POSITION=bottom-center
WHISPER_FREE_INJECTOR__MODE=paste
WHISPER_FREE_STARTUP__AUTO_START=false
WHISPER_FREE_LOG_LEVEL=INFO
```

## Validação

```python
from pydantic import ValidationError
from whisper_free.config.settings import load_settings

try:
    settings = load_settings()
except ValidationError as exc:
    for error in exc.errors():
        print(error["loc"], error["msg"])
```

## Overrides programáticos

```python
settings = load_settings()
settings.whisper.model_size = "medium"   # objeto é mutável
```

`load_settings(**overrides)` aplica `model_copy(update=...)`, útil em testes:

```python
settings = load_settings(log_level="DEBUG")
```

## Serialização

```python
settings.model_dump()
settings.whisper.model_dump()
```

## Debug rápido

```bash
.venv\Scripts\python -c "
from whisper_free.config.settings import load_settings
s = load_settings()
print(s.whisper.model_size, s.whisper.device, s.whisper.compute_type)
print(s.hotkey.trigger, s.hotkey.mode)
print(s.overlay.position)
"
```
