"""Export generated meshes to engine-ready files (GLB / OBJ+MTL)."""
from __future__ import annotations

from pathlib import Path

import trimesh
from PIL import Image

from .asset import Asset


def _apply_pbr_material(
    mesh: trimesh.Trimesh,
    albedo: Image.Image | None = None,
    normal: Image.Image | None = None,
    roughness: Image.Image | None = None,
    metallic: float = 0.0,
    roughness_factor: float = 1.0,
    base_color_factor: tuple[int, int, int, int] | None = None,
) -> None:
    """Attach a glTF-style metallic-roughness material to ``mesh`` in place."""
    material_kwargs = dict(metallicFactor=metallic, roughnessFactor=roughness_factor)
    if albedo is not None:
        # trimesh's OBJ/GLB exporters expect UVs for textured materials; when a
        # generator hasn't assigned any, fall back to vertex-color shading
        # instead of writing an unmapped (and therefore meaningless) texture.
        has_uv = getattr(mesh.visual, "uv", None) is not None
        if has_uv:
            material_kwargs["baseColorTexture"] = albedo
        else:
            material_kwargs["baseColorFactor"] = base_color_factor or (255, 255, 255, 255)
    elif base_color_factor is not None:
        material_kwargs["baseColorFactor"] = base_color_factor

    if normal is not None and getattr(mesh.visual, "uv", None) is not None:
        material_kwargs["normalTexture"] = normal
    if roughness is not None and getattr(mesh.visual, "uv", None) is not None:
        # PBRMaterial takes a single-channel-in-RGB roughness texture.
        material_kwargs["metallicRoughnessTexture"] = roughness

    material = trimesh.visual.material.PBRMaterial(**material_kwargs)
    if getattr(mesh.visual, "uv", None) is not None:
        mesh.visual = trimesh.visual.TextureVisuals(uv=mesh.visual.uv, material=material)
    else:
        mesh.visual.material = material


def export_asset(asset: Asset, out_dir: str | Path, fmt: str = "glb") -> Path:
    """Write ``asset`` to ``out_dir`` in the requested format.

    fmt: "glb" (single self-contained binary glTF, recommended for Unity /
    Unreal / Godot drag-and-drop import) or "obj" (OBJ + MTL + PNG textures).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for mesh, mat in zip(asset.meshes, asset.materials):
        _apply_pbr_material(
            mesh,
            albedo=mat.get("albedo"),
            normal=mat.get("normal"),
            roughness=mat.get("roughness"),
            metallic=mat.get("metallic", 0.0),
            roughness_factor=mat.get("roughness_factor", 1.0),
            base_color_factor=mat.get("base_color_factor"),
        )

    if len(asset.meshes) == 1:
        combined = asset.meshes[0]
    else:
        scene = trimesh.Scene()
        for i, mesh in enumerate(asset.meshes):
            scene.add_geometry(mesh, node_name=f"{asset.name}_part{i}")
        combined = scene

    fmt = fmt.lower()
    if fmt == "glb":
        path = out_dir / f"{asset.name}.glb"
        combined.export(path.as_posix(), file_type="glb")
    elif fmt == "obj":
        path = out_dir / f"{asset.name}.obj"
        combined.export(path.as_posix(), file_type="obj")
    else:
        raise ValueError(f"Unsupported export format: {fmt!r} (use 'glb' or 'obj')")

    return path
