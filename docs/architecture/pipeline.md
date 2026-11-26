# Pipeline de Transcrição - Síncrono

## Visão Geral

O `TranscriptionPipeline` (`transcription/pipeline.py`) encadeia:

**Áudio → Whisper/OpenAI → Gramática → Limpeza → Texto final**

O pipeline é **síncrono** e projetado para rodar na worker thread única do controller. Não há `asyncio`, `Future` interno nem executor próprio.

## Modos de transcrição

| Modo | Backend | GPU | Atalho padrão |
|------|---------|-----|---------------|
| `TranscriptionMode.LOCAL` | faster-whisper (CTranslate2) | sim | `Ctrl+Shift+Espaço` |
| `TranscriptionMode.CLOUD` | OpenAI `/audio/transcriptions` | não | `Ctrl+Alt+Espaço` |

O modo cloud envia um WAV PCM16 16 kHz mono via `urllib` (sem dependências extras) e nunca toca a VRAM. A correção gramatical e a limpeza final são compartilhadas.

## Estrutura

```python
class TranscriptionPipeline:
    def __init__(self, settings, whisper_engine, grammar, gpu_manager):
        self._settings = settings
        self._whisper = whisper_engine
        self._grammar = grammar
        self._gpu = gpu_manager
```

O controller cria a instância padrão, mas aceita um `pipeline=` injetado nos testes.

## Fluxo de execução

```
┌────────────────────────────────────────────────────────────────────┐
│                    TRANSCRIPTION PIPELINE                          │
├────────────────────────────────────────────────────────────────────┤
│  INPUT: np.ndarray float32, mono, 16 kHz                          │
│       │                                                            │
│       ▼                                                            │
│  gpu.begin_use()                                                   │
│       │                                                            │
│       ▼                                                            │
│  WhisperEngine.transcribe(audio)                                   │
│       │  └─ faster-whisper (CTranslate2)                           │
│       ▼                                                            │
│  texto vazio? ──sim──▶ retorna final_text=""                       │
│       │ não                                                        │
│       ▼                                                            │
│  GrammarCorrector.correct(text)                                    │
│       │  ├─ LanguageTool.check()                                   │
│       │  ├─ aplica categorias seguras                              │
│       │  └─ cleanup_text()                                         │
│       ▼                                                            │
│  cleanup_text(grammar.corrected or transcription.text)             │
│       │                                                            │
│       ▼                                                            │
│  gpu.end_use()  (finally)                                          │
│       │                                                            │
│       ▼                                                            │
│  OUTPUT: PipelineResult                                            │
└────────────────────────────────────────────────────────────────────┘
```

## Resultado

```python
@dataclass
class PipelineResult:
    final_text: str = ""
    transcription: TranscriptionResult = field(default_factory=TranscriptionResult)
    grammar: GrammarResult = field(default_factory=GrammarResult)
    total_elapsed_s: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.final_text)
```

## Métodos

### `process(audio) -> PipelineResult`

Executa o fluxo completo. Sempre retorna um `PipelineResult`; exceções são capturadas em `result.error` e logadas.

```python
def process(self, audio, mode=TranscriptionMode.LOCAL):
    started = time.perf_counter()
    result = PipelineResult()
    self._gpu.begin_use()
    try:
        transcription = self._whisper.transcribe(audio)
        result.transcription = transcription
        if not transcription.text:
            return result

        grammar_result = self._grammar.correct(transcription.text)
        result.grammar = grammar_result
        result.final_text = cleanup_text(
            grammar_result.corrected or transcription.text
        )
    except Exception as exc:
        result.error = str(exc)
    finally:
        self._gpu.end_use()
    result.total_elapsed_s = time.perf_counter() - started
    return result
```

### `release_gpu()`

Chamado ao **desativar** o assistente. Não é chamado a cada frase.

```python
def release_gpu(self) -> None:
    self._gpu.unload_models()
```

Se houver transcrição em andamento, o `GPUManager` adia o unload até `end_use()`.

### `warmup()`

Pré-carrega o Whisper para diagnóstico (o fluxo normal carrega no atalho e descarrega ao fim do ditado):

```python
def warmup(self) -> None:
    self._whisper.warmup()
    self._gpu.touch()
```

### `prepare_grammar()`

Inicia o LanguageTool e roda um `check()` curto para carregar dicionários:

```python
def prepare_grammar(self) -> None:
    if self._settings.grammar.enabled:
        self._grammar.warmup()
```

O controller chama isso em uma thread de preparação no startup.

### `shutdown()`

Encerra o LanguageTool e força o unload:

```python
def shutdown(self) -> None:
    self._grammar.close()
    self._gpu.unload_models(force=True)
```

## WhisperEngine

```python
class WhisperEngine:
    def transcribe(self, audio: np.ndarray) -> TranscriptionResult:
        self._gpu.ensure_loaded(need_whisper=True)
        model = self._gpu.whisper
        segments_iter, info = model.transcribe(
            audio,
            language=whisper.language or None,
            beam_size=whisper.beam_size,
            vad_filter=whisper.vad_filter,
            vad_parameters={
                "threshold": 0.5,
                "min_speech_duration_ms": 250,
                "max_speech_duration_s": 30,
                "min_silence_duration_ms": 400,
            },
            condition_on_previous_text=whisper.condition_on_previous_text,
            word_timestamps=False,
        )
        ...
```

Os parâmetros de VAD são fixos no código; `vad_filter` pode ser desligado via `.env`.

### `TranscriptionResult`

```python
@dataclass
class TranscriptionResult:
    text: str = ""
    language: str = ""
    language_probability: float = 0.0
    duration_s: float = 0.0
    elapsed_s: float = 0.0
    segments: list[dict] = field(default_factory=list)

    @property
    def realtime_factor(self) -> float:
        return self.duration_s / self.elapsed_s
```

## GrammarCorrector

- `start()` é idempotente e tenta apenas uma vez; se falhar, degrada para `cleanup_text`.
- `warmup()` inicia o servidor e roda uma verificação curta.
- `correct()` aplica apenas categorias seguras: `TYPOS`, `GRAMMAR`, `PUNCTUATION`, `CASING`, `CONFUSED_WORDS`, `REDUNDANCY`, `COMPOUNDS`, `AGREEMENT`, `MISC`.
- `max_matches` limita quantas sugestões são convertidas.
- `close()` encerra o processo Java.

```python
@dataclass
class GrammarResult:
    original: str = ""
    corrected: str = ""
    matches: list[GrammarMatch] = field(default_factory=list)
    elapsed_s: float = 0.0
    engine_used: str = "none"  # "languagetool" | "cleanup" | "none"
```

## Integração com o Controller

```python
# core/controller.py
def _stop_listening(self) -> None:
    ...
    audio = self.audio_buffer.consume()
    self._try_transition(AppState.LISTENING, AppState.PROCESSING)
    self._executor.submit(self._process_worker, audio, generation)

def _process_worker(self, audio, generation: int) -> None:
    result = self.pipeline.process(audio)
    if not self._is_current(generation):
        return
    ...
    self._try_transition(AppState.PROCESSING, AppState.INJECTING)
    self.injector.inject(result.final_text)
    self._settle_after_injection()
```

O `ThreadPoolExecutor(max_workers=1)` do controller serializa as transcrições.

## Performance

| Etapa | Tempo típico (RTX 3060) |
|-------|-------------------------|
| Whisper (5 s de áudio) | 800–1500 ms |
| Gramática (50 caracteres) | 100–300 ms |
| **Total** | **900–1800 ms** |

### Otimizações aplicadas

1. **Modelo sob demanda** — carregado no atalho e liberado ao fim do ditado.
2. **VAD integrado** — remove silêncio antes do Whisper.
3. **LanguageTool local** — sem latência de rede.
4. **`int8_float16`** — menos VRAM e mais velocidade que FP16/FP32.
5. **Worker única** — evita contenção na GPU.
