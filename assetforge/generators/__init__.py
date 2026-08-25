from .crystal import FAMILIES as CRYSTAL_FAMILIES, generate_crystal
from .rock import TINTS as ROCK_TINTS, generate_rock
from .terrain import BIOMES as TERRAIN_BIOMES, generate_terrain
from .tree import STYLE_PRESETS as TREE_STYLES, generate_tree

GENERATORS = {
    "rock": generate_rock,
    "crystal": generate_crystal,
    "tree": generate_tree,
    "terrain": generate_terrain,
}

__all__ = [
    "GENERATORS",
    "generate_rock",
    "generate_crystal",
    "generate_tree",
    "generate_terrain",
    "ROCK_TINTS",
    "CRYSTAL_FAMILIES",
    "TREE_STYLES",
    "TERRAIN_BIOMES",
]
