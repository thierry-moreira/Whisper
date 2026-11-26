# Changelog

Todas as mudanças notáveis neste projeto são documentadas aqui.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e o projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Adicionado
- Overlay compacto em forma de pílula (`216×44`) ancorado em `bottom-center`, com ponto de gravação, waveform animado, cronômetro, spinner e badges de sucesso/erro.
- Fallback CUDA → CPU (`WHISPER_FREE_WHISPER__FALLBACK_TO_CPU`) com detecção de falhas de CUDA.
- Runtime CUDA 12 via wheels NVIDIA (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) no extra `[gpu]`, sem CUDA Toolkit no sistema.
- `UNLOAD_AFTER_USE` (padrão `true`): o modelo carrega no atalho e a VRAM é liberada ao fim de cada ditado.
- Fallback clipboard → digitação direta (`WHISPER_FREE_INJECTOR__FALLBACK_TO_TYPE`).
- Unload ocioso do modelo (`WHISPER_FREE_WHISPER__IDLE_UNLOAD_SECONDS`, padrão 60 s).
- Token de geração no controller para descartar ditados iniciados antes de um disable.
- Testes para `GPUManager`, `TranscriptionPipeline`, `WhisperEngine`, logging e fallback de injeção.
- Teste de integração real de `SendInput` (marcador `integration`).
- `LICENSE` MIT, `build/whisper_free.spec`, `build/whisper_free.iss`, workflows de CI/release, `.pre-commit-config.yaml`, `scripts/make_icon.py` e `scripts/list_devices.py`.

### Corrigido
- Corrida `PROCESSING → DISABLED → INJECTING` que podia lançar `StateTransitionError` ou injetar texto com o assistente desativado.
- `keyboard.remove_hotkey` agora recebe o callable retornado por `add_hotkey`; registro parcial é limpo em caso de erro.
- Java 9–16 não é mais aceito; LanguageTool 6.x exige Java 17+.
- `--silent` agora desliga apenas o sink de console; `pythonw` (sem `stderr`) não quebra o logging.
- `GPUManager.unload_models(force=True)` garante liberação no shutdown.
- CUDA é pré-validado antes de carregar o modelo: sem `cublas64_12.dll`, o app já inicia em CPU/`int8`; falhas de CUDA durante a transcrição também refazem o modelo em CPU, evitando o estado `PROCESSING` travado.
- `PROJECT_ROOT` funciona em checkout, instalação editável, wheel e bundle congelado; `WHISPER_FREE_HOME` permite override.
- Auto-start usa fallback `pythonw -m whisper_free --silent` quando o launcher `.pyw` não existe.
- `scripts/install.py` instala o pacote (`pip install -e .`) em vez de apenas requirements soltos.

### Mudado
- Modelo Whisper carrega sob demanda e é descarregado ao fim de cada ditado; `UNLOAD_AFTER_USE=false` restaura a janela aquecida.
- Menu do tray não expõe mais "Pré-carregar modelo"; o carregamento é automático no atalho.
- `pyautogui` removido das dependências; injeção usa `pyperclip` + `SendInput`.
- Testes de integração/GPU excluídos por padrão via `addopts`.

### Documentação
- README e guias alinhados à arquitetura real: tkinter + pystray, pipeline síncrono, sem PyQt6/asyncio/estado `ERROR`.
- Prefixo de ambiente corrigido para `WHISPER_FREE_`.
- Métricas de teste corrigidas para 176 testes e ~62% de cobertura global.

---

## [0.1.0] - 2026-11-01

### Adicionado
- **Core STT**: `faster-whisper` (CTranslate2) com CUDA e fallback CPU.
- **Modelo padrão**: `large-v3-turbo` com `int8_float16`.
- **Gramática local**: LanguageTool com JRE 17 portátil (Eclipse Temurin).
- **Pipeline**: Whisper → gramática → limpeza, executado em worker única.
- **GPU sob demanda**: carregamento na primeira transcrição e unload após ociosidade.
- **Overlay**: pílula tkinter always-on-top com estados de escuta, processamento, sucesso e erro.
- **Tray**: pystray com menu de ativação, overlay, configuração, logs, autostart e saída.
- **Hotkeys globais**: `keyboard` com debounce de 150 ms.
- **Injeção**: clipboard + `Ctrl+V` (padrão) e `SendInput` Unicode (alternativo).
- **Auto-start**: `HKCU\Run`.
- **Single instance**: mutex nomeado.
- **Configuração**: Pydantic Settings v2 com prefixo `WHISPER_FREE_`.
- **Logging**: loguru com rotação em `logs/whisper_free.log`.

### Qualidade
- 176 testes unitários; 2 testes de integração excluídos por padrão.
- Cobertura global ~62%; núcleo 84–93%.
- Ruff, Black e MyPy limpos.
- CI em `windows-latest` (Python 3.11 e 3.12).

---

## Convenções de versionamento

| Tipo | Formato | Exemplo |
|------|---------|---------|
| Major | X.0.0 | Breaking changes |
| Minor | 0.X.0 | Novas features compatíveis |
| Patch | 0.0.X | Correções |

## Links
- [GitHub Releases](https://github.com/seu-usuario/whisper-free/releases)
- [Issues](https://github.com/seu-usuario/whisper-free/issues)
- [Discussions](https://github.com/seu-usuario/whisper-free/discussions)
