import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from desi_dj.analysis import analyze_audio_file
from desi_dj.library import MusicLibrary


def make_tone(path: str, seconds: float = 4.0, bpm: float = 128.0):
    sr = 44100
    t = np.arange(int(sr * seconds)) / sr
    base = np.sin(2 * np.pi * 220 * t)
    kick = 0.4 * np.sin(2 * np.pi * 55 * t)
    beat = np.sin(2 * np.pi * (bpm / 60.0) * t)
    signal = base + kick + 0.2 * beat
    sf.write(path, signal.astype(np.float32), sr)


def run():
    temp_dir = Path(tempfile.mkdtemp(prefix="desidj_"))
    track = temp_dir / "demo_track.wav"
    make_tone(str(track), seconds=4.0, bpm=128.0)

    result = analyze_audio_file(str(track))
    assert "bpm" in result, "No BPM data"
    assert "key" in result, "No key data"
    assert "energy" in result, "No energy data"
    assert result["bpm"] > 0, "BPM not detected"

    db = temp_dir / "test.db"
    lib = MusicLibrary(str(db))
    imported = lib.import_folder(str(temp_dir))
    assert len(imported) >= 1, "Library import failed"

    print("Self-test passed")
    print(result)


if __name__ == "__main__":
    run()
