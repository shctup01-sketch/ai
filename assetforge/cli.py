"""Command-line interface: ``python -m assetforge generate <type> [options]``."""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

from .core.export import export_asset
from .generators import (
    CRYSTAL_FAMILIES,
    ROCK_TINTS,
    TERRAIN_BIOMES,
    TREE_STYLES,
    generate_crystal,
    generate_rock,
    generate_terrain,
    generate_tree,
)


def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--count", type=int, default=1, help="Number of assets to generate (default: 1)")
    p.add_argument("--seed", type=int, default=None, help="Base random seed (omit for a random one)")
    p.add_argument("--out", type=str, default="out", help="Output directory (default: out)")
    p.add_argument("--format", choices=["glb", "obj"], default="glb", help="Export format (default: glb)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assetforge",
        description="Procedurally generate high-quality, engine-ready 3D game assets (no external APIs/models).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate one or more assets")
    asset_sub = gen.add_subparsers(dest="asset_type", required=True)

    rock_p = asset_sub.add_parser("rock", help="Rock / boulder")
    _add_common_args(rock_p)
    rock_p.add_argument("--style", choices=["weathered", "angular"], default="weathered")
    rock_p.add_argument("--tint", choices=ROCK_TINTS, default=None)
    rock_p.add_argument("--subdivisions", type=int, default=3, help="Mesh detail level (2-4 typical)")
    rock_p.add_argument("--radius", type=float, default=1.0)

    crystal_p = asset_sub.add_parser("crystal", help="Crystal cluster")
    _add_common_args(crystal_p)
    crystal_p.add_argument("--family", choices=CRYSTAL_FAMILIES, default=None)
    crystal_p.add_argument("--shards", type=int, default=None, help="Number of crystal shards (default: 3-6 random)")
    crystal_p.add_argument("--scale", type=float, default=1.0)

    tree_p = asset_sub.add_parser("tree", help="Tree")
    _add_common_args(tree_p)
    tree_p.add_argument("--style", choices=list(TREE_STYLES), default="oak")
    tree_p.add_argument("--height-scale", type=float, default=1.0)

    terrain_p = asset_sub.add_parser("terrain", help="Terrain chunk (heightfield)")
    _add_common_args(terrain_p)
    terrain_p.add_argument("--biome", choices=TERRAIN_BIOMES, default=None)
    terrain_p.add_argument("--resolution", type=int, default=64, help="Grid resolution per side")
    terrain_p.add_argument("--size", type=float, default=10.0, help="World-space side length")

    all_p = asset_sub.add_parser("all", help="Generate a demo batch: one (or --count) of every asset type")
    _add_common_args(all_p)

    return parser


def _generate_one(asset_type: str, args: argparse.Namespace, seed: int):
    if asset_type == "rock":
        return generate_rock(seed=seed, style=args.style, tint=args.tint, subdivisions=args.subdivisions, radius=args.radius)
    if asset_type == "crystal":
        return generate_crystal(seed=seed, shard_count=args.shards, family=args.family, scale=args.scale)
    if asset_type == "tree":
        return generate_tree(seed=seed, style=args.style, height_scale=args.height_scale)
    if asset_type == "terrain":
        return generate_terrain(seed=seed, resolution=args.resolution, size=args.size, biome=args.biome)
    raise ValueError(f"Unknown asset type: {asset_type}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "generate":
        parser.print_help()
        return 1

    base_seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    out_dir = Path(args.out)

    asset_types = list(GENERATORS_ORDER) if args.asset_type == "all" else [args.asset_type]

    t0 = time.time()
    total = 0
    for i in range(args.count):
        for asset_type in asset_types:
            seed = base_seed + i * 1000 + hash(asset_type) % 997
            # Re-parse per-type defaults when running "all" (its namespace lacks
            # per-type flags like --style/--tint), so every generator still
            # gets sensible parameters.
            type_args = args if args.asset_type != "all" else argparse.Namespace(
                style=None, tint=None, subdivisions=3, radius=1.0,
                shards=None, family=None, scale=1.0, height_scale=1.0,
                resolution=64, size=10.0, biome=None,
            )
            if asset_type == "tree" and type_args.style is None:
                type_args.style = random.Random(seed).choice(list(TREE_STYLES))
            if asset_type == "rock" and type_args.style is None:
                type_args.style = random.Random(seed).choice(["weathered", "angular"])

            asset = _generate_one(asset_type, type_args, seed)
            path = export_asset(asset, out_dir, fmt=args.format)
            total += 1
            print(f"[{total}] {asset_type:8s} -> {path}  (verts={asset.vertex_count}, tris={asset.triangle_count})")

    elapsed = time.time() - t0
    print(f"Done: {total} asset(s) written to {out_dir.resolve()} in {elapsed:.2f}s")
    return 0


GENERATORS_ORDER = ["rock", "crystal", "tree", "terrain"]


if __name__ == "__main__":
    sys.exit(main())
