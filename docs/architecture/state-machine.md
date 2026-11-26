# State Machine - Máquina de Estados

## Estados da Aplicação

```python
# core/states.py
class AppState(Enum):
    IDLE = auto()        # aguardando hotkey (modelo descarregado)
    LISTENING = auto()   # capturando áudio
    PROCESSING = auto()  # whisper + gramática na worker thread
    INJECTING = auto()   # inserindo o texto no campo focado
    DISABLED = auto()    # assistente desativado (hotkeys ignoradas)
```

> **Não existe estado `ERROR`.** Erros são exibidos como badge vermelho no overlay e o controller retorna a `IDLE` (ou `DISABLED`).

## Diagrama de Transições

```
                 press
      ┌──────┐ ─────────▶ ┌───────────┐
      │ IDLE │            │ LISTENING │
      └──────┘ ◀───────── └─────┬─────┘
          ▲      áudio curto    │ release
          │                     ▼
          │              ┌────────────┐
          │              │ PROCESSING │
          │              └─────┬──────┘
          │                    │ texto não vazio
          │                    ▼
          │              ┌────────────┐
          └──────────────│ INJECTING  │
             sucesso/erro└────────────┘

  Qualquer estado ──toggle──▶ DISABLED
  DISABLED ──toggle──▶ IDLE
```

## Detalhes por Estado

### IDLE
- **Entrada**: startup, fim de injeção, áudio curto, erro recuperável, reativação.
- **Ações**: hotkey registrado, overlay oculto, modelo descarregado (recarrega no próximo atalho).
- **Saída**: press → `LISTENING`; toggle → `DISABLED`.

### LISTENING
- **Entrada**: press em hold mode ou primeiro press em toggle mode.
- **Ações**:
  - `AudioCapture.start()` → `sounddevice.InputStream`.
  - Overlay: ponto de gravação, waveform e cronômetro.
  - Timer de segurança (`MAX_RECORDING_SECONDS = 120 s`).
- **Saída**:
  - release + áudio ≥ 0,3 s → `PROCESSING`;
  - release + áudio < 0,3 s → `IDLE`;
  - toggle → `DISABLED` (captura é interrompida);
  - timeout de 120 s → processa o que foi capturado.

### PROCESSING
- **Entrada**: release com áudio válido ou auto-stop.
- **Ações**:
  - `AudioBuffer.consume()` → `np.ndarray` float32 mono.
  - Overlay: spinner + "Processando…".
  - `executor.submit(_process_worker, audio, generation)`.
- **Worker**:
  1. `Pipeline.process(audio)` → Whisper → gramática → `cleanup_text`.
  2. Verifica se o token de geração ainda é o atual.
  3. `PROCESSING → INJECTING` via `_try_transition`.
- **Saída**: texto vazio → `IDLE`; erro → `IDLE`/`DISABLED` + overlay de erro.

### INJECTING
- **Entrada**: transição atômica de `PROCESSING` bem-sucedida.
- **Ações**: `TextInjector.inject(texto)`.
- **Saída**: `_settle_after_injection()` → `IDLE` ou `DISABLED`.

### DISABLED
- **Entrada**: hotkey de toggle, menu do tray.
- **Ações**:
  - incrementa `_generation` (invalida ditados em andamento);
  - interrompe captura se estiver em `LISTENING`;
  - overlay oculto; ícone do tray muda;
  - `pipeline.release_gpu()` (unload imediato; adiado se houver transcrição ativa).
- **Saída**: toggle novamente → `IDLE`.

## Corrida `PROCESSING → DISABLED → INJECTING`

O controller resolve a corrida com três mecanismos:

1. **`_generation`** — incrementado ao iniciar um ditado e ao alternar enabled/disabled. A worker captura o valor e o compara antes de injetar.
2. **`_try_transition(expected, new)`** — só transiciona se o estado atual ainda for o esperado; nunca lança `StateTransitionError` na worker.
3. **`_settle_after_injection()`** — retorna a `IDLE` ou `DISABLED`, conforme o estado de `_enabled` no momento.

Assim, desativar o assistente durante a transcrição **descarta** o resultado em vez de digitá-lo.

## Callbacks

```python
# core/controller.py
class Controller:
    def on_hotkey_press(self) -> None: ...
    def on_hotkey_release(self) -> None: ...
    def toggle_enabled(self) -> None: ...
    def warmup(self) -> None: ...
```

`HotkeyCallbacks` é um dataclass com `on_press`, `on_release` e `on_toggle_enabled`.

## Transições válidas

| De → Para | Condição |
|-----------|----------|
| `IDLE → LISTENING` | press, app habilitado e estado `IDLE` |
| `LISTENING → PROCESSING` | release com áudio ≥ 0,3 s |
| `LISTENING → IDLE` | release com áudio curto |
| `LISTENING → DISABLED` | toggle durante a captura |
| `PROCESSING → INJECTING` | worker com texto e token válido |
| `PROCESSING → IDLE` | texto vazio ou erro |
| `INJECTING → IDLE` | injeção concluída com app habilitado |
| `INJECTING → DISABLED` | app desativado durante a injeção |
| `IDLE ↔ DISABLED` | toggle |
| `PROCESSING → DISABLED` | toggle durante a transcrição |

## Timeouts e limites

```python
# config/constants.py
MIN_RECORDING_SECONDS = 0.3       # descarta presses acidentais
MAX_RECORDING_SECONDS = 120       # auto-stop
HOTKEY_PRESS_DEBOUNCE_S = 0.15    # debounce de presses
OVERLAY_FPS_MS = 33               # ~30 fps
```

```python
# config/settings.py
overlay.always_show_on_success_ms = 1200   # auto-hide de sucesso/erro
whisper.idle_unload_seconds = 60           # unload do modelo
```

## Persistência de estado

- O estado da máquina **não** persiste entre reinícios (sempre inicia em `IDLE`).
- Configurações persistem em `.env`.
- Auto-start persiste em `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (valor `whisper_free`).
