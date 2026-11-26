# Guia de Desenvolvimento

## Pré-requisitos

- Windows 10/11
- Python **3.11** ou **3.12**
- Git
- (Opcional) CUDA Toolkit 12.x para testar GPU
- (Opcional) Inno Setup 6 para gerar instalador

## Setup

```bash
git clone https://github.com/thierry-moreira/Whisper.git
cd Whisper

py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[dev]"

# Verificação rápida
.venv\Scripts\python -m whisper_free --check
.venv\Scripts\python -m pytest
```

## Estrutura

```
whisper-free/
├── .github/workflows/       # CI (Windows) e release
├── assets/                  # ícones
├── build/                   # .spec (PyInstaller) e .iss (Inno Setup)
├── docs/                    # esta documentação
├── scripts/                 # bootstrap, download, devices, ícones
├── src/whisper_free/
│   ├── config/              # constants.py, settings.py
│   ├── core/                # controller.py, gpu_manager.py, states.py
│   ├── audio/               # capture.py, buffer.py
│   ├── transcription/       # whisper_engine, grammar, java_runtime, pipeline
│   ├── input/               # hotkey.py, injector.py
│   ├── ui/                  # overlay.py (tkinter), tray.py (pystray)
│   ├── startup/             # windows.py (HKCU\Run)
│   ├── utils/               # helpers.py, logging.py
│   ├── main.py              # CLI + wiring
│   └── __main__.py          # python -m whisper_free
├── tests/
│   ├── conftest.py
│   ├── unit/                # 176 testes
│   └── integration/         # SendInput real (marcador)
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```

## Comandos do dia a dia

```bash
# Executar
.venv\Scripts\python -m whisper_free
.venv\Scripts\python -m whisper_free --debug
.venv\Scripts\python -m whisper_free --no-tray
.venv\Scripts\python -m whisper_free --no-overlay

# Diagnóstico
.venv\Scripts\python -m whisper_free --check
.venv\Scripts\python -m whisper_free --warmup

# Testes
.venv\Scripts\python -m pytest
.venv\Scripts\python -m pytest -v
.venv\Scripts\python -m pytest -k "controller or pipeline"
.venv\Scripts\python -m pytest -m integration -v

# Qualidade
.venv\Scripts\ruff check src tests scripts
.venv\Scripts\ruff check --fix src tests scripts
.venv\Scripts\black src tests scripts
.venv\Scripts\black --check src tests scripts
.venv\Scripts\mypy src
```

> Não há `pytest-xdist`: a suíte roda em um processo só e leva menos de 2 segundos. Evite adicionar `-n auto`.

## Pre-commit

```bash
.venv\Scripts\pre-commit install
.venv\Scripts\pre-commit run --all-files
```

Hooks configurados:

- `trailing-whitespace`
- `end-of-file-fixer`
- `check-yaml`
- `check-toml`
- `check-added-large-files`
- `ruff --fix`
- `black`

## Arquitetura em uma página

### Fluxo

```
HotkeyManager → Controller → AudioCapture → AudioBuffer
                    ↓
          ThreadPoolExecutor(1)
                    ↓
     TranscriptionPipeline → Whisper → Grammar → cleanup
                    ↓
              TextInjector → janela focada
```

### Regras

1. **Sem asyncio.** O pipeline é síncrono e roda em uma worker única.
2. **Sem PyQt6.** A UI é `tkinter` (overlay) + `pystray` (tray).
3. **Thread safety:**
   - `Controller` usa `RLock` e `_generation`.
   - `AudioBuffer` usa lock interno.
   - `OverlayWindow` recebe ações por `queue.Queue`; só a thread Tk toca widgets.
   - `GPUManager` usa `RLock` + `_active_uses`.
4. **GPU sob demanda:** `begin_use()`/`end_use()` protegem a transcrição; o unload ocioso usa `threading.Timer`.
5. **Injeção:** clipboard + `Ctrl+V` por padrão; `SendInput` Unicode como fallback.
6. **Configuração:** Pydantic Settings v2, prefixo `WHISPER_FREE_`, `__` para seções.

## Adicionando uma configuração

1. Adicione o campo na subclasse correta em `src/whisper_free/config/settings.py`:

```python
class WhisperSettings(BaseModel):
    ...
    my_option: int = Field(default=10, ge=1, le=100)
```

2. Documente em `.env.example`, `docs/reference/env-vars.md` e `docs/api/settings.md`.
3. Adicione um teste em `tests/unit/test_settings.py`.
4. Use via `self._settings.whisper.my_option`.

## Adicionando um teste

```python
# tests/unit/test_minha_feature.py
from whisper_free.core.states import AppState


def test_minha_feature(controller, fake_overlay):
    controller.on_hotkey_press()

    assert controller.state is AppState.LISTENING
    assert fake_overlay.states() == ["listening"]
```

Prefira as fixtures de `conftest.py`. Para componentes novos, injete fakes via construtor em vez de monkeypatch global.

## Debug

### Logs

```bash
.venv\Scripts\python -m whisper_free --debug
Get-Content logs\whisper_free.log -Tail 50 -Wait
```

O log usa `loguru`, com rotação em `logs/whisper_free.log`.

### Estado e GPU

```python
# Adicione temporariamente no controller ou use o REPL
print(controller.state, controller.enabled)
print(controller.gpu.stats)
```

### Áudio

```bash
.venv\Scripts\python scripts\list_devices.py
```

### Linguagem natural

```bash
.venv\Scripts\python -c "
from whisper_free.config.settings import load_settings
from whisper_free.core.gpu_manager import GPUManager
from whisper_free.transcription.whisper_engine import WhisperEngine
s = load_settings()
gpu = GPUManager(s)
engine = WhisperEngine(s, gpu)
print(engine.warmup())
"
```

## Estilo de código

- `black` com `line-length = 100`.
- `ruff` com `E, F, I, UP, B, C4, SIM, RUF`.
- `mypy src` sem erros.
- Type hints em APIs públicas.
- Docstrings curtas em módulos e classes.
- Evite imports pesados no topo quando puder adiar (`language_tool_python`, `torch`).

## Checklist antes de um PR

```bash
.venv\Scripts\ruff check src tests scripts
.venv\Scripts\black --check src tests scripts
.venv\Scripts\mypy src
.venv\Scripts\python -m pytest
.venv\Scripts\python -m whisper_free --check
```

## Release

1. Atualize a versão em `pyproject.toml`, `src/whisper_free/config/constants.py` e `build/whisper_free.iss`.
2. Atualize `docs/reference/changelog.md`.
3. Rode a validação completa.
4. Gere o executável e o instalador.
5. Crie a tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

O workflow de release anexa `WhisperFree-win64.zip`. O instalador é anexado manualmente.
