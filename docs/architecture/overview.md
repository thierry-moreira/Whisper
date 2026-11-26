# Visão Geral da Arquitetura

## Diagrama de Alto Nível

```
┌──────────────────────────────────────────────────────────────────────┐
│                        WHISPER FREE (Windows)                        │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  keyboard ──▶ HotkeyManager ──▶ Controller (state machine)           │
│                                      │                               │
│                     ┌────────────────┼────────────────┐              │
│                     ▼                ▼                ▼              │
│               AudioCapture      OverlayWindow      TrayIcon           │
│                     │           (tkinter)         (pystray)          │
│                     ▼                                                │
│               AudioBuffer                                            │
│                     │                                                │
│                     ▼  (worker thread)                               │
│            TranscriptionPipeline ──▶ GPUManager (lazy/idle)          │
│                     │                                                │
│          ┌──────────┴──────────┐                                     │
│          ▼                     ▼                                     │
│    WhisperEngine        GrammarCorrector                             │
│  (faster-whisper)        (LanguageTool)                              │
│          └──────────┬──────────┘                                     │
│                     ▼                                                │
│               TextInjector ──▶ janela focada                         │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

## Princípios de Design

### 1. Separação de responsabilidades
- `audio/` — captura (sounddevice) e buffer thread-safe.
- `transcription/` — Whisper, LanguageTool, pipeline e descoberta de Java.
- `input/` — hotkeys globais e injeção de texto.
- `ui/` — overlay (tkinter) e tray (pystray).
- `core/` — controller, máquina de estados e GPU manager.
- `config/` — settings tipados e constantes.
- `startup/` — integração com o registro do Windows.

### 2. GPU sob demanda, liberada após cada ditado
- O modelo Whisper é criado automaticamente na primeira transcrição disparada pelo atalho.
- Ao terminar o ditado, `end_use()` descarrega o modelo e libera a VRAM (`unload_after_use=true`).
- Com `unload_after_use=false`, ele permanece aquecido por `whisper.idle_unload_seconds` (padrão **60 s**).
- `GPUManager.begin_use()` / `end_use()` impedem que o unload ocioso ocorra no meio de uma transcrição.
- `unload_models(force=True)` é usado no shutdown.

### 3. Máquina de estados determinística
```
IDLE ──press──▶ LISTENING ──release──▶ PROCESSING ──▶ INJECTING ──▶ IDLE
  ▲                                                │
  └──────────── toggle / erro / áudio curto ───────┘
```
Não existe estado `ERROR`: falhas exibem um badge de erro no overlay e retornam a `IDLE` (ou `DISABLED`).

### 4. Concorrência controlada, sem asyncio
- O pipeline é **síncrono** e executa em um `ThreadPoolExecutor(max_workers=1)`.
- Callbacks de hotkey chegam na thread do listener do `keyboard`.
- Chunks de áudio chegam na thread de callback do `sounddevice`.
- O overlay enfileira ações e só toca widgets Tk na thread principal (`_poll_queue`).
- Toda mudança de estado é protegida por `threading.RLock`.

### 5. Injeção de dependências
- Componentes aceitam implementações alternativas via construtor (`gpu_manager`, `audio_capture`, `pipeline`, `injector`, `hotkey`, `overlay`, `tray`, `executor`).
- Os testes usam fakes definidos em `tests/conftest.py`.

---

## Fluxo de Dados Detalhado (hold mode)

```
1. Usuário PRESSIONA Ctrl+Shift+Espaço
   └─▶ HotkeyManager (thread do keyboard)
       └─▶ Controller.on_hotkey_press()
           ├─▶ State: IDLE → LISTENING
           ├─▶ AudioCapture.start()
           └─▶ Overlay: "Ouvindo" + waveform + cronômetro

2. sounddevice callback
   └─▶ AudioBuffer.append(chunk)

3. Usuário SOLTA a tecla
   └─▶ Controller.on_hotkey_release()
       ├─▶ AudioCapture.stop()
       ├─▶ duração < 0.3 s? → IDLE
       ├─▶ AudioBuffer.consume() → np.ndarray float32 mono
       ├─▶ State: LISTENING → PROCESSING
       ├─▶ Overlay: "Processando…"
       └─▶ executor.submit(_process_worker, audio, generation)

4. _process_worker (thread única)
   ├─▶ Pipeline.process(audio)
   │   ├─▶ WhisperEngine.transcribe()  (GPUManager.ensure_loaded)
   │   ├─▶ GrammarCorrector.correct()
   │   └─▶ cleanup_text()
   ├─▶ token de geração ainda válido?
   ├─▶ State: PROCESSING → INJECTING
   ├─▶ TextInjector.inject(texto)
   └─▶ State: INJECTING → IDLE (ou DISABLED, se desativado no meio)

5. Overlay: check verde + prévia do texto (auto-hide em 1,2 s)
```

> O modelo **não** é descarregado após cada frase. O unload acontece após o timeout de ociosidade, ao desativar o assistente ou no shutdown.

---

## Módulos Principais

| Módulo | Arquivo | Responsabilidade |
|--------|---------|------------------|
| **Config** | `config/settings.py` | Pydantic Settings, `.env`, validação |
| **Constants** | `config/constants.py` | Paths, defaults, limites |
| **Controller** | `core/controller.py` | Orquestração e máquina de estados |
| **States** | `core/states.py` | `AppState` e transições válidas |
| **GPU Manager** | `core/gpu_manager.py` | Lazy load, uso ativo, unload ocioso |
| **Audio Capture** | `audio/capture.py` | Stream sounddevice + callback |
| **Audio Buffer** | `audio/buffer.py` | Acumulação thread-safe de chunks |
| **Whisper Engine** | `transcription/whisper_engine.py` | Wrapper faster-whisper + fallback CUDA→CPU |
| **Grammar** | `transcription/grammar.py` | LanguageTool + limpeza básica |
| **Java Runtime** | `transcription/java_runtime.py` | Descoberta/baixa de JRE 17+ |
| **Pipeline** | `transcription/pipeline.py` | Whisper → gramática → texto final |
| **Hotkey** | `input/hotkey.py` | Hooks globais + debounce |
| **Injector** | `input/injector.py` | Clipboard/Ctrl+V e SendInput |
| **Overlay** | `ui/overlay.py` | Pílula tkinter sempre no topo |
| **Tray** | `ui/tray.py` | Ícone e menu pystray |
| **Startup** | `startup/windows.py` | `HKCU\Run` |
| **Main** | `main.py` | CLI, single instance, wiring |

---

## Modelo de Threads

```
┌──────────────────────────── MAIN THREAD (Tk) ────────────────────────────┐
│ OverlayWindow (Tk mainloop) · bootstrap · shutdown                       │
└───────────────▲───────────────────────────────▲──────────────────────────┘
                │ queue de ações                │ callbacks
┌───────────────┴──────────────┐   ┌────────────┴──────────────────────────┐
│ keyboard listener thread     │   │ sounddevice callback thread           │
│ HotkeyManager                │   │ AudioBuffer.append                    │
└───────────────┬──────────────┘   └───────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────────────────┐
│ ThreadPoolExecutor(max_workers=1) — whisper → grammar → injection       │
└──────────────────────────────────────────────────────────────────────────┘
```

**Regras de thread safety**
- `AudioBuffer` usa `threading.Lock` interno.
- `Controller` usa `RLock` e um contador `_generation` para invalidar ditados.
- `OverlayWindow` recebe ações por `queue.Queue` e as executa no thread Tk.
- `GPUManager` usa `RLock` e um contador `_active_uses`.

---

## Memória

| Situação | VRAM aproximada | Observação |
|----------|-----------------|------------|
| Sem modelo carregado | ~0 MB (do app) | Estado inicial / após cada ditado |
| Modelo carregado (`int8_float16`) | ~2,8 GB | Apenas durante o ditado (ou janela aquecida opcional) |
| Durante inferência | ~2,8–3,2 GB | Depende do modelo/duração |
| LanguageTool (JVM) | ~200–500 MB RAM | Processo Java separado (CPU) |

O `torch` é **opcional**: se estiver instalado, `torch.cuda.empty_cache()` é chamado no unload; caso contrário, o app apenas descarta as referências e chama `gc.collect()`.

---

## Performance esperada (RTX 3060 12 GB)

| Métrica | Valor típico |
|---------|--------------|
| Primeira carga do modelo | 10–20 s (inclui download na primeira vez) |
| Transcrição de 5 s de áudio | 0,8–1,5 s |
| Correção gramatical | 100–300 ms |
| Injeção de texto | 10–30 ms |
| Recarga após idle | ~3–5 s (modelo já em cache) |

---

## Limitações conhecidas

1. **Apps elevados (Admin/UAC)**: injeção pode falhar; o fallback de clipboard → digitação não contorna elevação.
2. **CUDA**: requer cuBLAS/cuDNN compatíveis; sem isso o app cai para CPU.
3. **Java 17+**: necessário para LanguageTool; o app pode baixar um JRE portátil.
4. **LanguageTool**: a primeira inicialização pode levar dezenas de segundos.
5. **Somente Windows**: hooks globais, `SendInput`, registro e overlay usam APIs do Windows.
