"""Procedural crystal cluster generator.

Each shard is the convex hull of a jittered hexagonal-prism-plus-apex point
set (the classic quartz-point silhouette); several shards of varying size
and tilt are clustered around a shared base to form one asset.
"""
from __future__ import annotations

import random

import numpy as np
import trimesh

from ..core.asset import Asset
from ..core.mesh_utils import merge_meshes, recenter_on_ground
from ..core.texture import crystal_palette

FAMILIES = ["amethyst", "quartz", "emerald", "citrine", "sapphire"]


def _shard(rng: np.random.Generator, sides: int, radius: float, height: float) -> trimesh.Trimesh:
    angles = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    angles += rng.uniform(-0.08, 0.08, size=sides)

    base_r = radius * (1.0 + rng.uniform(-0.1, 0.1, size=sides))
    base = np.stack([np.cos(angles) * base_r, np.zeros(sides), np.sin(angles) * base_r], axis=1)

    shaft_h = height * rng.uniform(0.55, 0.75)
    shaft_r = base_r * rng.uniform(0.75, 0.95)
    shaft = np.stack([np.cos(angles) * shaft_r, np.full(sides, shaft_h), np.sin(angles) * shaft_r], axis=1)

    apex_offset = rng.uniform(-radius * 0.15, radius * 0.15, size=2)
    apex = np.array([[apex_offset[0], height, apex_offset[1]]])

    points = np.concatenate([base, shaft, apex], axis=0)
    mesh = trimesh.Trimesh(vertices=points).convex_hull
    return mesh


def generate_crystal(
    seed: int | None = None,
    shard_count: int | None = None,
    family: str | None = None,
    scale: float = 1.0,
    name: str | None = None,
) -> Asset:
    """Generate a crystal cluster asset (one or more faceted shards)."""
    rng_seed = random.Random(seed).randint(0, 2**31 - 1) if seed is None else seed
    rng = np.random.default_rng(rng_seed)

    n_shards = shard_count or int(rng.integers(3, 7))
    chosen_family = family or FAMILIES[rng.integers(0, len(FAMILIES))]

    shards = []
    for i in range(n_shards):
        sides = int(rng.integers(5, 8))
        base_radius = scale * rng.uniform(0.12, 0.28) * (1.0 if i > 0 else 1.3)
        base_height = scale * rng.uniform(0.7, 1.6) * (1.0 if i > 0 else 1.35)
        shard = _shard(rng, sides, base_radius, base_height)

        tilt_x = rng.uniform(-18, 18)
        tilt_z = rng.uniform(-18, 18)
        rot_y = rng.uniform(0, 360)
        transform = trimesh.transformations.euler_matrix(
            np.radians(tilt_x), np.radians(rot_y), np.radians(tilt_z), axes="rxyz"
        )
        shard.apply_transform(transform)

        radial = scale * rng.uniform(0.0, 0.18) if i > 0 else 0.0
        theta = rng.uniform(0, 2 * np.pi)
        shard.apply_translation([np.cos(theta) * radial, 0.0, np.sin(theta) * radial])

        shards.append(shard)

    mesh = merge_meshes(shards)
    recenter_on_ground(mesh)
    mesh.fix_normals()

    base_color = crystal_palette(rng_seed, family=chosen_family)
    material = {
        "base_color_factor": base_color,
        "metallic": 0.05,
        "roughness_factor": 0.12,
    }

    asset_name = name or f"crystal_{chosen_family}_{rng_seed}"
    return Asset(
        name=asset_name,
        meshes=[mesh],
        materials=[material],
        metadata={"generator": "crystal", "family": chosen_family, "shards": n_shards, "seed": rng_seed},
    )
