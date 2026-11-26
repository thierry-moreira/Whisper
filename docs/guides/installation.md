# Guia de Instalação e Setup

## Requisitos

| Componente | Mínimo | Recomendado |
|------------|--------|-------------|
| **OS** | Windows 10 1909+ | Windows 11 22H2+ |
| **GPU** | Opcional (CPU funciona) | NVIDIA 8 GB+ / **RTX 3060 12 GB** |
| **RAM** | 8 GB | 16 GB+ |
| **CPU** | 4 cores (AVX2) | 8+ cores |
| **Disco** | 4 GB livres | SSD NVMe |
| **Python (dev)** | 3.11 | 3.12 |
| **CUDA (opcional)** | 12.x | 12.4+ |
| **Java (opcional)** | 17+ | JRE 17 portátil (auto) |

> O app **funciona sem GPU e sem Java instalado**. Sem GPU, a transcrição roda em CPU (`int8`). Sem Java, a correção gramatical degrada para limpeza básica — ou o app baixa um JRE portátil, se permitido.

---

## Opção 1 — Instalador (usuário final)

1. Baixe `WhisperFree-Setup-0.1.0.exe` em **GitHub Releases**.
2. Execute o instalador (não exige administrador; instala por usuário).
3. Escolha os atalhos e, se quiser, marque **"Iniciar com o Windows"**.
4. Abra pelo Menu Iniciar.

O instalador grava o autostart em:

```
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
  whisper_free = "<install>\WhisperFree.exe" --silent
```

## Opção 2 — Portable

1. Baixe `WhisperFree-win64.zip` em **GitHub Releases**.
2. Extraia para uma pasta gravável (ex.: `C:\Tools\WhisperFree`).
3. Execute `WhisperFree.exe`.

O portable mantém dados em `%LOCALAPPDATA%\Whisper Free` (modelos, logs, JRE). Para manter tudo junto da pasta do executável:

```powershell
$env:WHISPER_FREE_HOME = "C:\Tools\WhisperFree\data"
.\WhisperFree.exe
```

## Opção 3 — Código-fonte (desenvolvimento)

### 1. Python

Instale **Python 3.11 ou 3.12** (o projeto não suporta 3.13+):

```bash
py -3.12 --version
```

### 2. Ambiente virtual e dependências

```bash
git clone https://github.com/seu-usuario/whisper-free.git
cd whisper-free

py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[gpu,dev]"
```

Para habilitar a limpeza explícita de cache CUDA (opcional):

```bash
.venv\Scripts\python -m pip install -e ".[gpu-cleanup]"
```

O extra `[gpu]` instala o runtime CUDA 12 (cuBLAS + cuDNN 9) via wheels da NVIDIA. Em máquinas sem GPU NVIDIA, use `.[dev]` — o app cai para CPU automaticamente.

O `torch` **não é obrigatório**: sem ele o app ainda libera o modelo, apenas não chama `torch.cuda.empty_cache()`.

### 3. Verificação

```bash
.venv\Scripts\python -m whisper_free --check
```

Exemplo de saída saudável:

```
[OK]   CUDA disponível — 1 dispositivo(s) via CTranslate2
[OK]   cuBLAS/cuDNN carregados — GPU pronta para transcrição
[OK]   faster-whisper instalado
[OK]   Áudio: 19 dispositivo(s) de entrada encontrado(s)
[OK]   Java 17 em ...\runtime\jre\...\bin\java.exe
[OK]   Biblioteca keyboard disponível

Modelo configurado: large-v3-turbo (cuda, int8_float16)
Atalho: ctrl+shift+space (modo hold)
Gramática: ativa (pt-BR)

Resultado: TUDO PRONTO
```

### 4. Carregamento do modelo

Não é necessário pré-carregar: o modelo é baixado/carregado automaticamente no primeiro uso do atalho e descarregado ao fim do ditado. Para um teste isolado:

```bash
.venv\Scripts\python -m whisper_free --warmup
```

### 5. Executar

```bash
.venv\Scripts\python -m whisper_free
```

Ou pelo atalho sem console:

```bash
.venv\Scripts\pythonw.exe scripts\whisper_free_launcher.pyw
```

---

## Instalador assistido (`scripts/install.py`)

Alternativa ao passo a passo (usa o interpretador do `.venv`):

```bash
.venv\Scripts\python scripts\install.py --dev
```

Opções:

| Flag | Efeito |
|------|--------|
| `--dev` | instala `.[dev]` (testes, lint, mypy) |
| `--model large-v3-turbo` | pré-baixa o modelo |
| `--skip-java` | não baixa o JRE portátil |
| `--autostart` | ativa o início com Windows |

> O script instala no interpretador que o executa. Por isso, rode-o com `.venv\Scripts\python`, e não com `py -3.12`, para manter as dependências isoladas.

O script:

1. valida Python 3.11/3.12;
2. instala o pacote em modo editável (`pip install -e .`);
3. verifica CUDA (aviso, não erro);
4. opcionalmente baixa modelo e JRE;
5. opcionalmente registra o autostart.

---

## CUDA (opcional)

Para usar GPU:

1. Instale o driver NVIDIA mais recente.
2. Instale o **CUDA Toolkit 12.x** ou garanta que `cublas64_12.dll`/`cudnn` estejam no `PATH`:

```
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin
```

3. Verifique:

```bash
.venv\Scripts\python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
nvidia-smi
```

Se a inicialização CUDA falhar, o app tenta automaticamente CPU/`int8` (quando `WHISPER_FREE_WHISPER__FALLBACK_TO_CPU=true`, o padrão).

## Java / LanguageTool (opcional)

O LanguageTool 6.x exige **Java 17+**. O app:

1. procura `JAVA_HOME`, `java.exe` no `PATH` e JREs em `runtime/jre`;
2. rejeita versões 9–16;
3. se `WHISPER_FREE_GRAMMAR__AUTO_DOWNLOAD_JAVA=true`, baixa um **Temurin JRE 17** para `runtime/jre`.

Para baixar manualmente:

```bash
.venv\Scripts\python -c "from whisper_free.transcription.java_runtime import JavaRuntimeManager; print(JavaRuntimeManager().download_portable_jre())"
```

Para desligar a correção gramatical:

```ini
WHISPER_FREE_GRAMMAR__ENABLED=false
```

## Configuração

Copie o template:

```bash
copy .env.example .env
```

O prefixo é **`WHISPER_FREE_`** e o separador de seções é **`__`**:

```ini
WHISPER_FREE_WHISPER__MODEL_SIZE=large-v3-turbo
WHISPER_FREE_WHISPER__DEVICE=cuda
WHISPER_FREE_WHISPER__COMPUTE_TYPE=int8_float16
WHISPER_FREE_WHISPER__FALLBACK_TO_CPU=true
WHISPER_FREE_WHISPER__UNLOAD_AFTER_USE=true
WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS=60

WHISPER_FREE_HOTKEY__TRIGGER=ctrl+shift+space
WHISPER_FREE_GRAMMAR__ENABLED=true
WHISPER_FREE_OVERLAY__POSITION=bottom-center
WHISPER_FREE_LOG_LEVEL=INFO
```

Lista completa: [env-vars.md](../reference/env-vars.md).

## Auto-start

```bash
# Ativar
.venv\Scripts\python -m whisper_free --setup-startup

# Remover
.venv\Scripts\python -m whisper_free --remove-startup
```

Ou use o menu do tray. O valor do registro é `whisper_free`.

Em modo de desenvolvimento, o autostart usa `pythonw.exe` + `scripts\whisper_free_launcher.pyw`; se o launcher não existir, cai para `pythonw -m whisper_free --silent`.

## Primeiro uso

1. O modelo é baixado para `models/` (ou `%LOCALAPPDATA%\Whisper Free\models`).
2. O LanguageTool inicia o servidor Java na primeira correção (pode levar dezenas de segundos).
3. Segure `Ctrl+Shift+Espaço`, fale e solte.

## Atualização

### Instalador

Baixe e execute a nova versão; o instalador substitui os arquivos mantendo `.env` e dados do usuário.

### Código-fonte

```bash
git pull
.venv\Scripts\python -m pip install -e ".[gpu,dev]"
.venv\Scripts\python -m whisper_free --check
```

## Desinstalação

- **Instalador**: Configurações → Aplicativos → Whisper Free → Desinstalar.
- **Portable**: apague a pasta e, se quiser, `%LOCALAPPDATA%\Whisper Free`.
- **Autostart**: remova com `--remove-startup` ou pelo Gerenciador de Tarefas → Inicializar.

## Problemas de instalação

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| `requires-python >=3.11,<3.13` | Python 3.13+ | Use `py -3.12` |
| `No module named whisper_free` | pacote não instalado | `pip install -e .` |
| CUDA não detectada | driver/CUDA ausente | Funciona em CPU; instale CUDA 12.x para GPU |
| Java 17+ não encontrado | sem JRE compatível | Deixe `AUTO_DOWNLOAD_JAVA=true` ou instale Temurin 17 |
| Microfone não aparece | dispositivo padrão incorreto | `python scripts/list_devices.py` e ajuste `AUDIO__DEVICE` |
| Hotkey não funciona | conflito com outro app | Troque `HOTKEY__TRIGGER` |
