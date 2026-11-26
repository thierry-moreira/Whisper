"""Tests for Java discovery, version parsing and portable JRE download."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

from whisper_free.transcription.java_runtime import (
    JavaInfo,
    JavaRuntimeManager,
    _parse_major,
    probe_java,
)


class TestVersionParsing:
    def test_legacy_1_8(self):
        assert _parse_major("1.8.0_511") == 8

    def test_modern_17(self):
        assert _parse_major("17.0.9") == 17

    def test_modern_21(self):
        assert _parse_major("21.0.1") == 21

    def test_garbage(self):
        assert _parse_major("banana") == 0


class TestJavaInfo:
    def test_compatible_17(self):
        assert JavaInfo(path=Path("java"), major_version=17).is_compatible

    def test_compatible_21(self):
        assert JavaInfo(path=Path("java"), major_version=21).is_compatible

    def test_incompatible_9(self):
        assert not JavaInfo(path=Path("java"), major_version=9).is_compatible

    def test_incompatible_16(self):
        assert not JavaInfo(path=Path("java"), major_version=16).is_compatible

    def test_incompatible_8(self):
        assert not JavaInfo(path=Path("java"), major_version=8).is_compatible


class TestProbeJava:
    def test_parses_version_from_stderr(self):
        class FakeProc:
            stderr = 'openjdk version "17.0.9" 2023-10-17\n'
            stdout = ""

        with patch("subprocess.run", return_value=FakeProc()):
            info = probe_java("java")
        assert info is not None
        assert info.major_version == 17

    def test_returns_none_on_failure(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert probe_java("missing-java") is None

    def test_returns_none_when_no_version_string(self):
        class FakeProc:
            stderr = "no version here"
            stdout = ""

        with patch("subprocess.run", return_value=FakeProc()):
            assert probe_java("java") is None


class TestJavaRuntimeManager:
    def test_find_java_prefers_bundled(self, tmp_path):
        bundled = tmp_path / "jdk-17" / "bin"
        bundled.mkdir(parents=True)
        (bundled / "java.exe").write_bytes(b"fake")

        manager = JavaRuntimeManager(jre_dir=tmp_path)
        with patch(
            "whisper_free.transcription.java_runtime.probe_java",
            return_value=JavaInfo(path=bundled / "java.exe", major_version=17),
        ):
            found = manager.find_java()
        assert found is not None
        assert found.major_version == 17

    def test_find_java_ignores_incompatible_bundled(self, tmp_path):
        bundled = tmp_path / "jdk-11" / "bin"
        bundled.mkdir(parents=True)
        (bundled / "java.exe").write_bytes(b"fake")

        manager = JavaRuntimeManager(jre_dir=tmp_path)
        with (
            patch(
                "whisper_free.transcription.java_runtime.probe_java",
                return_value=JavaInfo(path=bundled / "java.exe", major_version=11),
            ),
            patch("shutil.which", return_value=None),
        ):
            assert manager.find_java() is None

    def test_find_java_falls_back_to_system(self, tmp_path):
        manager = JavaRuntimeManager(jre_dir=tmp_path / "empty")
        with (
            patch("shutil.which", return_value="C:/java/bin/java.exe"),
            patch(
                "whisper_free.transcription.java_runtime.probe_java",
                return_value=JavaInfo(path=Path("C:/java/bin/java.exe"), major_version=17),
            ),
        ):
            found = manager.find_java()
        assert found is not None
        assert found.major_version == 17

    def test_ensure_java_without_download_returns_none(self, tmp_path):
        manager = JavaRuntimeManager(jre_dir=tmp_path / "empty")
        with patch("shutil.which", return_value=None):
            assert manager.ensure_java(allow_download=False) is None

    def test_download_extracts_zip(self, tmp_path):
        # build a fake JRE zip with the expected folder layout
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("jdk-17.0.9-jre/bin/java.exe", "fake-binary")
        payload = buffer.getvalue()

        manager = JavaRuntimeManager(
            jre_dir=tmp_path / "jre",
            downloader=lambda url: payload,
        )
        with patch(
            "whisper_free.transcription.java_runtime.probe_java",
            return_value=JavaInfo(
                path=tmp_path / "jre" / "jdk-17.0.9-jre" / "bin" / "java.exe",
                major_version=17,
            ),
        ):
            info = manager.download_portable_jre()
        assert info is not None
        assert (tmp_path / "jre" / "jdk-17.0.9-jre" / "bin" / "java.exe").exists()

    def test_download_failure_returns_none(self, tmp_path):
        def broken(url):
            raise OSError("network down")

        manager = JavaRuntimeManager(jre_dir=tmp_path / "jre", downloader=broken)
        assert manager.download_portable_jre() is None


class TestApplyEnvironment:
    def test_path_modified(self, monkeypatch):
        info = JavaInfo(path=Path("C:/runtime/jre/bin/java.exe"), major_version=17)
        monkeypatch.setenv("PATH", "C:/Windows")
        JavaRuntimeManager.apply_environment(info)
        import os

        assert "C:/runtime/jre/bin" in os.environ["PATH"].replace("\\", "/")
        assert os.environ["JAVA_HOME"].endswith("jre")

    def test_none_is_noop(self, monkeypatch):
        monkeypatch.setenv("PATH", "C:/Windows")
        JavaRuntimeManager.apply_environment(None)
        import os

        assert os.environ["PATH"] == "C:/Windows"
