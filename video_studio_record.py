# -*- coding: utf-8 -*-
"""Microphone recording to a WAV file (QAudioSource, 44.1 kHz mono 16-bit). Qt only; degrades with a clear error."""

import wave
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices


class MicRecorder(QObject):
    failed = pyqtSignal(str)   # "no_device" | "no_data" | other error text
    finished = pyqtSignal(str)  # path of the finished WAV

    RATE = 44100

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._source: Optional[QAudioSource] = None
        self._io = None
        self._wav: Optional[wave.Wave_write] = None
        self._path: Optional[Path] = None
        self._bytes = 0

    @property
    def recording(self) -> bool:
        return self._source is not None

    def start(self, out_path: Path) -> bool:
        dev = QMediaDevices.defaultAudioInput()
        if dev.isNull():
            self.failed.emit("no_device")
            return False
        fmt = QAudioFormat()
        fmt.setSampleRate(self.RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not dev.isFormatSupported(fmt):
            fmt = dev.preferredFormat()
            if fmt.sampleFormat() != QAudioFormat.SampleFormat.Int16:
                self.failed.emit("unsupported_format")
                return False
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            self._wav = wave.open(str(out_path), "wb")
            self._wav.setnchannels(fmt.channelCount())
            self._wav.setsampwidth(2)
            self._wav.setframerate(fmt.sampleRate())
        except Exception as exc:
            self.failed.emit(str(exc))
            return False
        self._path, self._bytes = out_path, 0
        self._source = QAudioSource(dev, fmt, self)
        self._io = self._source.start()
        if self._io is None:
            self._cleanup()
            self.failed.emit("start_failed")
            return False
        self._io.readyRead.connect(self._on_data)
        return True

    def _on_data(self) -> None:
        if self._io is None or self._wav is None:
            return
        data = bytes(self._io.readAll())
        if data:
            self._wav.writeframes(data)
            self._bytes += len(data)

    def stop(self) -> None:
        if self._source is None:
            return
        self._on_data()
        path, got = self._path, self._bytes
        self._cleanup()
        if path is not None and got > 0:
            self.finished.emit(str(path))
        else:
            if path is not None:
                path.unlink(missing_ok=True)
            self.failed.emit("no_data")  # typically Windows microphone privacy setting is off

    def _cleanup(self) -> None:
        if self._source is not None:
            self._source.stop()
            self._source = None
        self._io = None
        if self._wav is not None:
            self._wav.close()
            self._wav = None
