"""Application entry point.

Responsibilities:
* parse CLI flags (``--silent``, ``--debug``, ``--setup-startup``, ...)
* enable per-monitor DPI awareness (crisp overlay on scaled displays)
* enforce single-instance behaviour
* build and wire the UI (overlay + tray) and the :class:`Controller`
* run the Tk main loop and perform an orderly shutdown afterwards
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import sys
import threading

from whisper_free.config.constants import APP_NAME, APP_VERSION
from whisper_free.config.settings import Settings, load_settings
from whisper_free.core.controller import Controller
from whisper_free.startup.windows import WindowsStartup
from whisper_free.utils.helpers import (
    acquire_single_instance_lock,
    is_windows,
    release_single_instance_lock,
)
from whisper_free.utils.logging import get_logger, setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="whisper-free", description=f"{APP_NAME} v{APP_VERSION}")
    parser.add_argument("--silent", action="store_true", help="start without any console output")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument("--no-tray", action="store_true", help="run without the system tray icon")
    parser.add_argument(
        "--no-overlay", action="store_true", help="run without the visual indicator"
    )
    parser.add_argument(
        "--setup-startup", action="store_true", help="enable auto-start with Windows and exit"
    )
    parser.add_argument(
        "--remove-startup", action="store_true", help="disable auto-start with Windows and exit"
    )
    parser.add_argument(
        "--check", action="store_true", help="check the environment (CUDA, audio, Java) and exit"
    )
    parser.add_argument(
        "--warmup", action="store_true", help="pre-load the whisper model into VRAM and exit"
    )
    return parser


def _enable_dpi_awareness() -> None:
    """Per-monitor-v2 DPI awareness so the overlay is sharp at any scale."""
    if not is_windows():
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
    except Exception:
        with contextlib.suppress(Exception):
            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]


def _build_controller(settings: Settings, args: argparse.Namespace) -> Controller:
    """Wire the controller with the optional overlay (main thread) and tray."""
    from whisper_free.ui.overlay import OverlayWindow
    from whisper_free.ui.tray import TrayCallbacks, TrayIcon

    overlay = None
    if settings.overlay.enabled and not args.no_overlay:
        overlay = OverlayWindow(settings.overlay)

    controller = Controller(settings, overlay=overlay)

    if not args.no_tray:
        tray = TrayIcon(
            TrayCallbacks(
                on_toggle_enabled=controller.toggle_enabled,
                on_toggle_overlay=controller.toggle_overlay,
                on_open_config=controller.open_config,
                on_configure_openai=controller.open_openai_settings,
                on_open_logs=controller.open_logs,
                on_toggle_autostart=controller.toggle_autostart,
                on_quit=controller.request_quit,
                is_enabled=lambda: controller.enabled,
                is_overlay_enabled=controller.is_overlay_enabled,
                is_autostart_enabled=controller.is_autostart_enabled,
                is_openai_configured=controller.is_openai_configured,
            )
        )
        controller.tray = tray
    return controller


def run_environment_check(settings: Settings) -> int:
    """Print a diagnostic report (used by ``--check`` and the installer)."""
    problems = 0
    print(f"\n=== {APP_NAME} v{APP_VERSION} — verificação de ambiente ===\n")

    # CUDA / CTranslate2
    try:
        import ctranslate2

        devices = ctranslate2.get_cuda_device_count()
        if devices > 0:
            print(f"[OK]   CUDA disponível — {devices} dispositivo(s) via CTranslate2")
            from whisper_free.transcription.whisper_engine import _cuda_runtime_available

            if _cuda_runtime_available():
                print("[OK]   cuBLAS/cuDNN carregados — GPU pronta para transcrição")
            else:
                print("[AVISO] cuBLAS/cuDNN ausentes — a transcrição usará CPU")
                problems += 1
        else:
            print("[AVISO] Nenhuma GPU CUDA detectada — a transcrição usará CPU (lenta)")
            problems += 1
    except Exception as exc:
        print(f"[FALHA] ctranslate2 não instalado: {exc}")
        problems += 1

    # faster-whisper
    try:
        import faster_whisper  # noqa: F401

        print("[OK]   faster-whisper instalado")
    except Exception as exc:
        print(f"[FALHA] faster-whisper não instalado: {exc}")
        problems += 1

    # Audio devices
    try:
        import sounddevice as sd

        inputs = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
        print(f"[OK]   Áudio: {len(inputs)} dispositivo(s) de entrada encontrado(s)")
    except Exception as exc:
        print(f"[FALHA] sounddevice/áudio indisponível: {exc}")
        problems += 1

    # Java (LanguageTool)
    from whisper_free.transcription.java_runtime import JavaRuntimeManager

    java = JavaRuntimeManager().find_java()
    if java is None:
        print("[AVISO] Java 17+ não encontrado — o JRE portátil será baixado no 1º uso")
    else:
        print(f"[OK]   Java {java.major_version} em {java.path}")

    # Keyboard / injection
    try:
        import keyboard  # noqa: F401

        print("[OK]   Biblioteca keyboard disponível")
    except Exception as exc:
        print(f"[FALHA] keyboard indisponível: {exc}")
        problems += 1

    print(
        f"\nModelo configurado: {settings.whisper.model_size} "
        f"({settings.whisper.device}, {settings.whisper.compute_type})"
    )
    print(f"Atalho local: {settings.hotkey.trigger} (modo {settings.hotkey.mode})")
    print(f"Atalho API: {settings.hotkey.cloud_trigger} (modelo {settings.openai.model})")
    print(
        "OpenAI: "
        + (
            "chave configurada"
            if settings.openai.api_key
            else "chave ausente — configure pelo menu do tray"
        )
    )
    print(
        f"Gramática: {'ativa' if settings.grammar.enabled else 'inativa'} "
        f"({settings.grammar.language})"
    )
    print(
        f"\nResultado: {'TUDO PRONTO' if problems == 0 else f'{problems} problema(s) encontrado(s)'}\n"
    )
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    """Program entry point. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    _enable_dpi_awareness()

    settings = load_settings()
    if args.debug:
        settings.log_level = "DEBUG"
    setup_logging(settings.log_level, console=not args.silent)
    logger = get_logger("whisper_free.main")
    logger.info(f"{APP_NAME} v{APP_VERSION} starting")

    # --- one-shot commands -------------------------------------------------
    if args.setup_startup:
        ok = WindowsStartup().enable()
        print("Inicialização com Windows ativada." if ok else "Falha ao ativar inicialização.")
        return 0 if ok else 1
    if args.remove_startup:
        ok = WindowsStartup().disable()
        print("Inicialização com Windows desativada." if ok else "Falha ao desativar.")
        return 0 if ok else 1
    if args.check:
        return run_environment_check(settings)
    if args.warmup:
        from whisper_free.core.gpu_manager import GPUManager
        from whisper_free.transcription.grammar import GrammarCorrector
        from whisper_free.transcription.java_runtime import JavaRuntimeManager
        from whisper_free.transcription.whisper_engine import WhisperEngine

        gpu = GPUManager(settings)
        WhisperEngine(settings, gpu).warmup()
        if settings.grammar.enabled:
            GrammarCorrector(settings, JavaRuntimeManager()).start()
        print("Modelos carregados com sucesso.")
        return 0

    # --- single instance -----------------------------------------------------
    if settings.single_instance and not acquire_single_instance_lock():
        logger.warning("Another instance is already running — exiting")
        return 0

    controller: Controller | None = None
    quit_event = threading.Event()
    try:
        controller = _build_controller(settings, args)
        original_quit = controller.request_quit

        def _quit_and_signal() -> None:
            original_quit()
            quit_event.set()

        if controller.tray is not None:
            # re-point the tray quit callback so headless mode also exits
            controller.tray._callbacks.on_quit = _quit_and_signal

        controller.start()
        if controller.tray is not None:
            controller.tray.start()

        if controller.overlay is not None:
            controller.overlay.run()  # blocks until quit
        else:
            while not quit_event.wait(0.5):
                pass
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as exc:
        logger.exception(f"Fatal error: {exc}")
        return 1
    finally:
        if controller is not None:
            controller.shutdown()
        release_single_instance_lock()
        logger.info("Exited cleanly")
    return 0


def cli_entry() -> None:
    """Console-script entry point (``whisper-free`` command)."""
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
