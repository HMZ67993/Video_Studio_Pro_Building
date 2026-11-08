# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — preview audio.

Headless part (testable): `audio_signature` detects when the audible content of the project changed and
`render_preview_wav` mixes the whole timeline to a temporary WAV with FFmpeg (same graph as the export).
Qt part: `PreviewAudio` plays that WAV with QMediaPlayer, seeking to the playhead and re-syncing on drift.
Everything degrades silently (no FFmpeg / no multimedia backend -> preview stays silent, the editor keeps working).
"""

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from video_studio_ffmpeg import audible_clips, build_audio_mix

# Keep a strong Python reference to any render QThread that takes longer than the
# normal shutdown grace period. Qt aborts the process if a live QThread wrapper is
# destroyed, so this registry outlives a closing PreviewAudio owner when necessary.
_LIVE_RENDER_THREADS: set[Any] = set()
_LIVE_RENDER_THREADS_LOCK = __import__("threading").RLock()


def audio_signature(project: Any) -> str:
    """Stable hash of everything that influences the mixed audio (clip fields + source file mtimes)."""
    rows = []
    for c in audible_clips(project):
        try:
            mtime = os.path.getmtime(c.source_path)
        except OSError:
            mtime = 0
        rows.append([c.id, c.source_path, mtime, round(c.timeline_start, 3), round(c.duration, 3), round(c.source_in, 3),
                     round(c.source_out, 3), c.speed, c.reverse, c.volume_db, c.fade_in, c.fade_out, c.pitch_semitones, c.eq_preset,
                     tuple(sorted((k, tuple((round(x.time_offset, 4), round(x.value, 4), x.easing) for x in v)) for k, v in c.keyframes.items()))])
    rows.append([round(project.total_duration(), 3), bool(getattr(project, "auto_ducking", False)), round(float(getattr(project, "ducking_amount_db", 12.0)), 2)])
    return hashlib.sha1(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()


def render_preview_wav(project: Any, ffmpeg: str, out_path: Path, cancel: Optional[Callable[[], bool]] = None) -> bool:
    """Mix the audible clips into `out_path` (44.1 kHz stereo WAV). Returns False if there is nothing to play."""
    dur = max(0.5, project.total_duration())
    mix = build_audio_mix(project, ffmpeg, dur, first_input_index=0)
    if mix is None:
        return False
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostdin", *mix["inputs"], "-filter_complex", mix["filter"],
           "-map", mix["label"], "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", "-t", f"{dur:.3f}", str(out_path)]
    if cancel and cancel():
        return False
    flags = 0x08000000 if os.name == "nt" else 0
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    while True:
        try:
            proc.wait(timeout=0.2)
            break
        except subprocess.TimeoutExpired:
            if cancel and cancel():
                proc.kill()
                proc.wait()
                return False
    return proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0


def _try_unlink(path: Path) -> bool:
    """Delete a temporary file without propagating transient Windows lock errors."""
    try:
        path.unlink(missing_ok=True)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        # In particular, Windows raises PermissionError/WinError 32 while a media
        # backend still owns the file. The caller can retry after releasing it.
        return False


try:  # ---------------------------------------------------------------- Qt part
    from PyQt6.QtCore import QObject, QThread, QTimer, QUrl, pyqtSignal

    class _RenderThread(QThread):
        done = pyqtSignal(bool, str)

        def __init__(self, project: Any, ffmpeg: str, out: Path, signature: str):
            super().__init__()
            self.project, self.ffmpeg, self.out, self.signature = project, ffmpeg, out, signature
            self._stop = False

        def stop(self) -> None:
            self.requestInterruption()

        def run(self) -> None:
            try:
                ok = render_preview_wav(
                    self.project, self.ffmpeg, self.out,
                    cancel=self.isInterruptionRequested,
                )
            except Exception:
                ok = False
            self.done.emit(ok and not self.isInterruptionRequested(), self.signature)

    def _release_render_thread(thread: Any) -> None:
        with _LIVE_RENDER_THREADS_LOCK:
            _LIVE_RENDER_THREADS.discard(thread)


    class PreviewAudio(QObject):
        """Plays the mixed project audio in sync with the playhead."""

        status = pyqtSignal(str)  # "preparing" | "ready" | "none" | "unavailable"

        def __init__(self, get_project: Callable[[], Any], get_ffmpeg: Callable[[], Optional[str]], parent: Optional[QObject] = None):
            super().__init__(parent)
            self._get_project, self._get_ffmpeg = get_project, get_ffmpeg
            self._dir = Path(tempfile.mkdtemp(prefix="hmz_preview_"))
            self._signature = ""
            self._rendered_signature = ""
            self._wav: Optional[Path] = None
            self._thread: Optional[_RenderThread] = None
            self._want_play = False
            self._want_pos = 0.0
            self._player: Any = None
            self._output: Any = None
            self._available = True
            self._volume = 1.0
            # On Windows, QMediaPlayer may keep the previous WAV file open briefly
            # after setSource() changes. Retire old mixes asynchronously instead of
            # deleting them inside the render-completion callback.
            self._retired_wavs: set[Path] = set()
            self._retired_attempts: dict[Path, int] = {}
            self._cleanup_scheduled = False
            self._closing = False
            # QMediaPlayer/QAudioOutput are created on first playback, not at startup: it makes the window
            # appear sooner and a machine without an audio device can no longer break the launch.

        def _ensure_player(self) -> bool:
            if self._player is not None:
                return True
            if not self._available:
                return False
            try:
                from PyQt6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

                if not QMediaDevices.audioOutputs():
                    raise RuntimeError("no audio output device")
                self._player = QMediaPlayer(self)
                self._output = QAudioOutput(self)
                self._output.setVolume(self._volume)
                self._player.setAudioOutput(self._output)
                return True
            except Exception:
                self._player, self._output, self._available = None, None, False
                return False

        # ---- public API ----------------------------------------------------
        @property
        def available(self) -> bool:
            return self._available

        def set_volume(self, v: float) -> None:
            self._volume = max(0.0, min(1.0, v))
            if self._output is not None:
                self._output.setVolume(self._volume)

        def project_changed(self) -> None:
            """Call after any edit: if the audible content changed the cached mix is stale."""
            if not self._available:
                return
            try:
                self._signature = audio_signature(self._get_project())
            except Exception:
                self._signature = ""

        def play(self, position_sec: float) -> None:
            self._want_play, self._want_pos = True, position_sec
            if not self._available:
                self.status.emit("unavailable")
                return
            ffmpeg = self._get_ffmpeg()
            if not ffmpeg:
                self.status.emit("unavailable")
                return
            self.project_changed()
            if self._wav is not None and self._rendered_signature == self._signature:
                self._start(position_sec)
                return
            self._render(ffmpeg)

        def pause(self) -> None:
            self._want_play = False
            if self._player is not None:
                self._player.pause()

        def seek(self, position_sec: float) -> None:
            self._want_pos = position_sec
            if self._player is not None and self._want_play and self._wav is not None:
                self._player.setPosition(int(position_sec * 1000))

        def resync(self, position_sec: float, tolerance_ms: int = 220) -> None:
            if self._player is not None and self._want_play and self._wav is not None:
                if abs(self._player.position() - int(position_sec * 1000)) > tolerance_ms:
                    self._player.setPosition(int(position_sec * 1000))

        def shutdown(self) -> None:
            self._closing = True
            self.pause()
            if self._player is not None:
                try:
                    self._player.stop()
                    # Explicitly detach the local file before cleaning the temp folder.
                    self._player.setSource(QUrl())
                except Exception:
                    pass
            thread = self._thread
            if thread is not None:
                if thread.isRunning():
                    thread.stop()
                    finished = thread.wait(8000)
                else:
                    finished = True
                if not finished:
                    # Do not destroy a running QThread. Keep it alive until its
                    # interruptible FFmpeg subprocess has exited.
                    with _LIVE_RENDER_THREADS_LOCK:
                        _LIVE_RENDER_THREADS.add(thread)
                    thread.finished.connect(lambda t=thread: _release_render_thread(t))
                else:
                    with _LIVE_RENDER_THREADS_LOCK:
                        _LIVE_RENDER_THREADS.discard(thread)
            # QMediaPlayer can retain a Windows file handle until its event loop
            # processes the empty source. Cleanup is best-effort and never fatal.
            for f in self._dir.glob("*"):
                _try_unlink(f)
            try:
                self._dir.rmdir()
            except OSError:
                pass

        # ---- internals -------------------------------------------------------
        def _render(self, ffmpeg: str) -> None:
            if self._closing:
                return
            if self._thread is not None and self._thread.isRunning():
                return  # the running render finishes first; `_on_rendered` re-checks the signature
            out = self._dir / f"mix_{self._signature[:10]}.wav"
            self.status.emit("preparing")
            self._thread = _RenderThread(self._get_project().clone_for_export(), ffmpeg, out, self._signature)
            with _LIVE_RENDER_THREADS_LOCK:
                _LIVE_RENDER_THREADS.add(self._thread)
            self._thread.finished.connect(lambda t=self._thread: _release_render_thread(t))
            self._thread.done.connect(self._on_rendered)
            self._thread.start()

        def _on_rendered(self, ok: bool, signature: str) -> None:
            if self._closing:
                _try_unlink(self._dir / f"mix_{signature[:10]}.wav")
                return
            if not ok:
                old = self._wav
                self._wav = None
                if old is not None:
                    self._detach_player_source(old)
                    self._queue_wav_cleanup(old)
                failed_output = self._dir / f"mix_{signature[:10]}.wav"
                if failed_output != old:
                    self._queue_wav_cleanup(failed_output)
                self.status.emit("none")
                return
            old = self._wav
            self._wav = self._dir / f"mix_{signature[:10]}.wav"
            self._rendered_signature = signature

            # Switch/unload QMediaPlayer's source BEFORE retiring the old WAV. On
            # Windows the backend can hold an open handle, and Path.unlink() would
            # raise PermissionError (WinError 32) if called immediately.
            signature_is_current = self._signature == signature
            if signature_is_current and self._want_play:
                self._start(self._want_pos)
            elif old is not None and old != self._wav:
                self._detach_player_source(old)

            if old is not None and old != self._wav:
                self._queue_wav_cleanup(old)

            self.status.emit("ready")
            if not signature_is_current:  # edited while rendering -> render again
                ffmpeg = self._get_ffmpeg()
                if ffmpeg and self._want_play:
                    self._render(ffmpeg)
                return

        def _player_uses(self, path: Path) -> bool:
            if self._player is None:
                return False
            try:
                source = self._player.source()
                return bool(source.isLocalFile() and Path(source.toLocalFile()).resolve() == path.resolve())
            except Exception:
                return False

        def _detach_player_source(self, path: Path) -> None:
            """Release a retired preview file if QMediaPlayer still points to it."""
            if not self._player_uses(path):
                return
            try:
                self._player.stop()
                self._player.setSource(QUrl())
            except Exception:
                # Cleanup will retry later; this method must never crash the editor.
                pass

        def _queue_wav_cleanup(self, path: Path) -> None:
            if path == self._wav:
                return
            self._retired_wavs.add(path)
            self._retired_attempts.setdefault(path, 0)
            self._schedule_wav_cleanup(250)

        def _schedule_wav_cleanup(self, delay_ms: int = 500) -> None:
            if self._cleanup_scheduled or not self._retired_wavs:
                return
            self._cleanup_scheduled = True
            QTimer.singleShot(delay_ms, self._cleanup_retired_wavs)

        def _cleanup_retired_wavs(self) -> None:
            self._cleanup_scheduled = False
            for path in tuple(self._retired_wavs):
                if path == self._wav:
                    self._retired_wavs.discard(path)
                    self._retired_attempts.pop(path, None)
                    continue
                self._detach_player_source(path)
                if _try_unlink(path):
                    self._retired_wavs.discard(path)
                    self._retired_attempts.pop(path, None)
                    continue
                attempts = self._retired_attempts.get(path, 0) + 1
                self._retired_attempts[path] = attempts
                # A permanently locked file is harmless in the OS temp directory.
                # Stop retrying after ~30 attempts rather than running a timer forever.
                if attempts >= 30:
                    self._retired_wavs.discard(path)
                    self._retired_attempts.pop(path, None)
            if self._retired_wavs:
                # Back off gradually while the multimedia backend releases its handle.
                max_attempt = max(self._retired_attempts.values(), default=1)
                self._schedule_wav_cleanup(min(2000, 250 * max(1, max_attempt)))

        def _start(self, position_sec: float) -> None:
            if self._wav is None:
                return
            if not self._ensure_player():
                self.status.emit("unavailable")
                return
            if self._player.source() != QUrl.fromLocalFile(str(self._wav)):
                self._player.setSource(QUrl.fromLocalFile(str(self._wav)))
            self._player.setPosition(int(position_sec * 1000))
            self._player.play()

except ImportError:  # pragma: no cover - PyQt6 missing (headless tests)
    PreviewAudio = None  # type: ignore
