"""Pre-download whisper models into ./models (one-time, speeds up first use).

Usage:
    py -3.12 scripts/download_models.py                  # configured model only
    py -3.12 scripts/download_models.py large-v3 medium  # specific models
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def main() -> int:
    from whisper_free.config.settings import load_settings

    settings = load_settings()
    targets = sys.argv[1:] or [settings.whisper.model_size]

    failures = 0
    for model_size in targets:
        print(f"\n→ Baixando modelo '{model_size}'...")
        try:
            from faster_whisper import WhisperModel

            WhisperModel(
                model_size,
                device=settings.whisper.device,
                compute_type=settings.whisper.compute_type,
                download_root=settings.whisper.model_dir,
            )
            print(f"  [OK] '{model_size}' pronto em {settings.whisper.model_dir}")
        except Exception as exc:
            print(f"  [FALHA] {model_size}: {exc}")
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
