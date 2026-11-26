# Guia de Testes

## Visão Geral

O projeto usa **pytest** com uma suíte rápida e determinística:

- **221 testes** unitários em **20 arquivos**;
- **2 testes de integração** excluídos por padrão (marcador `integration`);
- **cobertura global ~64%**; o núcleo fica entre **84% e 94%**;
- nenhuma dependência de GPU, microfone, hooks reais ou display Tk na suíte padrão.

```bash
# Suíte padrão (rápida)
.venv\Scripts\python -m pytest

# Saída detalhada
.venv\Scripts\python -m pytest -v

# Cobertura
.venv\Scripts\python -m pytest --cov=whisper_free --cov-report=term-missing
```

## Estrutura

```
tests/
├── conftest.py                    # fixtures + fakes compartilhados
├── unit/
│   ├── test_audio_buffer.py       # AudioBuffer thread-safe
│   ├── test_controller.py         # máquina de estados, corrida, toggle
│   ├── test_gpu_manager.py        # lazy load, idle unload, force unload
│   ├── test_grammar.py            # LanguageTool + cleanup
│   ├── test_helpers.py            # paths, mutex, pythonw
│   ├── test_hotkey.py             # handles, debounce, registro parcial
│   ├── test_injector.py           # paste/type, fallback, SendInput mockado
│   ├── test_java_runtime.py       # descoberta e compatibilidade (17+)
│   ├── test_logging.py            # console=False, stderr ausente
│   ├── test_pipeline.py           # whisper → gramática → texto
│   ├── test_settings.py           # defaults e validação
│   ├── test_startup.py            # HKCU\Run
│   ├── test_states.py             # AppState e transições
│   └── test_whisper_engine.py     # parâmetros + fallback CUDA→CPU
└── integration/
    └── test_sendinput.py          # toca o desktop real (marcador integration)
```

## Marcadores e `addopts`

O `pyproject.toml` já exclui os testes lentos por padrão:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = ["-ra", "-q", "-m", "not integration and not gpu"]
markers = [
    "integration: tests that use real models/audio (slow)",
    "gpu: tests that require a CUDA GPU",
]
```

| Comando | O que executa |
|---------|----------------|
| `pytest` | 221 testes unitários |
| `pytest -m integration` | apenas testes que tocam APIs reais do Windows |
| `pytest -m gpu` | apenas testes marcados como dependentes de GPU |
| `pytest -m "not integration and not gpu"` | explícito (mesmo que o padrão) |

> Os 2 testes de `tests/integration/test_sendinput.py` chamam `SendInput` de verdade e podem colar `Ctrl+V` na janela ativa. Execute-os apenas quando estiver pronto para isso.

## Fixtures compartilhadas (`conftest.py`)

| Fixture | Retorno | Uso |
|---------|---------|-----|
| `settings` | `Settings` determinístico | modelo `tiny`, CPU, gramática desligada, `tmp_path` |
| `audio_chunk` | `np.ndarray` int16 `(16000, 1)` | chunks no formato do sounddevice |
| `float_audio` | `np.ndarray` float32 | entrada do pipeline |
| `fake_capture` | `FakeAudioCapture` | simula start/stop e chunks |
| `fake_injector` | `FakeInjector` | captura textos e falhas |
| `fake_pipeline` | `FakePipeline` | resultado canned e contadores |
| `fake_overlay` | `FakeOverlay` | registra chamadas de estado |
| `fake_tray` | `FakeTray` | registra refresh/notify |
| `fake_startup` | `FakeStartup` | autostart em memória |
| `inline_executor` | `InlineExecutor` | executa jobs sob demanda |
| `fake_hotkey_backend` | `FakeHotkeyBackend` | imita `keyboard.add_hotkey` |
| `controller` | `Controller` | tudo acima injetado |

O `conftest.py` também insere `src/` no `sys.path`, então `pytest` funciona mesmo sem `pip install -e .` (embora a instalação seja recomendada).

## Padrões de teste

### Controller sem threads reais

```python
def test_press_starts_listening(controller, fake_capture, fake_overlay):
    controller.on_hotkey_press()

    assert controller.state is AppState.LISTENING
    assert fake_capture.start_calls == 1
    assert fake_overlay.states()[-1] == "listening"
```

Use `inline_executor.run_pending()` para controlar quando a worker roda:

```python
def test_release_processes_audio(controller, fake_capture, inline_executor, fake_injector):
    controller.on_hotkey_press()
    fake_capture.push(np.zeros((16000, 1), dtype=np.int16))
    controller.on_hotkey_release()

    inline_executor.run_pending()

    assert fake_injector.injected == ["Olá mundo."]
    assert controller.state is AppState.IDLE
```

### Corrida `PROCESSING → DISABLED → INJECTING`

O teste chama `toggle_enabled()` **antes** de liberar a worker e verifica que nada é injetado:

```python
def test_disable_during_processing_discards_result(
    controller, fake_capture, inline_executor, fake_injector
):
    controller.on_hotkey_press()
    fake_capture.push(np.zeros((16000, 1), dtype=np.int16))
    controller.on_hotkey_release()

    controller.toggle_enabled()      # invalida a geração
    inline_executor.run_pending()    # worker termina depois

    assert fake_injector.injected == []
    assert controller.state is AppState.DISABLED
```

### GPUManager sem GPU

Injete factories em vez de importar CTranslate2:

```python
from whisper_free.core.gpu_manager import GPUManager, _Factories

def test_lazy_load(settings):
    created = []

    def factory():
        created.append(True)
        return object()

    gpu = GPUManager(settings, _Factories(whisper_factory=factory))
    assert gpu.stats.loaded is False

    gpu.ensure_loaded(need_whisper=True)
    gpu.ensure_loaded(need_whisper=True)

    assert created == [True]
    assert gpu.stats.loaded is True
```

### Fallback CUDA → CPU

Monkeypatch `WhisperModel` para falhar na primeira chamada:

```python
def test_cuda_failure_falls_back_to_cpu(settings, monkeypatch):
    settings.whisper.device = "cuda"
    settings.whisper.fallback_to_cpu = True
    calls = []

    class FakeModel:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs["device"])
            if kwargs["device"] == "cuda":
                raise RuntimeError("CUDA driver not found")
            self.transcribe = lambda *a, **k: ([], None)

    monkeypatch.setattr(
        "whisper_free.transcription.whisper_engine.WhisperModel", FakeModel
    )

    engine = WhisperEngine(settings, gpu=...)
    engine.warmup()

    assert calls == ["cuda", "cpu"]
```

### Injeção sem tocar o desktop

`TextInjector` aceita um sender injetado:

```python
class FakeSender:
    def __init__(self):
        self.texts = []

    def send_text(self, text):
        self.texts.append(text)

    def send_ctrl_v(self):
        pass

def test_type_mode(settings):
    settings.injector.mode = "type"
    sender = FakeSender()
    injector = TextInjector(settings, sender=sender)

    result = injector.inject("olá")

    assert result.success
    assert sender.texts == ["olá"]
```

O `_SendInputKeySender` real só é exercitado com `pytest -m integration`.

## Cobertura

```bash
.venv\Scripts\python -m pytest --cov=whisper_free --cov-report=term-missing
.venv\Scripts\python -m pytest --cov=whisper_free --cov-report=html
start htmlcov\index.html
```

Números de referência da última execução:

| Módulo | Cobertura |
|--------|-----------|
| `core/controller.py` | 84% |
| `core/gpu_manager.py` | 83% |
| `transcription/pipeline.py` | 93% |
| `input/injector.py` | 87% |
| `input/hotkey.py` | 87% |
| `transcription/openai_engine.py` | 84% |
| **Global** | **~64%** |

A cobertura global é menor porque `main.py`, `ui/` e `audio/capture.py` dependem de Tk, tray, PortAudio e APIs do Windows. Esses caminhos são validados manualmente e pelo teste de integração, não por mocks frágeis.

## Execução seletiva

```bash
# Um arquivo
.venv\Scripts\python -m pytest tests/unit/test_controller.py -v

# Um teste
.venv\Scripts\python -m pytest tests/unit/test_controller.py::test_press_starts_listening -v

# Por palavra-chave
.venv\Scripts\python -m pytest -k "fallback or idle" -v

# Parar no primeiro erro
.venv\Scripts\python -m pytest -x -vv

# Mostrar prints
.venv\Scripts\python -m pytest -s
```

O `pytest-timeout` está instalado. Para limitar um comando:

```bash
.venv\Scripts\python -m pytest --timeout=60
```

## Convenções

- Nome de arquivo: `test_<módulo>.py`.
- Nome de teste: `test_<comportamento>_<condição>`.
- Use fixtures em vez de instanciar componentes reais.
- Não use `time.sleep()`; prefira `InlineExecutor` e eventos.
- Não dependa de ordem de execução.
- Testes de integração devem ter `@pytest.mark.integration` (ou `pytestmark`).
- Testes de GPU devem ter `@pytest.mark.gpu`.
- Evite mocks de funções internas do próprio projeto; injete fakes pelas costuras públicas.

## CI

O workflow `.github/workflows/ci.yml` roda em `windows-latest` com Python **3.11** e **3.12**:

1. `pip install -e ".[dev]"`
2. `ruff check src tests scripts`
3. `black --check src tests scripts`
4. `mypy src`
5. `pytest --cov=whisper_free --cov-report=term-missing --cov-report=xml`
6. upload do `coverage.xml` como artefato

## Problemas comuns

### `ModuleNotFoundError: whisper_free`

```bash
.venv\Scripts\python -m pip install -e ".[dev]"
```

O `conftest.py` cobre o caso de execução sem instalação, mas instalar é o caminho suportado.

### Teste de integração não aparece

Ele é excluído por `addopts`. Rode explicitamente:

```bash
.venv\Scripts\python -m pytest -m integration -v
```

### `pytest` abre janelas ou mexe no teclado

Verifique se algum teste está marcado como `integration`. A suíte padrão não deve tocar o desktop.

### Teste trava esperando thread

Use `InlineExecutor` (`inline_executor.run_pending()`) e evite `ThreadPoolExecutor` real. Se precisar de tempo real, use `--timeout=30` para diagnosticar.
