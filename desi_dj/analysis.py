from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np

try:
    import soundfile as sf
except Exception:
    sf = None

try:
    import librosa
except Exception:
    librosa = None


INDIAN_GENRES = [
    "Bollywood Remix",
    "Punjabi",
    "Nashik Baja",
    "Tapori Mix",
    "Club Mix",
    "Garba / Dandiya",
    "Indie / Electronic",
    "House",
    "Hip Hop",
    "Rock",
    "Unknown",
]


def _load_audio_array(file_path: str):
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(file_path)

    if sf is not None:
        audio, sr = sf.read(str(path), always_2d=False)
        arr = np.asarray(audio, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr.mean(axis=1)
        return arr.astype(np.float32), int(sr)

    if path.suffix.lower() == ".wav":
        import wave
        with wave.open(str(path), "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            sr = wf.getframerate()
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)

        if sampwidth == 1:
            data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
            data = (data - 128) / 128.0
        elif sampwidth == 2:
            data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif sampwidth == 4:
            data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Unsupported WAV width: {sampwidth}")

        if channels > 1:
            data = data.reshape(-1, channels)
            data = data.mean(axis=1)

        return data.astype(np.float32), int(sr)

    raise RuntimeError("No supported audio decoder available. Install soundfile.")


def _rms_envelope(audio: np.ndarray, framesize: int = 2048, hop: int = 512) -> np.ndarray:
    if len(audio) < framesize:
        framesize = max(256, len(audio))
    if framesize <= 0:
        return np.array([0.0], dtype=np.float32)

    win = np.hanning(framesize)
    out = []
    for i in range(0, len(audio) - framesize + 1, hop):
        chunk = audio[i:i + framesize]
        if len(chunk) < framesize:
            chunk = np.pad(chunk, (0, framesize - len(chunk)))
        rms = np.sqrt(np.mean((chunk * win) ** 2))
        out.append(float(rms))
    if not out:
        out = [float(np.sqrt(np.mean(audio ** 2)))]
    return np.asarray(out, dtype=np.float32)


def _detect_bpm(audio: np.ndarray, sr: int) -> float:
    if len(audio) < 2048:
        return 0.0

    env = _rms_envelope(audio)
    if len(env) < 8:
        return 0.0

    onset = np.abs(np.diff(env))
    onset = np.maximum(onset, 0.0)
    if np.all(onset == 0):
        return 0.0

    min_bpm = 60
    max_bpm = 180
    min_lag = max(1, int(sr / (max_bpm / 60.0)))
    max_lag = max(min_lag + 1, int(sr / (min_bpm / 60.0)))

    corr = np.correlate(onset, onset, mode="full")[len(onset) - 1:]
    corr = corr[min_lag:max_lag]
    if len(corr) == 0:
        return 0.0

    best_idx = int(np.argmax(corr))
    lag = best_idx + min_lag
    if lag <= 0:
        return 0.0

    bpm = 60.0 * sr / float(lag)
    bpm = float(np.clip(bpm, 60.0, 180.0))
    return round(bpm, 2)


def _chroma(audio: np.ndarray, sr: int) -> np.ndarray:
    if librosa is not None:
        try:
            chroma = librosa.feature.chroma_cqt(y=audio, sr=sr, bins_per_octave=36)
            return chroma.mean(axis=1)
        except Exception:
            pass

    n_fft = min(4096, len(audio))
    if n_fft < 256:
        return np.zeros(12, dtype=np.float32)

    spec = np.fft.rfft(audio[:n_fft])
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    mag = np.abs(spec)
    chroma = np.zeros(12, dtype=np.float32)

    for i, freq in enumerate(freqs):
        if freq <= 0:
            continue
        midi = 69 + 12 * np.log2(freq / 440.0)
        idx = int(round(midi)) % 12
        chroma[idx] += mag[i]

    if np.sum(chroma) == 0:
        return np.zeros(12, dtype=np.float32)
    return chroma / np.sum(chroma)


def _detect_key(audio: np.ndarray, sr: int) -> str:
    chroma = _chroma(audio, sr)
    pitches = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88], dtype=np.float32)
    minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17], dtype=np.float32)

    scores = []
    for i in range(12):
        maj_score = float(np.dot(chroma, np.roll(major, -i)))
        min_score = float(np.dot(chroma, np.roll(minor, -i)))
        scores.append((i, "maj", maj_score))
        scores.append((i, "min", min_score))

    root_index, mode, _ = max(scores, key=lambda x: x[2])
    key_name = pitches[root_index]
    if mode == "min":
        return f"{key_name}m"
    return key_name


def _energy_score(audio: np.ndarray) -> float:
    if len(audio) == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float32)))))
    return float(np.clip(rms * 100.0, 0.0, 100.0))


def _section_map(audio: np.ndarray, sr: int) -> List[Dict[str, Any]]:
    env = _rms_envelope(audio, framesize=2048, hop=512)
    if len(env) < 2:
        return [{"label": "Full Track", "start": 0.0, "end": max(len(audio) / sr, 1.0)}]

    threshold = float(np.median(env) * 0.75) if np.any(env) else 0.0
    sections = []
    current_label = "Intro"
    current_start = 0.0
    last_change = 0.0

    for idx, level in enumerate(env):
        t = idx * 512 / sr
        if level > threshold:
            if current_label == "Intro" and (t - last_change) > 4.0:
                current_label = "Verse"
                last_change = t
            elif current_label == "Verse" and (t - last_change) > 10.0:
                current_label = "Chorus"
                last_change = t
            elif current_label == "Chorus" and (t - last_change) > 14.0:
                current_label = "Breakdown"
                last_change = t
        else:
            if (t - last_change) > 6.0 and current_label != "Outro":
                sections.append({"label": current_label, "start": current_start, "end": t})
                current_start = t
                current_label = "Outro"
                last_change = t

    final_end = len(audio) / sr
    if not sections:
        return [{"label": "Full Track", "start": 0.0, "end": final_end}]
    sections.append({"label": current_label, "start": current_start, "end": final_end})
    return sections[:8]


def _waveform_peaks(audio: np.ndarray, target_points: int = 220) -> List[float]:
    if len(audio) == 0:
        return [0.0] * target_points
    chunk_size = max(1, len(audio) // target_points)
    peaks = []
    for i in range(0, len(audio), chunk_size):
        seg = audio[i:i + chunk_size]
        if len(seg) == 0:
            continue
        peaks.append(float(np.max(np.abs(seg))))
    if len(peaks) < target_points:
        peaks = peaks + [0.0] * (target_points - len(peaks))
    return [float(x) for x in peaks[:target_points]]


def suggest_indian_genre(file_path: str, tags: Dict[str, Any] | None = None) -> str:
    text = ""
    p = Path(file_path)
    text += " " + p.name.lower() + " " + p.parent.name.lower()
    if tags:
        for v in tags.values():
            if isinstance(v, str):
                text += " " + v.lower()

    score_map = {
        "Bollywood Remix": ["bollywood", "remix", "dance", "masala", "club", "party", "mix", "morni", "desi"],
        "Punjabi": ["punjabi", "bhangra", "dhol", "tandoori", "jatt", "gurmeet", "diljit"],
        "Nashik Baja": ["nashik", "baja", "bajaa", "nashikbaja", "nashik baja", "lavani"],
        "Tapori Mix": ["tapori", "street", "mumbai", "galli", "bindaas", "local"],
        "Club Mix": ["club", "house", "night", "deep", "edm", "dj", "techno", "clubmix"],
        "Garba / Dandiya": ["garba", "dandiya", "navratri", "garbha", "dandia"],
        "Indie / Electronic": ["indie", "electronic", "synth", "experimental", "future", "alternate"],
        "House": ["house", "deep house", "tech house"],
        "Hip Hop": ["rap", "hiphop", "hip hop", "trap", "desi hip hop"],
        "Rock": ["rock", "punk", "metal", "alternative"],
    }

    scores = {name: 0 for name in score_map}
    for genre, keywords in score_map.items():
        for kw in keywords:
            if kw in text:
                scores[genre] += 2

    if not any(scores.values()):
        return "Unknown"
    return max(scores, key=scores.get)


def analyze_audio_file(file_path: str) -> Dict[str, Any]:
    audio, sr = _load_audio_array(file_path)
    if len(audio) == 0:
        return {
            "bpm": 0.0,
            "key": "Unknown",
            "energy": 0.0,
            "sections": [],
            "waveform": [],
            "duration_seconds": 0.0,
        }

    audio = np.asarray(audio, dtype=np.float32)
    bpm = _detect_bpm(audio, sr)
    key = _detect_key(audio, sr)
    energy = _energy_score(audio)
    sections = _section_map(audio, sr)
    waveform = _waveform_peaks(audio, 220)

    return {
        "bpm": round(float(bpm), 2),
        "key": key,
        "energy": round(float(energy), 2),
        "sections": sections,
        "waveform": waveform,
        "duration_seconds": round(float(len(audio) / float(sr)), 2),
    }
