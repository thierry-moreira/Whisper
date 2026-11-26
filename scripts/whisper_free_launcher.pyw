"""Windowless launcher used by the Windows auto-start entry (dev mode).

``pythonw.exe`` runs this file without a console window.  The package is
imported from ``src/`` so an editable install is not strictly required.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from whisper_free.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["--silent"]))
