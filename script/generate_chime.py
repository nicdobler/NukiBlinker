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
    """Generate a classic 'ding-dong' doorbell chime.

    Uses fundamental + harmonics with exponential decay for a
    natural bell-like sound that plays clearly on smart speakers.
    """
    # (frequency_hz, duration_s, amplitude 0-1)
    tones = [
        (659.25, 0.60, 0.85),   # E5 — "ding"
        (0, 0.08, 0.0),         # brief silence
        (523.25, 0.80, 0.75),   # C5 — "dong"
        (0, 0.20, 0.0),         # tail silence
    ]

    # Harmonics: (multiplier, relative_amplitude)
    harmonics = [(1.0, 1.0), (2.0, 0.4), (3.0, 0.15), (4.0, 0.05)]

    samples: list[int] = []
    for freq, duration, amplitude in tones:
        n_samples = int(sample_rate * duration)
        for i in range(n_samples):
            t = i / sample_rate
            if freq > 0:
                # Sum harmonics with exponential decay for a bell timbre
                decay = math.exp(-4.0 * t / duration)
                value = 0.0
                for mult, rel_amp in harmonics:
                    value += rel_amp * math.sin(2.0 * math.pi * freq * mult * t)
                # Normalize harmonics sum and apply amplitude + decay
                value = amplitude * decay * value / sum(ra for _, ra in harmonics)
            else:
                value = 0.0
            samples.append(int(max(-1.0, min(1.0, value)) * 32767))

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
