# Guia de Troubleshooting

## Onde olhar primeiro

```bash
# Log em tempo real
Get-Content logs\whisper_free.log -Tail 50 -Wait

# Diagnóstico do ambiente
.venv\Scripts\python -m whisper_free --check

# Dispositivos de áudio e CUDA
.venv\Scripts\python scripts\list_devices.py
```

Em modo congelado, os logs ficam em `%LOCALAPPDATA%\Whisper Free\logs\whisper_free.log`.

Ative logs detalhados:

```bash
.venv\Scripts\python -m whisper_free --debug
```

ou:

```ini
WHISPER_FREE_LOG_LEVEL=DEBUG
```

---

## 1. GPU / CUDA

### "CUDA not available" / `cublas64_12.dll not found`

```
[ERROR] Library cublas64_12.dll is not found or cannot be loaded
```

**Causa**: driver NVIDIA/CUDA ausente ou DLLs fora do `PATH`.

**Solução**:

```powershell
# 1. Driver NVIDIA atualizado
nvidia-smi

# 2. Runtime CUDA via wheels (recomendado, sem Toolkit)
.venv\Scripts\python -m pip install -e ".[gpu]"

# 3. Alternativa: CUDA Toolkit 12.x com a pasta bin no PATH
$env:PATH -split ';' | Select-String cuda
```

Se não quiser instalar CUDA, o app cai automaticamente para CPU quando:

```ini
WHISPER_FREE_WHISPER__FALLBACK_TO_CPU=true
```

Antes de carregar o modelo, o app tenta carregar `cublas64_12.dll`. Se a DLL
não estiver disponível, ele já inicia em CPU/`int8` e registra:

```
CUDA runtime libraries are missing — falling back to CPU/int8.
```

Isso evita o estado `PROCESSING` travado que ocorria quando o modelo era
criado em CUDA mas a primeira codificação falhava.

### "CUDA out of memory"

```
[ERROR] CUDA out of memory. Tried to allocate 2.00 GiB
```

**Soluções**:

```ini
# Modelo menor
WHISPER_FREE_WHISPER__MODEL_SIZE=medium

# Quantização mais econômica
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8

# Liberar VRAM mais cedo
WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS=15
```

Feche jogos, Chrome com aceleração de GPU e outros processos CUDA. Verifique:

```bash
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

### GPU não detectada

```bash
.venv\Scripts\python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
```

Se retornar `0`, o problema é driver/CUDA — não é o Whisper Free. Sem GPU, use:

```ini
WHISPER_FREE_WHISPER__DEVICE=cpu
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8
WHISPER_FREE_WHISPER__MODEL_SIZE=small
```

### O modelo fica carregado e ocupa VRAM

Por padrão (`UNLOAD_AFTER_USE=true`), o modelo é descarregado assim que cada ditado termina — a VRAM volta ao normal em segundos. Para manter o modelo aquecido entre frases:

```ini
WHISPER_FREE_WHISPER__UNLOAD_AFTER_USE=false
WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS=60
```

> Não existem `GPU__UNLOAD_DELAY_S`, `GPU__MEMORY_FRACTION` ou `GPU__ENABLE_TF32`.

### `torch` não instalado

Não é erro. O `torch` é **opcional** e só habilita `torch.cuda.empty_cache()` no unload. Sem ele, o app descarta o modelo e chama `gc.collect()`.

```bash
# Opcional
.venv\Scripts\python -m pip install -e ".[gpu-cleanup]"
```

---

## 2. Áudio

### Nenhum dispositivo de entrada

```bash
.venv\Scripts\python scripts\list_devices.py
```

O app usa o dispositivo padrão do Windows quando `AUDIO__DEVICE` está vazio. Para escolher outro:

```ini
# Índice exibido pelo script
WHISPER_FREE_AUDIO__DEVICE=2

# Ou trecho do nome
WHISPER_FREE_AUDIO__DEVICE=Headset
```

### Áudio cortado, robótico ou com estalos

Ajuste o bloco de captura:

```ini
# Menor latência (mais chamadas de callback)
WHISPER_FREE_AUDIO__BLOCKSIZE=512

# Mais estável em máquinas lentas
WHISPER_FREE_AUDIO__BLOCKSIZE=2048
```

Taxa de amostragem esperada: **16000 Hz**, mono.

### Transcrição vazia ou "alucinações"

- Fale mais perto do microfone.
- Verifique o nível de entrada no Windows.
- Teste com `WHISPER_FREE_WHISPER__MODEL_SIZE=small` e `LANGUAGE=pt`.
- Desligue o VAD para diagnosticar:

```ini
WHISPER_FREE_WHISPER__VAD_FILTER=false
```

### Gravação muito longa é cortada

O limite é **120 segundos** (`MAX_RECORDING_SECONDS`). Ao atingi-lo, o controller processa o que foi capturado. Para ditados longos, divida em partes.

### Presses muito curtos são ignorados

Gravações menores que **0,3 s** são descartadas (`MIN_RECORDING_SECONDS`). Segure a tecla enquanto fala.

---

## 3. Hotkeys

### O atalho não faz nada

1. Verifique conflito com outro app (IDEs, gravadores, IME).
2. Teste outro atalho:

```ini
WHISPER_FREE_HOTKEY__TRIGGER=ctrl+shift+f1
```

3. Confirme que o app não está `DISABLED` (`Ctrl+Shift+F12` alterna).
4. Rode o app em um terminal para ver erros de registro.

### O atalho funciona, mas o caractere aparece no app focado

```ini
WHISPER_FREE_HOTKEY__SUPPRESS=true
```

O hotkey de toggle é registrado sem supressão, por design.

### `keyboard` exige administrador

Alguns apps elevados (UAC) não recebem hooks globais. Execute o Whisper Free no mesmo nível de privilégio do app alvo — ou evite apps elevados.

### Acentos/`Ctrl+V` não funcionam no app alvo

O modo padrão usa clipboard + `Ctrl+V`. Se o app bloqueia colar, ative o fallback:

```ini
WHISPER_FREE_INJECTOR__FALLBACK_TO_TYPE=true
```

Ou force digitação direta:

```ini
WHISPER_FREE_INJECTOR__MODE=type
```

> A injeção **não contorna elevação**. Se o app alvo roda como administrador, o Whisper Free também precisa rodar como administrador.

---

## 4. Injeção de texto

### Texto não aparece

1. Confirme que há um campo de texto focado.
2. Aumente a espera antes de injetar:

```ini
WHISPER_FREE_INJECTOR__PRE_INJECT_DELAY_S=0.15
```

3. Teste o modo `type`.
4. Verifique os logs: `InjectResult` registra `method` e `error`.

### Clipboard sobrescrito

```ini
WHISPER_FREE_INJECTOR__RESTORE_CLIPBOARD=true
```

O app salva e restaura o conteúdo anterior. Se o app alvo demorar a colar, aumente `PRE_INJECT_DELAY_S`.

### Caracteres faltando no modo `type`

Aumente o intervalo:

```ini
WHISPER_FREE_INJECTOR__CHAR_INTERVAL_S=0.005
```

### Acentos viram `?`

O modo `paste` preserva Unicode. No modo `type`, o `SendInput` usa eventos Unicode; apps que não aceitam Unicode podem perder caracteres. Prefira `paste`.

---

## 5. Gramática / Java

### "No compatible Java runtime (17+) found"

O LanguageTool 6.x exige **Java 17+**. O app rejeita Java 9–16.

```bash
# Verifique
java -version

# Deixe o app baixar um JRE portátil
WHISPER_FREE_GRAMMAR__AUTO_DOWNLOAD_JAVA=true
```

Ou instale o [Eclipse Temurin 17](https://adoptium.net/).

### LanguageTool demora muito na primeira frase

Esperado: o LanguageTool inicia junto com o app e faz warm-up automático; a primeira correção pode aguardar alguns segundos.

### Correção não aplica certas sugestões

Por segurança, o corretor aplica apenas categorias seguras (`TYPOS`, `GRAMMAR`, `PUNCTUATION`, `CASING`, `CONFUSED_WORDS`, `REDUNDANCY`, `COMPOUNDS`, `AGREEMENT`, `MISC`). Sugestões de estilo são ignoradas.

Para desligar:

```ini
WHISPER_FREE_GRAMMAR__ENABLED=false
```

### `timeout_seconds` não tem efeito

Correto: o campo existe em `GrammarSettings`, mas o `GrammarCorrector` atual não o repassa ao `language_tool_python`. Ele fica reservado para uso futuro.

---

## 6. Overlay

### Overlay não aparece

```ini
WHISPER_FREE_OVERLAY__ENABLED=true
```

E não inicie com `--no-overlay`.

### Overlay aparece no monitor errado

```ini
# top-center | center | bottom-center | mouse
WHISPER_FREE_OVERLAY__POSITION=bottom-center
```

O overlay usa a tela primária. Para seguir o cursor, use `mouse`.

### Overlay fica por cima de tudo

É intencional (`always-on-top`). Para ocultar temporariamente, use o menu do tray → **Overlay** ou `Ctrl+Shift+F12` para desativar o assistente.

### Overlay desatualizado após atualizar o código

Reinicie o processo. O app em execução mantém o código antigo carregado.

---

## 7. Inicialização com Windows

### O app não inicia com o Windows

```bash
# Verifique o registro
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v whisper_free
```

Ative novamente:

```bash
.venv\Scripts\python -m whisper_free --setup-startup
```

### Remover do autostart

```bash
.venv\Scripts\python -m whisper_free --remove-startup
```

Ou Gerenciador de Tarefas → Inicializar.

### Caminho antigo após mover a pasta

Desative e reative o autostart para regravar o caminho.

---

## 8. Configuração

### Valores do `.env` não são aplicados

- Prefixo correto: **`WHISPER_FREE_`**.
- Seções: **`__`** (dois underscores).
- Sem espaços ao redor do `=`.
- Reinicie o app — não há hot reload.
- Variáveis de ambiente reais têm precedência sobre o `.env`.

```ini
# Certo
WHISPER_FREE_WHISPER__MODEL_SIZE=medium

# Errado (formato antigo)
WHISPER__MODEL=medium
```

### Onde está o `.env`?

Em checkout/editable: raiz do projeto. Em bundle/wheel: `%LOCALAPPDATA%\Whisper Free\.env`. `WHISPER_FREE_HOME` sobrescreve a raiz.

### Configurações que não existem mais

`GPU__*`, `APP__*`, `LOGGING__*`, `OVERLAY__OPACITY` e `PIPELINE__THREAD_POOL_SIZE` não são lidos. Equivalentes atuais:

| Antigo | Atual |
|--------|-------|
| `GPU__UNLOAD_DELAY_S` | `WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS` |
| `LOGGING__LEVEL` | `WHISPER_FREE_LOG_LEVEL` |
| `OVERLAY__AUTO_HIDE_DELAY_MS` | `WHISPER_FREE_OVERLAY__ALWAYS_SHOW_ON_SUCCESS_MS` |

---

## 9. Desempenho

### Primeira transcrição lenta

Esperado: o modelo é carregado (e possivelmente baixado) na primeira vez. Não é preciso pré-carregar manualmente — o atalho dispara o carregamento.

### Recarga a cada ditado

Comportamento padrão: o modelo é descarregado ao fim de cada ditado para liberar a VRAM. Para mantê-lo aquecido:

```ini
WHISPER_FREE_WHISPER__UNLOAD_AFTER_USE=false
WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS=300
# 0 = nunca descarregar
```

### Transcrição lenta em CPU

```ini
WHISPER_FREE_WHISPER__MODEL_SIZE=small
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8
WHISPER_FREE_WHISPER__BEAM_SIZE=1
WHISPER_FREE_GRAMMAR__ENABLED=false
```

### Uso alto de CPU com o app ocioso

Verifique se o LanguageTool (processo Java) ficou ativo. Desative a gramática ou feche o app pelo tray.

---

## 10. Testes e desenvolvimento

### `pytest` não encontra `whisper_free`

```bash
.venv\Scripts\python -m pip install -e ".[dev]"
```

### Testes de integração não rodam

Eles são excluídos por `addopts`. Use:

```bash
.venv\Scripts\python -m pytest -m integration -v
```

### `ruff`/`black`/`mypy` falham no CI

Rode localmente na mesma ordem:

```bash
.venv\Scripts\ruff check src tests scripts
.venv\Scripts\black --check src tests scripts
.venv\Scripts\mypy src
```

### Erro `StateTransitionError` em log antigo

Corrigido: a worker usa `_try_transition` e um token de geração. Se aparecer, atualize o código e reinicie o app.

---

## 11. Coleta de diagnóstico para abrir uma issue

Inclua:

```bash
.venv\Scripts\python --version
.venv\Scripts\python -m whisper_free --check
.venv\Scripts\python -m pip list
nvidia-smi
```

E as últimas 50 linhas de `logs\whisper_free.log` com `WHISPER_FREE_LOG_LEVEL=DEBUG`.

> Remova caminhos pessoais, nomes de usuário e trechos de texto transcrito antes de publicar.
