# Documentação Técnica - Whisper Free

Bem-vindo à documentação técnica do **Whisper Free** — aplicação desktop Windows para ditado por voz com IA local.

## 📚 Índice da Documentação

### 🏗️ Arquitetura
- [Visão Geral da Arquitetura](architecture/overview.md)
- [Máquina de Estados](architecture/state-machine.md)
- [Gerenciamento de GPU](architecture/gpu-management.md)
- [Pipeline de Transcrição](architecture/pipeline.md)

### 🔌 API Reference
- [Configuração (Settings)](api/settings.md)

> Os demais módulos são documentados diretamente nos docstrings do código-fonte em [`src/whisper_free/`](../src/whisper_free/).

### 📖 Guias
- [Instalação e Setup](guides/installation.md)
- [Configuração Avançada](guides/configuration.md)
- [Desenvolvimento](guides/development.md)
- [Build e Distribuição](guides/build.md)
- [Testes](guides/testing.md)
- [Troubleshooting](guides/troubleshooting.md)

### 📋 Referência Rápida
- [Variáveis de Ambiente (.env)](reference/env-vars.md)
- [Atalhos de Teclado](reference/hotkeys.md)
- [Estrutura de Pastas](reference/folder-structure.md)
- [Changelog](reference/changelog.md)

---

## 🚀 Início Rápido

```bash
# 1. Clone e configure
git clone https://github.com/seu-usuario/whisper-free.git
cd whisper-free
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[gpu,dev]"

# 2. Baixe modelos (opcional — o primeiro uso baixa automaticamente)
.venv\Scripts\python scripts/download_models.py

# 3. Verifique o ambiente
.venv\Scripts\python -m whisper_free --check

# 4. Execute
.venv\Scripts\python -m whisper_free
```

---

## 🎯 Principais Características Técnicas

| Aspecto | Tecnologia | Detalhes |
|---------|------------|----------|
| **STT Engine** | faster-whisper (CTranslate2) | CUDA `int8_float16`, fallback CPU `int8` |
| **Grammar** | LanguageTool + Temurin JRE 17 | Servidor local, pt-BR |
| **Áudio** | sounddevice (PortAudio) | 16 kHz, mono, `int16` |
| **Hotkeys** | keyboard (boppreh) | Hooks globais, debounce de 150 ms |
| **Injeção** | pyperclip + `SendInput` | Clipboard/Ctrl+V com fallback para digitação |
| **UI** | tkinter Canvas + pystray | Overlay compacto e tray |
| **Config** | Pydantic Settings v2 | Prefixo `WHISPER_FREE_`, `__` para seções |
| **Logs** | loguru | Rotação em `logs/whisper_free.log` |
| **Testes** | pytest | 221 testes, ~64% global (84–94% no core) |

---

## 🔗 Links Úteis

- [README Principal](../README.md)
- [Código Fonte](../src/whisper_free/)
- [Testes](../tests/)
- [Scripts](../scripts/)
- [Configuração Exemplo](../.env.example)

---

*Documentação para Whisper Free v0.1.0.*
