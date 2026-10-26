"""ascii2skin: encode ASCII strings as CS skin Paint Seeds.

Everything runs offline against the local reference gallery in ``refs/``.
"""

from .codec import (
    CharImage,
    DecodedChar,
    char_to_seed,
    compose,
    decode_raw,
    decode_sheet,
    decode_tile,
    encode,
    fit_tile,
    save,
    seed_to_char,
)
from .providers import (
    DEFAULT_SEEDS,
    FallbackProvider,
    LocalRefs,
    PatternWikiRefs,
    ProceduralProvider,
    RefsMissing,
    cache_dir,
    default_provider,
    default_refs_root,
    gallery_status,
)
from .skins import DEFAULT_SKINS, SKINS_BY_KEY, Skin

__all__ = [
    "DEFAULT_SEEDS",
    "DEFAULT_SKINS",
    "SKINS_BY_KEY",
    "CharImage",
    "DecodedChar",
    "FallbackProvider",
    "LocalRefs",
    "PatternWikiRefs",
    "ProceduralProvider",
    "RefsMissing",
    "Skin",
    "cache_dir",
    "char_to_seed",
    "compose",
    "decode_raw",
    "decode_sheet",
    "decode_tile",
    "default_provider",
    "default_refs_root",
    "encode",
    "fit_tile",
    "gallery_status",
    "save",
    "seed_to_char",
]
