"""Generate ``assets/icon.ico`` and ``assets/icon.png`` from the tray glyph."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PIL import Image  # noqa: E402

from whisper_free.ui.tray import build_icon_image  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]


def main() -> int:
    assets = ROOT / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    base = build_icon_image(True).resize((256, 256), Image.Resampling.LANCZOS)
    base.save(assets / "icon.png")
    base.save(assets / "icon.ico", sizes=[(size, size) for size in SIZES])
    print(f"Ícones gravados em {assets}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
