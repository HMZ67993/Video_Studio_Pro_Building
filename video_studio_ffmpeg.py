# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — FFmpeg integration (headless, no Qt):
  * locate ffmpeg (user-chosen path, app data folder, next to the EXE, PATH)
  * optional download of the official Windows "essentials" build with SHA-256 verification
  * probing (audio stream present? version, hardware encoders)
  * audio mixdown filter graph built from the project timeline (volume, fades, speed, reverse, pitch, EQ, delay)
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_ZIP_SHA256_URL = FFMPEG_ZIP_URL + ".sha256"
FFMPEG_DOWNLOAD_PAGE = "https://www.gyan.dev/ffmpeg/builds/"
SAMPLE_RATE = 44100

_CREATE_NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0


def _run(cmd: List[str], timeout: float = 30.0) -> Tuple[int, str]:
    """Run a command, return (returncode, stderr+stdout text). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=_CREATE_NO_WINDOW)
        return p.returncode, (p.stderr + p.stdout).decode("utf-8", errors="replace")
    except Exception as exc:  # missing binary, timeout, permission
        return -1, str(exc)


# ---------------------------------------------------------------------------
# Locate / install
# ---------------------------------------------------------------------------
def app_ffmpeg_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "ffmpeg"


def find_ffmpeg(data_dir: Path, configured: str = "") -> Optional[str]:
    """Return a usable ffmpeg executable path, or None."""
    candidates: List[Path] = []
    if configured:
        candidates.append(Path(configured))
    exe = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
    candidates.append(app_ffmpeg_dir(data_dir) / exe)
    try:
        candidates.append(Path(os.path.abspath(sys.argv[0])).parent / exe)
    except Exception:
        pass
    for c in candidates:
        try:
            if c.is_file():
                return str(c)
        except OSError:
            continue
    return shutil.which("ffmpeg")


def ffmpeg_version(path: str) -> Optional[Tuple[int, ...]]:
    """Parse `ffmpeg -version` -> e.g. (7, 0, 1). Returns None if the binary does not run."""
    rc, text = _run([path, "-version"], timeout=15)
    if rc != 0:
        return None
    m = re.search(r"ffmpeg version\D*(\d+)(?:\.(\d+))?(?:\.(\d+))?", text)
    if not m:
        return (0,)  # git builds ("N-12345-g...") are recent enough; treated as unknown/new
    return tuple(int(x) for x in m.groups() if x is not None)


def validate_ffmpeg(path: str) -> bool:
    return ffmpeg_version(path) is not None


def has_audio_stream(ffmpeg: str, media_path: str, _cache: Dict[str, bool] = {}) -> bool:  # noqa: B006 (intentional cache)
    key = f"{media_path}|{os.path.getmtime(media_path) if os.path.exists(media_path) else 0}"
    if key in _cache:
        return _cache[key]
    _rc, text = _run([ffmpeg, "-hide_banner", "-i", media_path], timeout=30)
    res = bool(re.search(r"Stream #\d+:\d+.*Audio:", text))
    _cache[key] = res
    return res


def detect_nvenc(ffmpeg: str) -> bool:
    """True only if h264_nvenc really encodes a frame on this machine (the encoder can be listed without a GPU)."""
    rc, text = _run([ffmpeg, "-hide_banner", "-encoders"], timeout=20)
    if rc != 0 or "h264_nvenc" not in text:
        return False
    rc, _ = _run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1", "-frames:v", "1",
                  "-c:v", "h264_nvenc", "-f", "null", "-"], timeout=30)
    return rc == 0


def download_ffmpeg(
    data_dir: Path,
    progress: Optional[Callable[[int], None]] = None,
    cancel: Optional[Callable[[], bool]] = None,
    zip_url: str = FFMPEG_ZIP_URL,
    sha_url: str = FFMPEG_ZIP_SHA256_URL,
) -> Tuple[bool, str]:
    """Download + verify (SHA-256 from the publisher) + extract only ffmpeg.exe into the app data folder.
    Returns (ok, path_or_error). Only https URLs are accepted."""
    if not zip_url.lower().startswith("https://") or not sha_url.lower().startswith("https://"):
        return False, "insecure url"
    dest_dir = app_ffmpeg_dir(data_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="hmz_ffmpeg_"))
    try:
        expected = ""
        try:
            with urllib.request.urlopen(urllib.request.Request(sha_url, headers={"User-Agent": "HMZ-VideoStudio"}), timeout=20) as r:
                m = re.search(r"\b([0-9a-fA-F]{64})\b", r.read(4096).decode("ascii", errors="ignore"))
                expected = m.group(1).lower() if m else ""
        except Exception as exc:
            return False, f"checksum download failed: {exc}"
        if not expected:
            return False, "checksum missing"
        zpath = tmp / "ffmpeg.zip"
        h = hashlib.sha256()
        req = urllib.request.Request(zip_url, headers={"User-Agent": "HMZ-VideoStudio"})
        with urllib.request.urlopen(req, timeout=30) as r, open(zpath, "wb") as out:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancel and cancel():
                    return False, "cancelled"
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress and total:
                    progress(min(95, int(done * 95 / total)))
        if h.hexdigest() != expected:
            return False, "checksum mismatch"
        return extract_ffmpeg_from_zip(zpath, dest_dir, progress)
    except Exception as exc:
        return False, str(exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def extract_ffmpeg_from_zip(zpath: Path, dest_dir: Path, progress: Optional[Callable[[int], None]] = None) -> Tuple[bool, str]:
    exe = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
    with zipfile.ZipFile(zpath) as z:
        member = next((n for n in z.namelist() if n.replace("\\", "/").endswith("/bin/" + exe) or n == exe), None)
        if member is None:
            return False, "ffmpeg not found in archive"
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        target = Path(dest_dir) / exe
        tmp_target = target.with_suffix(target.suffix + ".part")
        with z.open(member) as src, open(tmp_target, "wb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
        os.replace(tmp_target, target)
        try:
            target.chmod(target.stat().st_mode | 0o111)  # no-op on Windows, needed on POSIX
        except OSError:
            pass
    if progress:
        progress(100)
    if not validate_ffmpeg(str(target)):
        return False, "downloaded ffmpeg does not run"
    return True, str(target)


# ---------------------------------------------------------------------------
# Audio mixdown
# ---------------------------------------------------------------------------
def _atempo_chain(speed: float) -> List[str]:
    """atempo only accepts 0.5..2.0 per instance; chain for other values."""
    speed = max(0.1, min(100.0, speed))
    parts: List[str] = []
    while speed > 2.0:
        parts.append("atempo=2.0")
        speed /= 2.0
    while speed < 0.5:
        parts.append("atempo=0.5")
        speed /= 0.5
    parts.append(f"atempo={speed:.5f}")
    return parts


def clip_audio_chain(clip: Any) -> str:
    """Filter chain (without input/output labels) that turns a clip's source audio into its timeline audio,
    starting at t=0 of the clip. Everything is expressed in the clip's own timeline duration."""
    src_in = max(0.0, float(clip.source_in))
    src_out = max(src_in + 0.05, float(clip.source_out))
    f = [
        f"aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo",
        f"atrim=start={src_in:.4f}:end={src_out:.4f}",
        "asetpts=PTS-STARTPTS",
    ]
    if getattr(clip, "reverse", False):
        f.append("areverse")
    speed = float(getattr(clip, "speed", 1.0) or 1.0)
    if abs(speed - 1.0) > 0.01:
        f += _atempo_chain(speed)
    semis = float(getattr(clip, "pitch_semitones", 0.0) or 0.0)
    if abs(semis) > 0.1:
        factor = 2.0 ** (semis / 12.0)
        f += [f"asetrate={SAMPLE_RATE * factor:.2f}", f"aresample={SAMPLE_RATE}", *_atempo_chain(1.0 / factor)]
    dur = max(0.05, float(clip.duration))
    f.append(f"atrim=end={dur:.4f}")
    f.append("asetpts=PTS-STARTPTS")
    volume_kfs = getattr(clip, "keyframes", {}).get("volume_db", [])
    if volume_kfs:
        # Piecewise-linear dB automation evaluated on clip-local audio time.
        ordered = sorted(volume_kfs, key=lambda k: k.time_offset)
        expr = f"{float(ordered[-1].value):.4f}"
        for left, right in reversed(list(zip(ordered[:-1], ordered[1:]))):
            span = max(1e-6, float(right.time_offset) - float(left.time_offset))
            interp = f"({float(left.value):.4f}+({float(right.value)-float(left.value):.4f})*(t-{float(left.time_offset):.4f})/{span:.4f})"
            expr = f"if(lt(t,{float(right.time_offset):.4f}),{interp},{expr})"
        if float(ordered[0].time_offset) > 0:
            expr = f"if(lt(t,{float(ordered[0].time_offset):.4f}),{float(ordered[0].value):.4f},{expr})"
        f.append(f"volume='pow(10,({expr})/20)':eval=frame")
    elif abs(clip.volume_db) > 0.05:
        f.append(f"volume={clip.volume_db:.2f}dB")
    if clip.fade_in > 0.02:
        f.append(f"afade=t=in:st=0:d={min(clip.fade_in, dur):.3f}")
    if clip.fade_out > 0.02:
        d = min(clip.fade_out, dur)
        f.append(f"afade=t=out:st={max(0.0, dur - d):.3f}:d={d:.3f}")
    eq = getattr(clip, "eq_preset", "flat")
    from video_studio_core import EQUALIZER_PRESETS  # local import: avoids a cycle at module import time

    if eq in EQUALIZER_PRESETS and eq != "flat":
        for freq, gain in EQUALIZER_PRESETS[eq]:
            if gain:
                f.append(f"equalizer=f={freq}:width_type=o:width=2:g={gain}")
    delay_ms = int(round(max(0.0, clip.timeline_start) * 1000))
    f.append(f"adelay={delay_ms}|{delay_ms}")
    return ",".join(f)


def audible_clips(project: Any) -> List[Any]:
    """Clips that contribute sound: audio-track clips and video clips with their own audio, not muted."""
    out: List[Any] = []
    for trk in project.tracks:
        if trk.muted or trk.track_type == "text":
            continue
        for c in trk.clips:
            if c.muted or not c.source_path or c.is_freeze_frame:
                continue
            if c.clip_type == "audio" or (c.clip_type == "video" and trk.track_type == "video"):
                if c.clip_type == "video" and c.volume_db <= -59.0:
                    continue
                out.append(c)
    return out


def project_has_audio(project: Any, ffmpeg: Optional[str] = None) -> bool:
    """True if the timeline would produce sound. Without ffmpeg we cannot probe, so any candidate counts
    (video files usually carry audio) — used only to decide whether to ask the user to install FFmpeg."""
    for c in audible_clips(project):
        if not os.path.exists(c.source_path):
            continue
        if c.clip_type == "audio":
            return True
        if ffmpeg is None or has_audio_stream(ffmpeg, c.source_path):
            return True
    return False


def build_audio_mix(project: Any, ffmpeg: str, duration: float, first_input_index: int) -> Optional[Dict[str, Any]]:
    """Build a timeline mix. Optional auto-ducking uses video/dialogue audio as sidechain key."""
    ver = ffmpeg_version(ffmpeg) or (0,)
    new_amix = ver[0] == 0 or ver[0] >= 5
    inputs: List[str] = []
    chains: List[str] = []
    labels: List[str] = []
    voice_labels: List[str] = []
    music_labels: List[str] = []
    # Keep track metadata so only music beds are ducked; dialogue remains untouched.
    track_kind: Dict[str, str] = {}
    for trk in project.tracks:
        for clip in trk.clips:
            track_kind[clip.id] = "voice" if clip.clip_type == "video" or any(x in trk.name.lower() for x in ("voice", "dialog", "speech", "حوار", "كلام")) else "music"
    idx = first_input_index
    for c in audible_clips(project):
        if not os.path.exists(c.source_path):
            continue
        if c.clip_type == "video" and not has_audio_stream(ffmpeg, c.source_path):
            continue
        inputs += ["-i", c.source_path]
        label = f"a{idx}"
        chains.append(f"[{idx}:a]{clip_audio_chain(c)}[{label}]")
        labels.append(f"[{label}]")
        (voice_labels if track_kind.get(c.id) == "voice" else music_labels).append(f"[{label}]")
        idx += 1
    if not labels:
        return None
    if getattr(project, "auto_ducking", False) and voice_labels and music_labels:
        voice_key = "[hmzvoice]"
        if len(voice_labels) == 1:
            chains.append(f"{voice_labels[0]}anull{voice_key}")
        else:
            chains.append(f"{''.join(voice_labels)}amix=inputs={len(voice_labels)}:duration=longest:normalize=0{voice_key}")
        ducked = []
        threshold = 0.03
        ratio = max(2.0, min(20.0, float(getattr(project, "ducking_amount_db", 12.0)) / 2.0))
        for n, label in enumerate(music_labels):
            out = f"hmzduck{n}"
            chains.append(f"{label}{voice_key}sidechaincompress=threshold={threshold}:ratio={ratio:.2f}:attack=18:release=420[{out}]")
            ducked.append(f"[{out}]")
        mix_labels = ducked + voice_labels
    else:
        mix_labels = labels
    n = len(mix_labels)
    if n == 1:
        mix = f"{mix_labels[0]}apad=whole_dur={duration:.3f},atrim=end={duration:.3f},alimiter=limit=0.97[aout]"
    else:
        amix = f"amix=inputs={n}:duration=longest:dropout_transition=0:normalize=0" if new_amix else f"amix=inputs={n}:duration=longest:dropout_transition=0,volume={n}"
        mix = f"{''.join(mix_labels)}{amix},apad=whole_dur={duration:.3f},atrim=end={duration:.3f},alimiter=limit=0.97[aout]"
    return {"inputs": inputs, "filter": ";".join(chains + [mix]), "label": "[aout]"}


def decode_pcm_mono(ffmpeg: str, media_path: str, rate: int = 22050, max_seconds: float = 3600.0, start: float = 0.0, duration: Optional[float] = None) -> Optional["Any"]:
    """Decode any media's audio to float32 mono numpy array at `rate` Hz (used by beat detection / denoise / whisper)."""
    import numpy as np

    length = max_seconds if duration is None else min(max_seconds, duration)
    cmd = [ffmpeg, "-v", "error", "-nostdin"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", media_path, "-t", f"{length:.3f}", "-vn", "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=900, creationflags=_CREATE_NO_WINDOW)
    except Exception:
        return None
    if p.returncode != 0 or not p.stdout:
        return None
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


# ---------------------------------------------------------------------------
# Encoder arguments
# ---------------------------------------------------------------------------
QUALITY_CRF = {"high": 18, "balanced": 23, "compact": 28}


def video_encoder_args(quality: str = "balanced", use_gpu: bool = False, nvenc_ok: bool = False) -> List[str]:
    crf = QUALITY_CRF.get(quality, 23)
    if use_gpu and nvenc_ok:
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(crf + 2), "-b:v", "0", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "medium" if quality != "compact" else "faster", "-crf", str(crf), "-pix_fmt", "yuv420p"]
