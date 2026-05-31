#!/usr/bin/env python3
"""Generate a two-tone doorbell chime WAV file.

Run at Docker build time to bundle a default chime sound.
Uses only Python stdlib (wave, struct, math) — no external dependencies.
"""

import math
import struct
import wave
from pathlib import Path


def generate_chime(output_path: Path, sample_rate: int = 44100) -> None:
    """Generate a classic 'ding-dong' doorbell chime."""
    # (frequency_hz, duration_s, amplitude 0-1)
    tones = [
        (659, 0.30, 0.8),   # E5 — "ding"
        (0, 0.05, 0.0),     # brief silence
        (523, 0.50, 0.7),   # C5 — "dong"
    ]

    samples: list[int] = []
    for freq, duration, amplitude in tones:
        n_samples = int(sample_rate * duration)
        for i in range(n_samples):
            t = i / sample_rate
            if freq > 0:
                # Sine wave with exponential decay for a natural bell sound
                decay = math.exp(-3.0 * t / duration)
                value = amplitude * decay * math.sin(2.0 * math.pi * freq * t)
            else:
                value = 0.0
            samples.append(int(value * 32767))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "w") as wf:
        wf.setnchannels(1)       # mono
        wf.setsampwidth(2)       # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    print(f"Generated chime: {output_path} ({output_path.stat().st_size} bytes)")


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "nukiblinker" / "sounds" / "chime.wav"
    generate_chime(target)
