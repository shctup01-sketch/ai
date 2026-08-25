"""Procedural PBR texture synthesis (albedo / normal / roughness maps).

Everything here is pure NumPy + Pillow — no network calls, no pretrained
models — so a full material set is generated in milliseconds and the
result is fully reproducible from a seed.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from .noise import GradientNoise


def _fbm_field(noise: GradientNoise, size: int, scale: float, octaves: int = 5) -> np.ndarray:
    """Tileable-ish fBm field sampled on a size x size grid, normalized to [0, 1]."""
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float64)
    field = noise.fbm2(xs / size * scale, ys / size * scale, octaves=octaves)
    field = (field - field.min()) / (field.max() - field.min() + 1e-9)
    return field


def height_to_normal_map(height: np.ndarray, strength: float = 3.0) -> Image.Image:
    """Convert a grayscale height field (0..1) to a tangent-space RGB normal map."""
    gy, gx = np.gradient(height.astype(np.float64) * strength)
    nx = -gx
    ny = -gy
    nz = np.ones_like(height)
    length = np.sqrt(nx**2 + ny**2 + nz**2)
    nx, ny, nz = nx / length, ny / length, nz / length
    rgb = np.stack(
        [(nx * 0.5 + 0.5), (ny * 0.5 + 0.5), (nz * 0.5 + 0.5)], axis=-1
    )
    return Image.fromarray((rgb * 255).astype(np.uint8), mode="RGB")


def _colorize(field: np.ndarray, ramp: list[tuple[float, tuple[int, int, int]]]) -> np.ndarray:
    """Map a scalar field through a color ramp -> HxWx3 uint8 array."""
    ramp = sorted(ramp, key=lambda s: s[0])
    h, w = field.shape
    out = np.zeros((h, w, 3), dtype=np.float64)
    for j in range(len(ramp) - 1):
        t0, c0 = ramp[j]
        t1, c1 = ramp[j + 1]
        mask = (field >= t0) & (field <= t1 if j == len(ramp) - 2 else field < t1)
        span = max(t1 - t0, 1e-9)
        f = np.clip((field[mask] - t0) / span, 0.0, 1.0)
        c0a, c1a = np.array(c0, dtype=np.float64), np.array(c1, dtype=np.float64)
        out[mask] = c0a[None, :] * (1 - f[:, None]) + c1a[None, :] * f[:, None]
    return out.astype(np.uint8)


def rock_material(seed: int, size: int = 512, tint: str = "grey") -> dict[str, Image.Image]:
    """Weathered rock/stone PBR set: albedo, normal, roughness (greyscale)."""
    noise = GradientNoise(seed)
    base = _fbm_field(noise, size, scale=6.0, octaves=5)
    detail = _fbm_field(noise, size, scale=24.0, octaves=3)
    height = np.clip(base * 0.75 + detail * 0.25, 0, 1)

    ramps = {
        "grey": [(0.0, (58, 55, 52)), (0.5, (98, 93, 86)), (1.0, (150, 144, 132))],
        "red": [(0.0, (70, 40, 32)), (0.5, (120, 74, 55)), (1.0, (168, 118, 88))],
        "moss": [(0.0, (48, 54, 40)), (0.5, (86, 96, 68)), (1.0, (132, 140, 104))],
    }
    albedo_rgb = _colorize(height, ramps.get(tint, ramps["grey"]))
    ao = 0.55 + 0.45 * _fbm_field(noise, size, scale=10.0, octaves=4)
    albedo_rgb = np.clip(albedo_rgb.astype(np.float64) * ao[..., None], 0, 255).astype(np.uint8)

    roughness_field = 0.55 + 0.35 * _fbm_field(noise, size, scale=18.0, octaves=3)
    roughness_field = np.clip(roughness_field, 0, 1)
    roughness_rgb = np.stack([roughness_field] * 3, axis=-1)

    return {
        "albedo": Image.fromarray(albedo_rgb, mode="RGB"),
        "normal": height_to_normal_map(height, strength=4.5),
        "roughness": Image.fromarray((roughness_rgb * 255).astype(np.uint8), mode="RGB"),
    }


def bark_material(seed: int, size: int = 512, species: str = "oak") -> dict[str, Image.Image]:
    """Vertical fibrous bark texture (used on tree trunks/branches)."""
    noise = GradientNoise(seed)
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float64)
    stripes = np.sin(xs / size * 60.0 + noise.fbm2(xs / size * 3, ys / size * 20, octaves=4) * 6.0)
    stripes = (stripes + 1) / 2
    fine = _fbm_field(noise, size, scale=30.0, octaves=4)
    height = np.clip(stripes * 0.6 + fine * 0.4, 0, 1)

    ramps = {
        "oak": [(0.0, (35, 25, 18)), (0.5, (66, 47, 32)), (1.0, (99, 74, 51))],
        "pine": [(0.0, (45, 30, 20)), (0.5, (92, 62, 38)), (1.0, (133, 96, 62))],
        "birch": [(0.0, (222, 216, 202)), (0.5, (238, 233, 222)), (1.0, (60, 55, 50))],
    }
    albedo_rgb = _colorize(height, ramps.get(species, ramps["oak"]))
    roughness_field = np.clip(0.75 + 0.2 * fine, 0, 1)
    roughness_rgb = np.stack([roughness_field] * 3, axis=-1)

    return {
        "albedo": Image.fromarray(albedo_rgb, mode="RGB"),
        "normal": height_to_normal_map(height, strength=3.0),
        "roughness": Image.fromarray((roughness_rgb * 255).astype(np.uint8), mode="RGB"),
    }


def foliage_material(seed: int, size: int = 256, season: str = "summer") -> dict[str, Image.Image]:
    """Mottled leaf-canopy color set (albedo + roughness only; canopies are
    low-poly so a normal map adds little)."""
    noise = GradientNoise(seed)
    field = _fbm_field(noise, size, scale=10.0, octaves=4)

    ramps = {
        "summer": [(0.0, (28, 66, 24)), (0.5, (46, 98, 36)), (1.0, (78, 138, 54))],
        "autumn": [(0.0, (120, 58, 16)), (0.5, (172, 104, 24)), (1.0, (206, 156, 40))],
        "pine": [(0.0, (18, 46, 30)), (0.5, (28, 70, 44)), (1.0, (44, 96, 60))],
    }
    albedo_rgb = _colorize(field, ramps.get(season, ramps["summer"]))
    roughness_field = np.clip(0.6 + 0.3 * field, 0, 1)
    roughness_rgb = np.stack([roughness_field] * 3, axis=-1)

    return {
        "albedo": Image.fromarray(albedo_rgb, mode="RGB"),
        "roughness": Image.fromarray((roughness_rgb * 255).astype(np.uint8), mode="RGB"),
    }


def terrain_material(seed: int, size: int = 1024, biome: str = "grass") -> dict[str, Image.Image]:
    """Height/slope-blended ground material (grass/dirt/rock or sand/rock)."""
    noise = GradientNoise(seed)
    base = _fbm_field(noise, size, scale=8.0, octaves=6)
    detail = _fbm_field(noise, size, scale=40.0, octaves=3)
    height = np.clip(base * 0.7 + detail * 0.3, 0, 1)

    ramps = {
        "grass": [(0.0, (46, 58, 30)), (0.35, (70, 92, 42)), (0.7, (96, 88, 58)), (1.0, (150, 146, 138))],
        "desert": [(0.0, (146, 116, 74)), (0.5, (184, 152, 100)), (1.0, (214, 196, 160))],
        "snow": [(0.0, (120, 128, 132)), (0.4, (200, 206, 210)), (1.0, (245, 248, 250))],
    }
    albedo_rgb = _colorize(height, ramps.get(biome, ramps["grass"]))

    roughness_field = np.clip(0.7 + 0.2 * detail, 0, 1)
    roughness_rgb = np.stack([roughness_field] * 3, axis=-1)

    return {
        "albedo": Image.fromarray(albedo_rgb, mode="RGB"),
        "normal": height_to_normal_map(height, strength=6.0),
        "roughness": Image.fromarray((roughness_rgb * 255).astype(np.uint8), mode="RGB"),
        "height": height,
    }


def crystal_palette(seed: int, family: str = "amethyst") -> tuple[int, int, int, int]:
    """A single translucent-looking base RGBA color for a crystal family,
    with small seeded hue jitter so batches of the same family still vary."""
    rng = np.random.default_rng(seed)
    palettes = {
        "amethyst": (150, 90, 210),
        "quartz": (225, 232, 238),
        "emerald": (46, 176, 120),
        "citrine": (232, 172, 58),
        "sapphire": (52, 108, 210),
    }
    base = np.array(palettes.get(family, palettes["amethyst"]), dtype=np.float64)
    jitter = rng.uniform(-12, 12, size=3)
    color = np.clip(base + jitter, 0, 255).astype(int)
    return (int(color[0]), int(color[1]), int(color[2]), 235)
