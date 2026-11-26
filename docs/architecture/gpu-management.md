# Gerenciamento de GPU - Lazy Loading & Memória

## Visão Geral

O `GPUManager` (`core/gpu_manager.py`) controla o ciclo de vida dos modelos que ocupam VRAM:

1. **Lazy loading** — o Whisper é criado na primeira transcrição, disparada pelo atalho.
2. **Unload após o uso** — `end_use()` descarrega o modelo assim que o ditado termina (`unload_after_use=true`).
3. **Janela aquecida opcional** — com `unload_after_use=false`, o modelo permanece por `idle_unload_seconds` (padrão 60 s).
4. **Proteção contra corrida** — `begin_use()`/`end_use()` impedem o unload durante uma transcrição.
5. **Limpeza opcional de cache CUDA** — se `torch` estiver instalado, `torch.cuda.empty_cache()` é chamado.

> O fallback CUDA → CPU fica em `transcription/whisper_engine.py`, não no `GPUManager`.

## Estrutura

```python
class GPUManager:
    def __init__(self, settings: Settings, factories: _Factories | None = None):
        self._lock = threading.RLock()
        self._whisper: Any | None = None
        self._grammar: Any | None = None
        self._stats = GPUStats()
        self._active_uses = 0
        self._idle_timer: threading.Timer | None = None
        self._last_used = 0.0
        self._pending_unload = False
```

`_Factories` permite injetar `whisper_factory`, `whisper_cpu_factory`, `grammar_factory` e `torch_module` nos testes, sem importar as dependências pesadas.

## Lazy loading

```python
def ensure_loaded(self, need_whisper: bool = True, need_grammar: bool = False) -> None:
    with self._lock:
        if need_whisper and self._whisper is None:
            self._load_whisper()
        if need_grammar and self._grammar is None:
            self._load_grammar()
        self._last_used = time.monotonic()
```

O `WhisperEngine.transcribe()` chama `ensure_loaded(need_whisper=True)` antes de usar o modelo. A primeira transcrição paga o custo de criação; as seguintes reutilizam a instância.

### Configuração usada na criação

```python
WhisperModel(
    settings.whisper.model_size,
    device=settings.whisper.device,          # cuda | cpu | auto
    compute_type=settings.whisper.compute_type,
    cpu_threads=settings.whisper.cpu_threads,
    download_root=settings.whisper.model_dir,
)
```

| Parâmetro | Padrão | Observação |
|-----------|--------|------------|
| `model_size` | `large-v3-turbo` | Pode ser um diretório local |
| `device` | `cuda` | `auto` testa CTranslate2 |
| `compute_type` | `int8_float16` | Em CPU é convertido para `int8` |
| `cpu_threads` | `0` | 0 = automático |
| `model_dir` | `models/` | Cache local |

## Uso ativo e unload ocioso

```python
def begin_use(self) -> None:
    with self._lock:
        self._active_uses += 1
        self._cancel_idle_timer_locked()

def end_use(self) -> None:
    with self._lock:
        if self._active_uses > 0:
            self._active_uses -= 1
        self._last_used = time.monotonic()
        if self._active_uses == 0:
            if self._pending_unload:
                self._pending_unload = False
                unload_now = True
            else:
                self._schedule_idle_unload_locked()
    if unload_now:
        self.unload_models()
```

O `TranscriptionPipeline.process()` envolve a transcrição em `begin_use()` / `end_use()` em um bloco `try/finally`, então uma exceção também libera o contador.

### Timer de ociosidade

```python
def _schedule_idle_unload_locked(self) -> None:
    self._cancel_idle_timer_locked()
    delay = self._settings.whisper.idle_unload_seconds
    if delay <= 0 or (self._whisper is None and self._grammar is None):
        return
    timer = threading.Timer(delay, self._idle_unload)
    timer.daemon = True
    self._idle_timer = timer
    timer.start()
```

- Este timer só é usado quando `unload_after_use=false`; `idle_unload_seconds = 0` desativa o unload por ociosidade.
- Se o timer disparar enquanto `_active_uses > 0`, ele retorna sem descarregar.
- Se o uso recomeçar, o timer é cancelado e reagendado ao final.

### Unload imediato e adiado

```python
def unload_models(self, *, force: bool = False) -> None:
    with self._lock:
        self._cancel_idle_timer_locked()
        if self._active_uses > 0 and not force:
            self._pending_unload = True
            return
        self._whisper = None
        self._grammar = None
        ...
    gc.collect()
    self._empty_cuda_cache()
```

| Chamada | Comportamento |
|---------|---------------|
| `unload_models()` | adia se houver transcrição ativa |
| `unload_models(force=True)` | descarrega mesmo durante a transcrição (shutdown) |
| `pipeline.release_gpu()` | chama `unload_models()` ao desativar o assistente |
| `pipeline.shutdown()` | chama `unload_models(force=True)` |

Com `unload_after_use=true` (padrão), o `end_use()` do pipeline chama `unload_models()` imediatamente após a transcrição — a VRAM é liberada antes mesmo da injeção do texto.

## Estatísticas

```python
@dataclass
class GPUStats:
    loaded: bool = False
    device: str = "unknown"
    load_time_s: float = 0.0
    whisper_model: str = ""
    grammar_ready: bool = False
```

`gpu.stats` retorna uma **cópia** do snapshot (segura para leitura concorrente).

## Fallback CUDA → CPU

Antes de criar o modelo, `_cuda_runtime_available()` registra as DLLs dos wheels `nvidia-*` e tenta carregar `cublas64_12.dll`/`cudnn64_9.dll`. Se alguma falhar, o modelo já nasce em CPU/`int8`. Falhas de CUDA durante a transcrição também refazem o modelo via `GPUManager.switch_to_cpu()` e repetem a frase uma vez.

```python
try:
    return _build_model(WhisperModel, whisper, device, compute_type)
except Exception as exc:
    if device != "cuda" or not whisper.fallback_to_cpu or not _is_cuda_failure(exc):
        raise
    logger.warning(f"CUDA initialisation failed ({exc}). Falling back to CPU/int8")
    return _build_model(WhisperModel, whisper, "cpu", "int8")
```

- `_is_cuda_failure()` procura por `cuda`, `cudnn`, `cublas`, `cublaslt`, `nvidia` ou `gpu` na mensagem.
- Falhas não relacionadas a CUDA (ex.: `model.bin` ausente) **não** são repetidas em CPU.
- `fallback_to_cpu=false` mantém o erro original.

## Limpeza de VRAM

`torch` é uma dependência **opcional**. Se não estiver instalado:

```python
try:
    import torch as torch_module
except Exception:
    logger.debug("torch not installed — skipping CUDA cache cleanup")
    return
```

Quando disponível e com CUDA ativa, o manager executa `torch.cuda.empty_cache()`. O CTranslate2/faster-whisper libera a maior parte da VRAM ao descartar a referência do modelo.

## Configuração (.env)

```ini
WHISPER_FREE_WHISPER__DEVICE=cuda
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8_float16
WHISPER_FREE_WHISPER__FALLBACK_TO_CPU=true
WHISPER_FREE_WHISPER__UNLOAD_AFTER_USE=true
WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS=60
```

Não existem hoje `GPU__UNLOAD_DELAY_S`, `GPU__MEMORY_FRACTION` nem `GPU__ENABLE_TF32`.

## Troubleshooting

### `cublas64_12.dll` não encontrado

```
[ERROR] Library cublas64_12.dll is not found or cannot be loaded
```

**Solução**: instalar CUDA Toolkit 12.x ou adicionar ao `PATH`:

```
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin
```

Se não quiser instalar, deixe `FALLBACK_TO_CPU=true` para continuar em CPU.

O app pré-valida a DLL antes de criar o modelo: sem `cublas64_12.dll`, o modelo
já nasce em CPU/`int8`. Se uma falha de CUDA ocorrer durante a transcrição, o
`WhisperEngine` descarta o modelo CUDA, reconstrói em CPU e repete a frase uma
vez — o pipeline nunca fica preso em `PROCESSING`.

### CUDA out of memory

**Soluções**:
1. Usar modelo menor (`medium`, `small`).
2. Usar `COMPUTE_TYPE=int8` (menos VRAM, mais lento).
3. Fechar outros apps que usam GPU.
4. Reduzir `IDLE_UNLOAD_SECONDS` para liberar VRAM mais cedo.

### GPU não detectada

```bash
python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
nvidia-smi
```

Driver NVIDIA recente é necessário. Sem GPU, o app usa CPU automaticamente.

## Medindo VRAM

```bash
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

Comportamento esperado:
- após o primeiro ditado: ~2,8 GB (modelo `large-v3-turbo`, `int8_float16`);
- após 60 s ociosos: VRAM do app volta próxima de zero;
- próximo ditado: recarga de ~3–5 s (modelo já em cache de disco).
