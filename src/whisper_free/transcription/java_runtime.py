"""Java runtime discovery / portable download for LanguageTool.

LanguageTool 6.x needs Java 17+.  This module:

1. Looks for a suitable ``java.exe`` (system PATH or a previously downloaded
   portable JRE under ``runtime/jre``).
2. Optionally downloads a portable Eclipse Temurin JRE 17 when none is found.
3. Exposes helpers to put that JRE first on PATH for the current process, so
   ``language_tool_python`` spawns the correct JVM.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from whisper_free.config.constants import JAVA_MIN_MAJOR, JRE_DIR, JRE_DOWNLOAD_URL
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.java")

_VERSION_RE = re.compile(r'version "(?P<version>[^"]+)"')


@dataclass
class JavaInfo:
    """Result of a java discovery attempt."""

    path: Path
    major_version: int

    @property
    def is_compatible(self) -> bool:
        """True for the Java 17+ runtime required by LanguageTool 6.x."""
        return self.major_version >= JAVA_MIN_MAJOR


def _parse_major(version_string: str) -> int:
    """Parse the Java version string into a major number (1.8 -> 8, 17.0.9 -> 17)."""
    parts = version_string.strip().split(".")
    try:
        if parts[0] == "1" and len(parts) > 1:
            return int(parts[1])
        return int(parts[0])
    except (ValueError, IndexError):
        return 0


def probe_java(java_exe: str | Path) -> JavaInfo | None:
    """Run ``java -version`` and parse the result; None when unusable."""
    try:
        proc = subprocess.run(
            [str(java_exe), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        logger.debug(f"java probe failed for {java_exe}: {exc}")
        return None
    output = (proc.stderr or "") + (proc.stdout or "")
    match = _VERSION_RE.search(output)
    if not match:
        return None
    major = _parse_major(match.group("version"))
    if major == 0:
        return None
    return JavaInfo(path=Path(java_exe), major_version=major)


class JavaRuntimeManager:
    """Finds or provisions a Java runtime for LanguageTool."""

    def __init__(
        self,
        jre_dir: Path | None = None,
        download_url: str = JRE_DOWNLOAD_URL,
        downloader: Callable[[str], bytes] | None = None,
    ) -> None:
        self._jre_dir = jre_dir or JRE_DIR
        self._download_url = download_url
        self._downloader = downloader or self._http_download

    # ------------------------------------------------------------- discovery
    def find_java(self) -> JavaInfo | None:
        """Return the best available Java, preferring the bundled JRE."""
        bundled = self._find_bundled()
        if bundled:
            if bundled.is_compatible:
                logger.debug(f"Using bundled JRE: {bundled.path} (v{bundled.major_version})")
                return bundled
            logger.warning(
                f"Bundled Java is version {bundled.major_version}; "
                f"LanguageTool needs Java {JAVA_MIN_MAJOR}+."
            )

        system = shutil.which("java")
        if system:
            info = probe_java(system)
            if info and info.is_compatible:
                logger.debug(f"Using system Java: {info.path} (v{info.major_version})")
                return info
            if info:
                logger.warning(
                    f"System Java is version {info.major_version}; "
                    f"LanguageTool needs Java {JAVA_MIN_MAJOR}+."
                )
        return None

    def ensure_java(self, allow_download: bool = True) -> JavaInfo | None:
        """Find a compatible Java or download a portable JRE 17."""
        found = self.find_java()
        if found and found.is_compatible:
            return found
        if not allow_download:
            return None
        return self.download_portable_jre()

    # -------------------------------------------------------------- download
    def download_portable_jre(self) -> JavaInfo | None:
        """Download + extract Temurin JRE 17 into ``runtime/jre``."""
        try:
            logger.info("Downloading portable JRE 17 (~45 MB, one time only)...")
            payload = self._downloader(self._download_url)
            self._jre_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                zf.extractall(self._jre_dir)
            logger.info(f"Portable JRE extracted to {self._jre_dir}")
        except Exception as exc:
            logger.error(f"Portable JRE download failed: {exc}")
            return None
        found = self._find_bundled()
        if not found:
            logger.error("Downloaded JRE could not be located after extraction")
        return found

    def _find_bundled(self) -> JavaInfo | None:
        if not self._jre_dir.exists():
            return None
        for java_exe in self._jre_dir.glob("*/bin/java.exe"):
            info = probe_java(java_exe)
            if info:
                return info
        return None

    @staticmethod
    def _http_download(url: str) -> bytes:
        import urllib.request

        with urllib.request.urlopen(url, timeout=180) as response:
            return response.read()

    # ------------------------------------------------------------- ambiente
    @staticmethod
    def apply_environment(info: JavaInfo | None) -> None:
        """Put the chosen java.exe first on PATH for this process tree."""
        if info is None:
            return
        java_bin = str(info.path.parent)
        current = os.environ.get("PATH", "")
        if java_bin.lower() not in current.lower():
            os.environ["PATH"] = java_bin + os.pathsep + current
            logger.debug(f"Prepended '{java_bin}' to PATH for LanguageTool")
        os.environ["JAVA_HOME"] = str(info.path.parent.parent)
