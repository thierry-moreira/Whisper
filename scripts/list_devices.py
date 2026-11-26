"""List audio input devices and CUDA availability.

Usage:
    py -3.12 scripts/list_devices.py
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    try:
        import sounddevice as sd
    except Exception as exc:
        print(f"sounddevice indisponível: {exc}")
        return 1

    try:
        default_input = sd.default.device[0]
    except Exception:
        default_input = None

    print("Dispositivos de entrada:")
    found = 0
    for index, device in enumerate(sd.query_devices()):
        if int(device.get("max_input_channels", 0)) <= 0:
            continue
        found += 1
        marker = "  <- padrão" if index == default_input else ""
        rate = float(device.get("default_samplerate", 0.0))
        print(
            f"  [{index:>2}] {device.get('name', '?')} "
            f"({device.get('max_input_channels')} ch @ {rate:.0f} Hz){marker}"
        )
    if not found:
        print("  (nenhum dispositivo de entrada encontrado)")

    print()
    try:
        import ctranslate2

        count = ctranslate2.get_cuda_device_count()
        print(f"Dispositivos CUDA (CTranslate2): {count}")
    except Exception as exc:
        print(f"Verificação CUDA falhou: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
