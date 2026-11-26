# Referência - Estrutura de Pastas

## Visão Geral

```
whisper-free/
├── .github/
│   └── workflows/
│       ├── ci.yml                 # Ruff + Black + MyPy + pytest (Windows)
│       └── release.yml            # PyInstaller + anexo no GitHub Release
├── .vscode/
│   └── settings.json              # Configuração do interpretador/lint
├── assets/
│   ├── icon.ico                   # Ícone do executável/instalador
│   └── icon.png                   # Ícone PNG
├── build/
│   ├── whisper_free.spec          # PyInstaller one-file
│   └── whisper_free.iss           # Inno Setup 6
├── docs/
│   ├── index.md
│   ├── architecture/              # overview, state-machine, gpu, pipeline
│   ├── api/                       # settings.md
│   ├── guides/                    # instalação, configuração, dev, build, testes, troubleshooting
│   └── reference/                 # env-vars, hotkeys, folders, changelog
├── scripts/
│   ├── download_models.py         # Pré-baixa modelos Whisper
│   ├── install.py                 # Bootstrap (Python, pacote, CUDA, JRE, autostart)
│   ├── list_devices.py            # Lista microfones e dispositivos CUDA
│   ├── make_icon.py               # Gera assets/icon.{ico,png}
│   └── whisper_free_launcher.pyw  # Launcher sem console (pythonw)
├── src/whisper_free/
│   ├── __init__.py
│   ├── __main__.py                # python -m whisper_free
│   ├── main.py                    # CLI, single instance, wiring
│   ├── config/
│   │   ├── constants.py           # paths, defaults, limites
│   │   └── settings.py            # Pydantic Settings
│   ├── core/
│   │   ├── controller.py          # orquestração + state machine
│   │   ├── gpu_manager.py         # lazy load / idle unload
│   │   └── states.py              # AppState + transições
│   ├── audio/
│   │   ├── capture.py             # sounddevice InputStream
│   │   └── buffer.py              # AudioBuffer thread-safe
│   ├── transcription/
│   │   ├── whisper_engine.py      # faster-whisper + fallback CUDA→CPU
│   │   ├── cuda_runtime.py        # DLLs cuBLAS/cuDNN dos wheels NVIDIA
│   │   ├── grammar.py             # LanguageTool + cleanup
│   │   ├── java_runtime.py        # descoberta/download de JRE 17+
│   │   └── pipeline.py            # whisper → gramática → texto
│   ├── input/
│   │   ├── hotkey.py              # hooks globais + debounce
│   │   └── injector.py            # clipboard/SendInput
│   ├── ui/
│   │   ├── overlay.py             # pílula tkinter
│   │   └── tray.py                # pystray
│   ├── startup/
│   │   └── windows.py             # HKCU\Run
│   └── utils/
│       ├── helpers.py             # mutex, pythonw, launcher
│       └── logging.py             # loguru
├── tests/
│   ├── conftest.py                # fixtures e fakes
│   ├── unit/                      # 176 testes (14 arquivos)
│   └── integration/
│       └── test_sendinput.py      # marcado com @pytest.mark.integration
├── .env.example                   # template de configuração
├── .gitignore
├── .pre-commit-config.yaml
├── LICENSE                        # MIT
├── pyproject.toml                 # build, dependências e ferramentas
├── README.md
├── requirements.txt
└── requirements-dev.txt
```

> O diretório `build/` contém os arquivos-fonte do PyInstaller/Inno Setup. Durante um build, o PyInstaller também cria `build/` temporário; os artefatos finais vão para `dist/`.

---

## Descrição dos diretórios

### `src/whisper_free/`
Pacote Python instalável (`pip install -e .`). Contém toda a lógica do aplicativo.

### `tests/`
- `conftest.py`: fixtures compartilhadas (`settings`, `controller`, `fake_capture`, `fake_pipeline`, `fake_injector`, `inline_executor`, `float_audio`).
- `unit/`: 176 testes rápidos, sem GPU, microfone, hooks reais ou display Tk.
- `integration/`: testes que tocam APIs reais do Windows; excluídos por padrão.

### `scripts/`
- `download_models.py`: pré-baixa o modelo configurado.
- `install.py`: verifica Python/CUDA, instala o pacote em modo editável, opcionalmente baixa modelo/JRE e ativa autostart.
- `list_devices.py`: lista microfones e dispositivos CUDA.
- `make_icon.py`: gera os ícones a partir do glifo do tray.
- `whisper_free_launcher.pyw`: inicia o app via `pythonw`, sem console.

### `docs/`
- `architecture/`: decisões e diagramas.
- `api/`: referência de settings.
- `guides/`: tutoriais.
- `reference/`: consulta rápida.

### `assets/`
Ícones usados pelo tray, pelo executável e pelo instalador.

---

## Arquivos de configuração raiz

| Arquivo | Propósito |
|---------|-----------|
| `pyproject.toml` | PEP 621, dependências, `addopts` do pytest, Ruff/Black/MyPy |
| `requirements.txt` | Dependências de runtime |
| `requirements-dev.txt` | Dependências de desenvolvimento |
| `.env.example` | Template de configuração |
| `.gitignore` | Arquivos ignorados |
| `.pre-commit-config.yaml` | Hooks de pre-commit |
| `LICENSE` | MIT |

---

## Arquivos gerados (não versionados)

```
.venv/                    # Ambiente virtual
__pycache__/              # Bytecode
.pytest_cache/            # Cache do pytest
.mypy_cache/              # Cache do MyPy
.ruff_cache/              # Cache do Ruff
.coverage                 # Dados de cobertura
htmlcov/                  # Relatório HTML de cobertura
dist/                     # Executável/instalador
logs/                     # Logs de runtime
models/                   # Modelos Whisper em cache
runtime/                  # JRE portátil
*.egg-info/               # Metadados do pacote
```

---

## Convenções

| Tipo | Convenção | Exemplo |
|------|-----------|---------|
| Pacotes | snake_case | `whisper_free` |
| Módulos | snake_case | `gpu_manager.py` |
| Classes | PascalCase | `GPUManager` |
| Funções | snake_case | `ensure_loaded()` |
| Constantes | UPPER_SNAKE | `MAX_RECORDING_SECONDS` |
| Settings | `WHISPER_FREE_` + `SECTION__FIELD` | `WHISPER_FREE_WHISPER__MODEL_SIZE` |
| Privado | `_leading_underscore` | `_idle_unload()` |
| Type hints | PascalCase | `AudioBuffer` |
