"""Smoke tests: every generator must produce valid, finite, exportable meshes."""
from __future__ import annotations

import numpy as np
import pytest

from assetforge.core.export import export_asset
from assetforge.generators import generate_crystal, generate_rock, generate_terrain, generate_tree


def _assert_valid_mesh(mesh):
    assert np.isfinite(mesh.vertices).all(), "mesh contains NaN/inf vertices"
    assert len(mesh.faces) > 0
    assert mesh.faces.max() < len(mesh.vertices)
    assert mesh.faces.min() >= 0


@pytest.mark.parametrize("style", ["weathered", "angular"])
@pytest.mark.parametrize("seed", [1, 42])
def test_rock(style, seed, tmp_path):
    asset = generate_rock(seed=seed, style=style)
    assert len(asset.meshes) == 1
    _assert_valid_mesh(asset.meshes[0])
    path = export_asset(asset, tmp_path, fmt="glb")
    assert path.exists() and path.stat().st_size > 0


@pytest.mark.parametrize("family", ["amethyst", "quartz", "emerald", "citrine", "sapphire"])
def test_crystal(family, tmp_path):
    asset = generate_crystal(seed=7, family=family)
    _assert_valid_mesh(asset.meshes[0])
    path = export_asset(asset, tmp_path, fmt="glb")
    assert path.exists() and path.stat().st_size > 0


@pytest.mark.parametrize("style", ["oak", "pine", "birch"])
def test_tree(style, tmp_path):
    asset = generate_tree(seed=5, style=style)
    assert len(asset.meshes) == 2  # trunk, canopy
    for mesh in asset.meshes:
        _assert_valid_mesh(mesh)
    path = export_asset(asset, tmp_path, fmt="glb")
    assert path.exists() and path.stat().st_size > 0


@pytest.mark.parametrize("biome", ["grass", "desert", "snow"])
def test_terrain(biome, tmp_path):
    asset = generate_terrain(seed=3, resolution=16, biome=biome)
    _assert_valid_mesh(asset.meshes[0])
    path = export_asset(asset, tmp_path, fmt="glb")
    assert path.exists() and path.stat().st_size > 0


def test_obj_export(tmp_path):
    asset = generate_rock(seed=1)
    path = export_asset(asset, tmp_path, fmt="obj")
    assert path.exists() and path.suffix == ".obj"
    assert (tmp_path / "material.mtl").exists()


def test_reproducible_seed():
    a = generate_rock(seed=123)
    b = generate_rock(seed=123)
    assert np.allclose(a.meshes[0].vertices, b.meshes[0].vertices)
