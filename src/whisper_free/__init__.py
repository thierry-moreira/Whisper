"""Whisper Free — local, private speech-to-text with grammar correction.

A Windows desktop application that transcribes microphone speech in real time
using faster-whisper (CUDA), optionally corrects grammar/spelling with a local
LanguageTool server (pt-BR), and injects the resulting text into whatever
field has focus — triggered by a global hotkey.
"""

from whisper_free.config.constants import APP_NAME, APP_VERSION

__all__ = ["APP_NAME", "APP_VERSION"]
