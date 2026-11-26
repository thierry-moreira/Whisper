# Guia de Build e Distribuição

## Visão Geral

O Whisper Free tem dois formatos de distribuição:

1. **Portable** — `dist/WhisperFree.exe` (PyInstaller one-file, sem instalação).
2. **Instalador** — `dist/WhisperFree-Setup-0.1.0.exe` (Inno Setup 6).

Ambos usam os mesmos arquivos-fonte:

| Arquivo | Papel |
|---------|-------|
| `build/whisper_free.spec` | receita do PyInstaller |
| `build/whisper_free.iss` | script do Inno Setup |
| `assets/icon.ico` | ícone do executável e do instalador |
| `assets/icon.png` | ícone PNG (tray) |

## Pré-requisitos

```bash
# Ambiente de desenvolvimento já configurado
.venv\Scripts\python -m pip install -e ".[dev]"

# PyInstaller (não é dependência de runtime)
.venv\Scripts\python -m pip install pyinstaller
```

Para o instalador, instale o **Inno Setup 6** e garanta que `ISCC.exe` esteja no `PATH`:

```
C:\Program Files (x86)\Inno Setup 6\ISCC.exe
```

## Build portable (PyInstaller)

Execute **da raiz do repositório**:

```bash
.venv\Scripts\pyinstaller --clean --noconfirm build/whisper_free.spec
```

Saída:

```
dist/
└── WhisperFree.exe
```

### O que o `.spec` faz

```python
ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
ASSETS = ROOT / "assets"

hiddenimports = [
    "ctranslate2", "faster_whisper", "language_tool_python",
    "pystray", "PIL", "keyboard", "pyperclip", "sounddevice",
    "numpy", "pydantic", "pydantic_settings", "loguru",
]

excludes = ["pytest", "tests", "tkinter.test"]
console = False
upx = True
```

- **one-file**: `EXE(...)` recebe `a.binaries` e `a.datas`, gerando um único `.exe`.
- **`console=False`**: nenhuma janela de console; logs vão para `logs/whisper_free.log`.
- **`assets/`** é embutido e extraído em tempo de execução.
- **`torch` não é hidden import**: é opcional e não deve ser empacotado por padrão.
- **`tkinter`** é incluído automaticamente pelo PyInstaller (necessário para o overlay).

### Tamanho e primeira execução

O executável tem dezenas de MB porque inclui Python, CTranslate2, NumPy e dependências. O **modelo Whisper não é embutido** — ele é baixado no primeiro uso para `models/` (ou para `%LOCALAPPDATA%\Whisper Free\models` em instalação congelada).

O **JRE também não é embutido**. Na primeira correção gramatical, o app procura Java 17+ e, se `GRAMMAR__AUTO_DOWNLOAD_JAVA=true`, baixa um Temurin JRE para `runtime/jre`.

## Build do instalador (Inno Setup)

Depois de gerar o `.exe`:

```bash
iscc build/whisper_free.iss
```

Ou, se o `ISCC` não estiver no `PATH`:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build\whisper_free.iss
```

Saída:

```
dist/
├── WhisperFree.exe
└── WhisperFree-Setup-0.1.0.exe
```

### O que o instalador faz

- Instala em `{autopf}\Whisper Free` (por usuário, `PrivilegesRequired=lowest`).
- Cria atalhos no Menu Iniciar e, opcionalmente, na área de trabalho.
- Oferece a tarefa **"Iniciar com o Windows"**, que grava:

```
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
  whisper_free = "<install>\WhisperFree.exe" --silent
```

- Idiomas: Português (Brasil) e Inglês.
- Desinstalador registrado no Windows.
- Ao final, oferece iniciar o aplicativo.

> O instalador **não** baixa modelos nem JRE; isso acontece no primeiro uso do app.

## Workflow de release

`.github/workflows/release.yml` é disparado por tags `v*` (ou manualmente):

```bash
git tag v0.1.0
git push origin v0.1.0
```

O workflow:

1. instala `.[dev]` + `pyinstaller`;
2. roda `pyinstaller --clean --noconfirm build/whisper_free.spec`;
3. compacta `dist/WhisperFree.exe` em `dist/WhisperFree-win64.zip`;
4. anexa o zip ao GitHub Release.

O **instalador Inno Setup não é gerado no CI** (o runner não traz o `ISCC` por padrão). Para publicar o instalador, compile-o localmente e anexe manualmente ao Release.

## Limpeza

```bash
# Remover artefatos
Remove-Item -Recurse -Force dist, build\WhisperFree -ErrorAction SilentlyContinue

# Rebuild completo
.venv\Scripts\pyinstaller --clean --noconfirm build/whisper_free.spec
```

> O PyInstaller cria uma pasta temporária `build/WhisperFree/` ao lado dos scripts. Ela é separada dos arquivos-fonte `build/whisper_free.spec` e `build/whisper_free.iss`.

## Ícones

```bash
.venv\Scripts\python scripts/make_icon.py
```

Gera `assets/icon.ico` (16–256 px) e `assets/icon.png` a partir do glifo desenhado no script.

## Verificação pós-build

```powershell
# 1. O executável inicia?
.\dist\WhisperFree.exe --check

# 2. O overlay aparece? Segure Ctrl+Shift+Espaço.
# 3. Os logs são gravados?
Get-Content "$env:LOCALAPPDATA\Whisper Free\logs\whisper_free.log" -Tail 30
```

Em modo congelado, os dados ficam em `%LOCALAPPDATA%\Whisper Free` (a menos que `WHISPER_FREE_HOME` seja definido).

## Troubleshooting

### `ModuleNotFoundError` ao rodar o `.exe`

Falta um hidden import. Adicione o pacote em `hiddenimports` no `.spec` e reconstrua.

### `tkinter` ausente

O Python do build precisa ter Tcl/Tk. Teste:

```bash
.venv\Scripts\python -c "import tkinter; print(tkinter.TkVersion)"
```

### Antivírus bloqueia o executável

Executáveis PyInstaller one-file são frequentemente sinalizados por heurística. Opções:

- assinar o binário com um certificado de code signing;
- distribuir em modo `onedir` (menos suspeito);
- enviar o binário para análise no fornecedor do antivírus.

### O instalador não encontra o `.exe`

Compile o PyInstaller **antes** do Inno Setup. O `.iss` referencia `..\dist\WhisperFree.exe`.

### Modelo/JRE não baixam no primeiro uso

Verifique firewall/proxy e os logs. Para pré-baixar antes de empacotar:

```bash
.venv\Scripts\python scripts/download_models.py
.venv\Scripts\python scripts/install.py --model large-v3-turbo
```
