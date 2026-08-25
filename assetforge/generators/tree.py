"""Procedural low/mid-poly tree generator.

A recursive branching algorithm (functionally an L-system, expressed as
direct recursion for clarity) grows a tapered branch skeleton; each branch
segment becomes a lofted tube, and terminal twigs get a foliage cluster.
Two canopy silhouettes are supported: "blob" (broadleaf, e.g. oak) and
"conical" (conifer, e.g. pine).
"""
from __future__ import annotations

import random

import numpy as np
import trimesh

from ..core.asset import Asset
from ..core.mesh_utils import icosphere, merge_meshes, spherical_uv
from ..core.texture import bark_material, foliage_material

STYLE_PRESETS = {
    "oak": dict(
        species="oak", canopy="blob", season="summer",
        branch_angle=(22, 42), branch_count=(2, 3), depth=4,
        length_decay=(0.62, 0.78), radius_decay=0.68, base_radius=0.16,
        base_length=1.4, upward_bias=0.35,
    ),
    "pine": dict(
        species="pine", canopy="conical", season="pine",
        branch_angle=(45, 65), branch_count=(3, 5), depth=3,
        length_decay=(0.5, 0.62), radius_decay=0.6, base_radius=0.13,
        base_length=1.7, upward_bias=0.1,
    ),
    "birch": dict(
        species="birch", canopy="blob", season="autumn",
        branch_angle=(18, 34), branch_count=(2, 3), depth=4,
        length_decay=(0.68, 0.82), radius_decay=0.72, base_radius=0.1,
        base_length=1.6, upward_bias=0.45,
    ),
}


def _orthonormal_basis(direction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    helper = np.array([0.0, 1.0, 0.0]) if abs(direction[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    right = np.cross(direction, helper)
    right /= np.linalg.norm(right) + 1e-9
    up = np.cross(right, direction)
    return right, up


def _tube_segment(p0: np.ndarray, p1: np.ndarray, r0: float, r1: float, sides: int = 7) -> trimesh.Trimesh:
    direction = p1 - p0
    length = np.linalg.norm(direction)
    if length < 1e-6:
        direction = np.array([0.0, 1.0, 0.0])
    else:
        direction = direction / length
    right, up = _orthonormal_basis(direction)

    angles = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    circle = np.stack([np.cos(angles), np.sin(angles)], axis=1)

    ring0 = p0 + (circle[:, 0:1] * right + circle[:, 1:2] * up) * r0
    ring1 = p1 + (circle[:, 0:1] * right + circle[:, 1:2] * up) * r1
    vertices = np.concatenate([ring0, ring1], axis=0)

    faces = []
    for i in range(sides):
        j = (i + 1) % sides
        faces.append([i, j, sides + j])
        faces.append([i, sides + j, sides + i])
    faces = np.array(faces)

    uv = np.zeros((len(vertices), 2))
    uv[:sides, 0] = np.arange(sides) / sides
    uv[:sides, 1] = 0.0
    uv[sides:, 0] = np.arange(sides) / sides
    uv[sides:, 1] = 1.0

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.visual = trimesh.visual.TextureVisuals(uv=uv)
    return mesh


def _grow(
    rng: random.Random,
    start: np.ndarray,
    direction: np.ndarray,
    length: float,
    radius: float,
    depth: int,
    params: dict,
    trunk_segments: list,
    canopy_points: list,
) -> None:
    end = start + direction * length
    trunk_segments.append(_tube_segment(start, end, radius, radius * params["radius_decay"]))

    if depth <= 0 or radius < 0.012:
        canopy_points.append((end, direction, radius))
        return

    n_children = rng.randint(*params["branch_count"])
    for _ in range(n_children):
        angle = np.radians(rng.uniform(*params["branch_angle"]))
        twist = rng.uniform(0, 2 * np.pi)
        right, up = _orthonormal_basis(direction)
        lateral = np.cos(twist) * right + np.sin(twist) * up
        new_dir = direction * np.cos(angle) + lateral * np.sin(angle)
        new_dir[1] += params["upward_bias"] * rng.uniform(0.3, 1.0)
        new_dir = new_dir / (np.linalg.norm(new_dir) + 1e-9)

        decay = rng.uniform(*params["length_decay"])
        _grow(
            rng, end, new_dir, length * decay, radius * params["radius_decay"],
            depth - 1, params, trunk_segments, canopy_points,
        )


def _canopy_clusters(rng: random.Random, canopy_points: list, style: str, canopy_scale: float) -> list[trimesh.Trimesh]:
    blobs = []
    if style == "conical":
        heights = sorted((p[0][1] for p in canopy_points))
        top = max(heights) if heights else 1.0
        bottom = min(heights) if heights else 0.0
        for p, direction, radius in canopy_points:
            t = 0.0 if top - bottom < 1e-6 else (p[1] - bottom) / (top - bottom)
            r = canopy_scale * (0.35 + 0.65 * (1.0 - t))
            sphere = icosphere(subdivisions=1, radius=r)
            sphere.apply_translation(p)
            blobs.append(sphere)
    else:
        for p, direction, radius in canopy_points:
            r = canopy_scale * rng.uniform(0.55, 1.0)
            sphere = icosphere(subdivisions=1, radius=r)
            jitter = np.array([rng.uniform(-r, r) * 0.3 for _ in range(3)])
            sphere.apply_translation(p + jitter)
            blobs.append(sphere)
    return blobs


def generate_tree(
    seed: int | None = None,
    style: str = "oak",
    height_scale: float = 1.0,
    name: str | None = None,
) -> Asset:
    """Generate one tree asset with a bark-textured trunk/branches and a
    foliage canopy, returned as two meshes (trunk, canopy) so engines can
    apply e.g. wind-sway shaders to the canopy only."""
    if style not in STYLE_PRESETS:
        raise ValueError(f"Unknown tree style {style!r}; choose from {list(STYLE_PRESETS)}")
    params = STYLE_PRESETS[style]

    seed_val = random.Random(seed).randint(0, 2**31 - 1) if seed is None else seed
    rng = random.Random(seed_val)

    trunk_segments: list[trimesh.Trimesh] = []
    canopy_points: list = []
    _grow(
        rng,
        start=np.array([0.0, 0.0, 0.0]),
        direction=np.array([0.0, 1.0, 0.0]),
        length=params["base_length"] * height_scale,
        radius=params["base_radius"] * height_scale,
        depth=params["depth"],
        params=params,
        trunk_segments=trunk_segments,
        canopy_points=canopy_points,
    )

    trunk_mesh = merge_meshes(trunk_segments)
    trunk_mesh.fix_normals()

    canopy_scale = 0.55 * height_scale if params["canopy"] == "blob" else 0.5 * height_scale
    canopy_blobs = _canopy_clusters(rng, canopy_points, params["canopy"], canopy_scale)
    canopy_mesh = merge_meshes(canopy_blobs) if canopy_blobs else icosphere(subdivisions=1, radius=0.1)
    canopy_mesh.visual = trimesh.visual.TextureVisuals(uv=spherical_uv(canopy_mesh))

    combined_bounds = np.concatenate([trunk_mesh.vertices, canopy_mesh.vertices], axis=0)
    min_y = combined_bounds[:, 1].min()
    center_xz = ((combined_bounds.min(axis=0) + combined_bounds.max(axis=0)) / 2)[[0, 2]]
    shift = np.array([-center_xz[0], -min_y, -center_xz[1]])
    trunk_mesh.apply_translation(shift)
    canopy_mesh.apply_translation(shift)

    bark = bark_material(seed_val, species=params["species"])
    foliage = foliage_material(seed_val, season=params["season"])

    asset_name = name or f"tree_{style}_{seed_val}"
    return Asset(
        name=asset_name,
        meshes=[trunk_mesh, canopy_mesh],
        materials=[
            {"albedo": bark["albedo"], "normal": bark["normal"], "roughness": bark["roughness"]},
            {"albedo": foliage["albedo"], "roughness": foliage["roughness"]},
        ],
        metadata={"generator": "tree", "style": style, "seed": seed_val},
    )
