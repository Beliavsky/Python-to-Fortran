"""Numerical methods suite: FFT-based frequency detection.

Builds a synthetic signal as the sum of two known sinusoids (3 Hz and
7 Hz) sampled at 64 Hz, runs np.fft.fft, and identifies the two
dominant frequency bins from the magnitude spectrum -- checking they
match the known input frequencies.
"""
import numpy as np

fs = 64.0
n = 64
t = np.arange(n) / fs

signal = np.sin(2.0 * np.pi * 3.0 * t) + 0.5 * np.sin(2.0 * np.pi * 7.0 * t)

spectrum = np.fft.fft(signal)
mag = np.abs(spectrum)

half = n // 2
freqs = np.arange(half) * fs / n

# find the peak bin (excluding DC)
peak1 = 1
peak_val = mag[1]
for i in range(2, half):
    if mag[i] > peak_val:
        peak_val = mag[i]
        peak1 = i

print("peak frequency (Hz) =", freqs[peak1])
print("peak magnitude =", peak_val)
