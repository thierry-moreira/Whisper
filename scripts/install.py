"""Installer / environment bootstrapper for Whisper Free.

Usage:
    py -3.12 -m venv .venv
    .venv\Scripts\python scripts/install.py --dev

What it does:
1. Verifies the Python version (3.11-3.12 required).
2. Verifies CUDA availability (warns when missing, does not fail).
3. Installs the package (and its dependencies) in editable mode.
4. Optionally pre-downloads the configured whisper model.
5. Optionally pre-downloads the portable JRE for LanguageTool.
6. Optionally enables auto-start with Windows.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC))

REQUIRED_PYTHON = (3, 11)
MAX_PYTHON = (3, 13)


def check_python() -> bool:
    version = sys.version_info
    print(f"Python: {version.major}.{version.minor}.{version.micro}")
    if version[:2] < REQUIRED_PYTHON or version[:2] >= MAX_PYTHON:
        print(
            f"ERRO: é necessário Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]} "
            f"até {MAX_PYTHON[0]}.{MAX_PYTHON[1] - 1} (atual: {version.major}.{version.minor})."
        )
        print("Dica: instale o Python 3.12 e execute com: py -3.12 scripts/install.py")
        return False
    return True


def install_package(dev: bool = False) -> bool:
    """Install Whisper Free in editable mode (``pip install -e .``)."""
    extras = ["gpu"] + (["dev"] if dev else [])
    target = f"{PROJECT_ROOT}[{','.join(extras)}]"
    print(f"\nInstalando o pacote em modo editável ({target})...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", target],
        check=False,
    )
    return result.returncode == 0


def check_cuda() -> None:
    print("\nVerificando CUDA...")
    try:
        import ctranslate2

        count = ctranslate2.get_cuda_device_count()
        if count > 0:
            print(f"  [OK] {count} dispositivo(s) CUDA detectado(s)")
        else:
            print("  [AVISO] Nenhuma GPU CUDA detectada. A transcrição usará CPU (lenta).")
            print("          Verifique se o driver NVIDIA está atualizado.")
    except Exception as exc:
        print(f"  [AVISO] Não foi possível verificar CUDA ainda: {exc}")


def download_model(model_size: str) -> bool:
    print(f"\nBaixando modelo Whisper '{model_size}' (pode levar alguns minutos)...")
    try:
        from whisper_free.config.settings import load_settings
        from whisper_free.transcription.whisper_engine import create_whisper_model

        settings = load_settings()
        settings.whisper.model_size = model_size
        create_whisper_model(settings)
        print(f"  [OK] Modelo '{model_size}' pronto")
        return True
    except Exception as exc:
        print(f"  [FALHA] {exc}")
        return False


def download_java() -> bool:
    print("\nVerificando Java para correção gramatical...")
    try:
        from whisper_free.transcription.java_runtime import JavaRuntimeManager

        manager = JavaRuntimeManager()
        found = manager.find_java()
        if found and found.is_compatible:
            print(f"  [OK] Java {found.major_version} encontrado em {found.path}")
            return True
        print("  Baixando JRE 17 portátil (~45 MB)...")
        downloaded = manager.download_portable_jre()
        if downloaded:
            print(f"  [OK] JRE portátil pronto em {downloaded.path}")
            return True
        print("  [AVISO] Não foi possível baixar o JRE — a correção gramatical usará modo básico.")
        return False
    except Exception as exc:
        print(f"  [AVISO] {exc}")
        return False


def enable_autostart() -> bool:
    print("\nAtivando inicialização com Windows...")
    try:
        from whisper_free.startup.windows import WindowsStartup

        ok = WindowsStartup().enable()
        print("  [OK] Ativada" if ok else "  [FALHA] Não foi possível ativar")
        return ok
    except Exception as exc:
        print(f"  [FALHA] {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Instalador do Whisper Free")
    parser.add_argument(
        "--dev", action="store_true", help="instalar dependências de desenvolvimento"
    )
    parser.add_argument("--model", default="", help="pré-baixar um modelo (ex.: large-v3-turbo)")
    parser.add_argument("--skip-java", action="store_true", help="não baixar o JRE portátil")
    parser.add_argument("--autostart", action="store_true", help="ativar início com Windows")
    args = parser.parse_args()

    print("=" * 60)
    print("  WHISPER FREE — Instalação")
    print("=" * 60)

    if not check_python():
        return 1
    if not install_package(dev=args.dev):
        print("ERRO: falha ao instalar o pacote.")
        return 1

    check_cuda()

    if args.model:
        download_model(args.model)
    if not args.skip_java:
        download_java()
    if args.autostart:
        enable_autostart()

    print("\n" + "=" * 60)
    print("  Instalação concluída!")
    print(f"  Para iniciar:  {sys.executable} -m whisper_free")
    print(f"  Verificação:   {sys.executable} -m whisper_free --check")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
