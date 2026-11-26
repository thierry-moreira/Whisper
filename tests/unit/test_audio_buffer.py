"""Tests for the thread-safe AudioBuffer."""

from __future__ import annotations

import threading

import numpy as np

from whisper_free.audio.buffer import AudioBuffer


class TestAppendAndRetrieve:
    def test_empty_buffer_returns_empty_float32(self):
        buf = AudioBuffer()
        audio = buf.get_audio()
        assert audio.dtype == np.float32
        assert audio.size == 0

    def test_int16_is_normalised_to_float32(self):
        buf = AudioBuffer(sample_rate=16_000)
        chunk = np.array([[16_384], [-32_768]], dtype=np.int16)  # 0.5 and -1.0
        buf.append(chunk)
        audio = buf.get_audio()
        assert audio.dtype == np.float32
        np.testing.assert_allclose(audio, [0.5, -1.0], atol=1e-4)

    def test_multiple_chunks_concatenated(self):
        buf = AudioBuffer()
        buf.append(np.ones((100, 1), dtype=np.int16))
        buf.append(np.ones((50, 1), dtype=np.int16))
        audio = buf.get_audio()
        assert audio.ndim == 1  # mono output for whisper
        assert audio.size == 150

    def test_stereo_downmixed(self):
        buf = AudioBuffer()
        stereo = np.array([[1000, 3000], [2000, 4000]], dtype=np.int16)
        buf.append(stereo)
        audio = buf.get_audio()
        # Mean of channels then normalised: (1000+3000)/2 = 2000, (2000+4000)/2 = 3000
        np.testing.assert_allclose(audio, [2000 / 32768, 3000 / 32768], atol=1e-6)

    def test_float32_clipped(self):
        buf = AudioBuffer()
        buf.append(np.array([[2.0], [-3.0]], dtype=np.float32))
        np.testing.assert_allclose(buf.get_audio(), [1.0, -1.0])

    def test_empty_chunk_ignored(self):
        buf = AudioBuffer()
        buf.append(np.zeros(0, dtype=np.int16))
        assert buf.is_empty


class TestDurationAndClear:
    def test_duration_seconds(self):
        buf = AudioBuffer(sample_rate=16_000)
        buf.append(np.zeros((8_000, 1), dtype=np.int16))
        assert buf.duration_s == 0.5

    def test_clear_resets(self):
        buf = AudioBuffer()
        buf.append(np.zeros((100, 1), dtype=np.int16))
        buf.clear()
        assert buf.is_empty
        assert buf.duration_s == 0.0

    def test_consume_returns_and_resets(self):
        buf = AudioBuffer()
        buf.append(np.ones((64, 1), dtype=np.int16))
        audio = buf.consume()
        assert audio.size == 64
        assert buf.is_empty

    def test_get_audio_preserves_contents(self):
        buf = AudioBuffer()
        buf.append(np.ones((64, 1), dtype=np.int16))
        assert buf.get_audio().size == 64
        assert buf.get_audio().size == 64  # still there


class TestThreadSafety:
    def test_concurrent_appends(self):
        buf = AudioBuffer()
        chunk = np.ones((100, 1), dtype=np.int16)

        def worker():
            for _ in range(50):
                buf.append(chunk)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert buf.get_audio().size == 4 * 50 * 100


class TestFlattenChannels:
    def test_mono_2d_flattened(self):
        mono = np.ones((10, 1), dtype=np.float32)
        assert AudioBuffer.flatten_channels(mono).ndim == 1

    def test_stereo_averaged(self):
        stereo = np.array([[1.0, 3.0]], dtype=np.float32)
        np.testing.assert_allclose(AudioBuffer.flatten_channels(stereo), [2.0])
