"""Procedural rock / boulder generator.

Strategy: start from a subdivided icosphere, carve/bulge it with layered
fractal noise displaced along vertex normals, then optionally facet it
(flat-shade + light re-noise) for a more angular, "chipped stone" look.
"""
from __future__ import annotations

import random

import numpy as np
import trimesh

from ..core.asset import Asset
from ..core.mesh_utils import displace_along_normals, icosphere, recenter_on_ground, spherical_uv
from ..core.noise import GradientNoise
from ..core.texture import rock_material

TINTS = ["grey", "red", "moss"]


def generate_rock(
    seed: int | None = None,
    subdivisions: int = 3,
    radius: float = 1.0,
    style: str = "weathered",
    tint: str | None = None,
    size_variation: float = 0.25,
    name: str | None = None,
) -> Asset:
    """Generate one rock/boulder asset.

    style: "weathered" (smooth, rounded, wind/water-worn) or "angular"
    (jagged, faceted, freshly-fractured look).
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    seed_val = rng.randint(0, 2**31 - 1) if seed is None else seed
    noise = GradientNoise(seed_val)

    mesh = icosphere(subdivisions=subdivisions, radius=radius)

    # Non-uniform base scale so it isn't a perfect sphere before displacement.
    scale = 1.0 + (np_rng.random(3) - 0.5) * size_variation
    mesh.vertices *= scale

    if style == "angular":
        displace_along_normals(mesh, noise, amplitude=radius * 0.32, frequency=1.4, octaves=3, power=0.6)
        # Facet the surface: flat-shade by duplicating vertices per-face and
        # nudging each face along its own normal for a chipped-stone look.
        face_normals = mesh.face_normals
        face_verts = mesh.vertices[mesh.faces]  # (n_faces, 3, 3)
        jitter = (np_rng.random(len(mesh.faces)) - 0.5) * radius * 0.05
        face_verts = face_verts + (face_normals[:, None, :] * jitter[:, None, None])
        new_faces = np.arange(face_verts.shape[0] * 3).reshape(-1, 3)
        mesh = trimesh.Trimesh(vertices=face_verts.reshape(-1, 3), faces=new_faces, process=False)
    else:
        displace_along_normals(mesh, noise, amplitude=radius * 0.22, frequency=1.0, octaves=5, power=1.0)
        displace_along_normals(mesh, noise, amplitude=radius * 0.05, frequency=4.0, octaves=2, offset=np.array([50, 50, 50]))

    mesh.fix_normals()
    recenter_on_ground(mesh)

    uv = spherical_uv(mesh)
    mesh.visual = trimesh.visual.TextureVisuals(uv=uv)

    chosen_tint = tint or rng.choice(TINTS)
    mats = rock_material(seed_val, tint=chosen_tint)

    asset_name = name or f"rock_{style}_{chosen_tint}_{seed_val}"
    return Asset(
        name=asset_name,
        meshes=[mesh],
        materials=[{"albedo": mats["albedo"], "normal": mats["normal"], "roughness": mats["roughness"]}],
        metadata={"generator": "rock", "style": style, "tint": chosen_tint, "seed": seed_val},
    )
