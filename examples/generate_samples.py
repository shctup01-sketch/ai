"""Example: use assetforge as a library (not just the CLI) to generate a
small showcase batch covering every generator and style.

Run from the repo root:  python3 examples/generate_samples.py
"""
from pathlib import Path

from assetforge.core.export import export_asset
from assetforge.generators import generate_crystal, generate_rock, generate_terrain, generate_tree

OUT_DIR = Path(__file__).resolve().parent.parent / "out" / "showcase"


def main():
    assets = [
        generate_rock(seed=101, style="weathered", tint="grey"),
        generate_rock(seed=102, style="angular", tint="red"),
        generate_crystal(seed=201, family="amethyst"),
        generate_crystal(seed=202, family="quartz"),
        generate_tree(seed=301, style="oak"),
        generate_tree(seed=302, style="pine"),
        generate_tree(seed=303, style="birch"),
        generate_terrain(seed=401, biome="grass"),
        generate_terrain(seed=402, biome="desert"),
    ]

    for asset in assets:
        path = export_asset(asset, OUT_DIR, fmt="glb")
        print(f"{asset.name:28s} verts={asset.vertex_count:6d} tris={asset.triangle_count:6d} -> {path}")


if __name__ == "__main__":
    main()
