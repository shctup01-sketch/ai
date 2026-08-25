"""Common container returned by every generator."""
from __future__ import annotations

from dataclasses import dataclass, field

import trimesh


@dataclass
class Asset:
    """One generated asset: one or more meshes plus a parallel list of
    material dicts (``{"albedo": PIL.Image, "normal": ..., "roughness": ...,
    "metallic": float, "base_color_factor": (r,g,b,a)}``, all keys optional).

    ``meshes`` and ``materials`` must be the same length — each mesh gets the
    material at the same index.
    """

    name: str
    meshes: list[trimesh.Trimesh]
    materials: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.materials:
            self.materials = [{} for _ in self.meshes]
        if len(self.materials) != len(self.meshes):
            raise ValueError("materials must be the same length as meshes")

    @property
    def triangle_count(self) -> int:
        return sum(len(m.faces) for m in self.meshes)

    @property
    def vertex_count(self) -> int:
        return sum(len(m.vertices) for m in self.meshes)
