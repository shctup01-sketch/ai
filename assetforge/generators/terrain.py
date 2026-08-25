"""Procedural terrain chunk generator (heightfield grid mesh)."""
from __future__ import annotations

import random

import numpy as np
import trimesh

from ..core.asset import Asset
from ..core.noise import GradientNoise
from ..core.texture import terrain_material

BIOMES = ["grass", "desert", "snow"]


def generate_terrain(
    seed: int | None = None,
    resolution: int = 64,
    size: float = 10.0,
    height_scale: float = 1.6,
    biome: str | None = None,
    name: str | None = None,
) -> Asset:
    """Generate a flat-footprint terrain patch (a tileable-ish ground chunk)
    with height and biome-blended albedo/normal/roughness maps sharing the
    same underlying noise field."""
    seed_val = random.Random(seed).randint(0, 2**31 - 1) if seed is None else seed
    rng = random.Random(seed_val)
    chosen_biome = biome or rng.choice(BIOMES)

    noise = GradientNoise(seed_val)
    xs = np.linspace(-size / 2, size / 2, resolution)
    zs = np.linspace(-size / 2, size / 2, resolution)
    gx, gz = np.meshgrid(xs, zs)

    freq = 0.35
    h = noise.fbm2(gx * freq, gz * freq, octaves=5)
    h = (h - h.min()) / (h.max() - h.min() + 1e-9)
    heights = h * height_scale

    vertices = np.stack([gx.ravel(), heights.ravel(), gz.ravel()], axis=1)

    faces = []
    for i in range(resolution - 1):
        for j in range(resolution - 1):
            a = i * resolution + j
            b = a + 1
            c = a + resolution
            d = c + 1
            faces.append([a, c, b])
            faces.append([b, c, d])
    faces = np.array(faces)

    uv = np.stack([(gx.ravel() / size + 0.5), 1.0 - (gz.ravel() / size + 0.5)], axis=1)

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.visual = trimesh.visual.TextureVisuals(uv=uv)
    mesh.fix_normals()

    mats = terrain_material(seed_val, biome=chosen_biome)

    asset_name = name or f"terrain_{chosen_biome}_{seed_val}"
    return Asset(
        name=asset_name,
        meshes=[mesh],
        materials=[{"albedo": mats["albedo"], "normal": mats["normal"], "roughness": mats["roughness"]}],
        metadata={
            "generator": "terrain",
            "biome": chosen_biome,
            "seed": seed_val,
            "resolution": resolution,
            "size": size,
        },
    )
