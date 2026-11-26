# Referência - Atalhos de Teclado (Hotkeys)

## Hotkeys padrão

| Ação | Combinação | Modo | Descrição |
|------|------------|------|-----------|
| **Gravar (push-to-talk)** | `Ctrl` + `Shift` + `Espaço` | Hold | Segure para gravar, solte para transcrever |
| **Gravar via API OpenAI** | `Ctrl` + `Alt` + `Espaço` | Hold | Segure para gravar, solte para transcrever pela API |
| **Ativar/desativar app** | `Ctrl` + `Shift` + `F12` | Toggle | Alterna entre `IDLE` e `DISABLED` |

## Configuração

```ini
WHISPER_FREE_HOTKEY__MODE=hold
WHISPER_FREE_HOTKEY__TRIGGER=ctrl+shift+space
WHISPER_FREE_HOTKEY__CLOUD_TRIGGER=ctrl+alt+space
WHISPER_FREE_HOTKEY__TOGGLE_ENABLED=ctrl+shift+f12
WHISPER_FREE_HOTKEY__SUPPRESS=true
```

- `SUPPRESS=true` impede que a janela focada receba a combinação.
- O atalho da API (`CLOUD_TRIGGER`) usa o mesmo modo (hold/toggle) do atalho local, mas com debounce independente: soltar um nunca para o outro.
- O hotkey de ativar/desativar é registrado com `suppress=false` para continuar funcionando como atalho global.

## Formato

- Teclas separadas por `+`.
- Não sensível a maiúsculas: `CTRL+SHIFT+SPACE` = `ctrl+shift+space`.
- Espaços são removidos: `ctrl + shift + space` = `ctrl+shift+space`.
- Máximo de 4 teclas.
- A configuração é normalizada ao carregar o `.env`.

### Teclas suportadas

#### Modificadores
- `ctrl` / `control`
- `alt`
- `shift`
- `win` / `windows` / `super`

#### Teclas principais
- `space`, `enter` / `return`, `tab`, `esc` / `escape`
- `backspace`, `delete` / `del`, `insert` / `ins`
- `home`, `end`, `pageup`, `pagedown`
- `up`, `down`, `left`, `right`

#### Função
- `f1` até `f24`

#### Letras e números
- `a`–`z`, `0`–`9`

#### Especiais
- `capslock`, `numlock`, `scrolllock`
- `printscreen` / `prtsc`
- `pause` / `break`

## Exemplos

| Combinação | Observação |
|------------|------------|
| `ctrl+shift+space` | Padrão |
| `ctrl+alt+space` | Alternativa comum |
| `ctrl+shift+f1` | Boa para evitar conflito com IDEs |
| `alt+space` | Pode abrir o menu da janela |
| `ctrl+shift+alt+space` | 4 teclas (máximo) |
| `win+shift+s` | Conflita com a captura de tela do Windows |

## Conflitos comuns

| Hotkey | Conflito | Solução |
|--------|----------|---------|
| `win+shift+s` | Captura de tela | Evite |
| `ctrl+shift+s` | Salvar como | Evite |
| `ctrl+space` | IME | Evite |
| `alt+space` | Menu do sistema | Evite |
| `ctrl+shift+space` | Autocomplete em algumas IDEs | Funciona na maioria |

## Teste isolado

```python
import keyboard

hotkey = "ctrl+shift+space"
handle = keyboard.add_hotkey(hotkey, lambda: print(f"{hotkey} OK"))
print(f"{hotkey} registrado")
keyboard.remove_hotkey(handle)  # remove_hotkey aceita o callable retornado
```

> `keyboard.add_hotkey` retorna um **callable** removedor; passar uma string para `remove_hotkey` não funciona.

## Debounce

Presses duplicados dentro de **150 ms** são ignorados:

```python
# config/constants.py
HOTKEY_PRESS_DEBOUNCE_S = 0.15
```

## Hold vs Toggle

### Hold (padrão)

```
PRESSIONA → "Ouvindo" (grava)
SOLTA     → "Processando…" → check verde (insere texto)
```

### Toggle

```
1º press → "Ouvindo" (inicia gravação)
2º press → "Processando…" → check verde (para e transcreve)
```

```ini
WHISPER_FREE_HOTKEY__MODE=toggle
```

## Limite de gravação

O controller força o processamento após **120 segundos** (`MAX_RECORDING_SECONDS`). Gravações menores que **0,3 s** são descartadas.

## Desativação temporária

`Ctrl+Shift+F12` alterna:

- **Ativado** (`IDLE`): o hotkey principal funciona.
- **Desativado** (`DISABLED`): o hotkey principal é ignorado e o ícone do tray muda.

Útil ao jogar, em calls ou ao digitar código.

## Acessibilidade e limitações

- Hotkeys globais funcionam na maioria dos apps, mas **não garantem** atuação sobre janelas elevadas (Admin/UAC).
- A injeção de texto também pode falhar em apps elevados; o fallback clipboard → digitação não contorna a elevação.
- O overlay fornece feedback visual do estado atual.
- Feedback sonoro ainda não existe.
