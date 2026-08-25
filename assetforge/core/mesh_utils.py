"""Shared mesh-manipulation helpers built on top of :mod:`trimesh`."""
from __future__ import annotations

import numpy as np
import trimesh

from .noise import GradientNoise


def icosphere(subdivisions: int = 3, radius: float = 1.0) -> trimesh.Trimesh:
    """Return a unit icosphere with evenly distributed vertices.

    Subdivided icospheres (vs. UV spheres) avoid pole pinching, which keeps
    noise displacement and texturing distortion-free.
    """
    return trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)


def displace_along_normals(
    mesh: trimesh.Trimesh,
    noise: GradientNoise,
    amplitude: float,
    frequency: float = 1.0,
    octaves: int = 4,
    offset: np.ndarray | None = None,
    power: float = 1.0,
) -> trimesh.Trimesh:
    """Displace vertices along their normals using fractal noise.

    ``power`` > 1 sharpens peaks (useful for jagged rocks); < 1 smooths them.
    Returns the same mesh object, mutated in place, for chaining.
    """
    offset = np.zeros(3) if offset is None else offset
    verts = mesh.vertices
    normals = mesh.vertex_normals
    sample = verts * frequency + offset
    n = noise.fbm3(sample[:, 0], sample[:, 1], sample[:, 2], octaves=octaves)
    n = np.sign(n) * (np.abs(n) ** power)
    mesh.vertices = verts + normals * (n[:, None] * amplitude)
    mesh.fix_normals()
    return mesh


def recenter_on_ground(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Translate the mesh so its lowest point sits on the Y=0 plane and its
    horizontal footprint is centered on the origin (Y-up convention)."""
    bounds = mesh.bounds
    center_xz = (bounds[0] + bounds[1]) / 2.0
    mesh.apply_translation([-center_xz[0], -bounds[0][1], -center_xz[2]])
    return mesh


def apply_vertex_color_by_height(
    mesh: trimesh.Trimesh,
    color_stops: list[tuple[float, tuple[int, int, int, int]]],
) -> trimesh.Trimesh:
    """Paint vertex colors by interpolating a ramp keyed on normalized height
    (0 = lowest point, 1 = highest point) along the mesh's Y axis."""
    y = mesh.vertices[:, 1]
    lo, hi = y.min(), y.max()
    t = np.zeros_like(y) if hi - lo < 1e-9 else (y - lo) / (hi - lo)

    stops = sorted(color_stops, key=lambda s: s[0])
    colors = np.zeros((len(t), 4), dtype=np.uint8)
    for i in range(len(t)):
        ti = t[i]
        for j in range(len(stops) - 1):
            t0, c0 = stops[j]
            t1, c1 = stops[j + 1]
            if t0 <= ti <= t1 or j == len(stops) - 2:
                span = max(t1 - t0, 1e-9)
                f = np.clip((ti - t0) / span, 0.0, 1.0)
                colors[i] = np.array(c0) * (1 - f) + np.array(c1) * f
                break
    mesh.visual = trimesh.visual.ColorVisuals(mesh, vertex_colors=colors)
    return mesh


def spherical_uv(mesh: trimesh.Trimesh, center: np.ndarray | None = None) -> np.ndarray:
    """Equirectangular (lat/long) UV coordinates from each vertex's direction
    relative to ``center`` (defaults to the mesh's bounding-box center).

    Good enough for blobby, roughly-spherical assets (rocks, crystals); it
    will show a seam/pole pinch on very elongated shapes.
    """
    center = mesh.bounds.mean(axis=0) if center is None else center
    d = mesh.vertices - center
    d = d / (np.linalg.norm(d, axis=1, keepdims=True) + 1e-9)
    u = 0.5 + np.arctan2(d[:, 2], d[:, 0]) / (2 * np.pi)
    v = 0.5 - np.arcsin(np.clip(d[:, 1], -1, 1)) / np.pi
    return np.stack([u, v], axis=1)


def cylindrical_uv(mesh: trimesh.Trimesh, axis: int = 1) -> np.ndarray:
    """Cylindrical UVs around ``axis`` (default Y) — used for trunks/branches
    and other elongated shapes where spherical UVs would pinch badly."""
    verts = mesh.vertices
    other = [i for i in range(3) if i != axis]
    a, b = verts[:, other[0]], verts[:, other[1]]
    u = 0.5 + np.arctan2(b, a) / (2 * np.pi)
    h = verts[:, axis]
    lo, hi = h.min(), h.max()
    v = np.zeros_like(h) if hi - lo < 1e-9 else (h - lo) / (hi - lo)
    return np.stack([u, v], axis=1)


def merge_meshes(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    """Concatenate multiple meshes (preserving per-mesh vertex colors when
    present) into a single mesh."""
    return trimesh.util.concatenate(meshes)


def jittered_sphere_points(
    count: int, rng: np.random.Generator, radius: float = 1.0, jitter: float = 0.15
) -> np.ndarray:
    """Fibonacci sphere point distribution with per-point radial jitter —
    a fast source of well-spread random directions (used by crystal
    clusters and rock fields)."""
    i = np.arange(count)
    golden = np.pi * (3.0 - np.sqrt(5.0))
    y = 1 - (i / max(count - 1, 1)) * 2
    r = np.sqrt(np.clip(1 - y * y, 0, 1))
    theta = golden * i
    x = np.cos(theta) * r
    z = np.sin(theta) * r
    pts = np.stack([x, y, z], axis=1) * radius
    pts *= 1.0 + rng.uniform(-jitter, jitter, size=(count, 1))
    return pts
