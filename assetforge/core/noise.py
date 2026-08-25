"""Seedable gradient (Perlin-style) noise, implemented in pure NumPy.

No compiled/native dependency is required, so asset generation stays
reproducible and portable across platforms. Supports 2D and 3D sampling
plus fractal Brownian motion (fBm) for natural-looking multi-octave detail.
"""
from __future__ import annotations

import numpy as np


class GradientNoise:
    """Deterministic, seedable Perlin-style gradient noise."""

    def __init__(self, seed: int = 0):
        rng = np.random.default_rng(seed)
        perm = rng.permutation(256).astype(np.int64)
        self._perm = np.tile(perm, 2)

        angles = rng.uniform(0, 2 * np.pi, size=256)
        self._grad2 = np.stack([np.cos(angles), np.sin(angles)], axis=1)

        g3 = rng.normal(size=(256, 3))
        g3 /= np.linalg.norm(g3, axis=1, keepdims=True)
        self._grad3 = g3

    @staticmethod
    def _fade(t):
        return t * t * t * (t * (t * 6 - 15) + 10)

    def _hash2(self, xi, yi):
        return self._perm[(self._perm[xi & 255] + yi) & 255]

    def _hash3(self, xi, yi, zi):
        return self._perm[(self._perm[(self._perm[xi & 255] + yi) & 255] + zi) & 255]

    def noise2(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        xi = np.floor(x).astype(np.int64)
        yi = np.floor(y).astype(np.int64)
        xf = x - xi
        yf = y - yi

        u = self._fade(xf)
        v = self._fade(yf)

        def grad_at(ix, iy, dx, dy):
            idx = self._hash2(ix, iy)
            g = self._grad2[idx % 256]
            return g[..., 0] * dx + g[..., 1] * dy

        n00 = grad_at(xi, yi, xf, yf)
        n10 = grad_at(xi + 1, yi, xf - 1, yf)
        n01 = grad_at(xi, yi + 1, xf, yf - 1)
        n11 = grad_at(xi + 1, yi + 1, xf - 1, yf - 1)

        nx0 = n00 + u * (n10 - n00)
        nx1 = n01 + u * (n11 - n01)
        return nx0 + v * (nx1 - nx0)

    def noise3(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        z = np.asarray(z, dtype=np.float64)
        xi = np.floor(x).astype(np.int64)
        yi = np.floor(y).astype(np.int64)
        zi = np.floor(z).astype(np.int64)
        xf = x - xi
        yf = y - yi
        zf = z - zi

        u = self._fade(xf)
        v = self._fade(yf)
        w = self._fade(zf)

        def grad_at(ix, iy, iz, dx, dy, dz):
            idx = self._hash3(ix, iy, iz)
            g = self._grad3[idx % 256]
            return g[..., 0] * dx + g[..., 1] * dy + g[..., 2] * dz

        n000 = grad_at(xi, yi, zi, xf, yf, zf)
        n100 = grad_at(xi + 1, yi, zi, xf - 1, yf, zf)
        n010 = grad_at(xi, yi + 1, zi, xf, yf - 1, zf)
        n110 = grad_at(xi + 1, yi + 1, zi, xf - 1, yf - 1, zf)
        n001 = grad_at(xi, yi, zi + 1, xf, yf, zf - 1)
        n101 = grad_at(xi + 1, yi, zi + 1, xf - 1, yf, zf - 1)
        n011 = grad_at(xi, yi + 1, zi + 1, xf, yf - 1, zf - 1)
        n111 = grad_at(xi + 1, yi + 1, zi + 1, xf - 1, yf - 1, zf - 1)

        nx00 = n000 + u * (n100 - n000)
        nx10 = n010 + u * (n110 - n010)
        nx01 = n001 + u * (n101 - n001)
        nx11 = n011 + u * (n111 - n011)
        nxy0 = nx00 + v * (nx10 - nx00)
        nxy1 = nx01 + v * (nx11 - nx01)
        return nxy0 + w * (nxy1 - nxy0)

    def fbm3(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        octaves: int = 4,
        lacunarity: float = 2.0,
        gain: float = 0.5,
    ) -> np.ndarray:
        total = np.zeros_like(np.asarray(x, dtype=np.float64))
        amplitude = 1.0
        frequency = 1.0
        max_amp = 0.0
        for _ in range(octaves):
            total += amplitude * self.noise3(x * frequency, y * frequency, z * frequency)
            max_amp += amplitude
            amplitude *= gain
            frequency *= lacunarity
        return total / max_amp

    def fbm2(
        self,
        x: np.ndarray,
        y: np.ndarray,
        octaves: int = 4,
        lacunarity: float = 2.0,
        gain: float = 0.5,
    ) -> np.ndarray:
        total = np.zeros_like(np.asarray(x, dtype=np.float64))
        amplitude = 1.0
        frequency = 1.0
        max_amp = 0.0
        for _ in range(octaves):
            total += amplitude * self.noise2(x * frequency, y * frequency)
            max_amp += amplitude
            amplitude *= gain
            frequency *= lacunarity
        return total / max_amp
