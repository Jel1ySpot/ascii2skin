"""Image providers (a.k.a. "paint renderers").

A provider turns ``(skin, paint_seed)`` into an RGB image.  Everything in this
module is strictly offline: no HTTP client, no downloader, no sockets.

``PatternWikiRefs`` / ``LocalRefs``
    Reads pre-fetched pattern.wiki renders from a local gallery
    (``refs/<pattern_id>__<weapon_id>/<seed>.webp``).  This is the default and
    the faithful renderer.

``ProceduralProvider``
    Fully synthetic.  Deterministically paints a CS-style
    case-hardened/marble texture parameterised by the seed.  Useful for tests
    and as a fallback when a local gallery is incomplete.

``FallbackProvider``
    Local renders first, procedural rendering for any missing seed.  Also
    entirely offline.
"""

from __future__ import annotations

import os
import zlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .skins import DEFAULT_SKINS, Skin

SEED_MIN = 32
SEED_MAX = 126
DEFAULT_SEEDS = tuple(range(SEED_MIN, SEED_MAX + 1))
IMAGE_EXTS = (".png", ".webp", ".jpg", ".jpeg")


# --------------------------------------------------------------------------
# Local gallery discovery
# --------------------------------------------------------------------------


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".cache"
    return root / "ascii2skin"


def _has_images(root: Path) -> bool:
    """True when *root* looks like a gallery with at least one render."""
    try:
        if not root.is_dir():
            return False
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if any(
                f.suffix.lower() in IMAGE_EXTS and ".thumb" not in f.name
                for f in child.iterdir()
            ):
                return True
    except OSError:
        return False
    return False


def default_refs_root() -> Path | None:
    """Locate the local reference gallery without touching the network.

    Search order:

    1. ``$ASCII2SKIN_REFS``
    2. ``./refs``
    3. ``refs`` next to the project / package root
    4. ``~/.local/share/ascii2skin/refs``
    5. ``$XDG_CACHE_HOME/ascii2skin/refs``
    """

    candidates: list[Path] = []
    env = os.environ.get("ASCII2SKIN_REFS")
    if env:
        candidates.append(Path(env).expanduser())
    candidates.extend(
        [
            Path.cwd() / "refs",
            Path(__file__).resolve().parent.parent / "refs",
            Path.home() / ".local" / "share" / "ascii2skin" / "refs",
            cache_dir() / "refs",
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate.absolute()
        if resolved in seen:
            continue
        seen.add(resolved)
        if _has_images(resolved):
            return resolved
    return None


# --------------------------------------------------------------------------
# Procedural (synthetic, offline) provider
# --------------------------------------------------------------------------


def _crc(text: str) -> int:
    return zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF


def _hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
    import colorsys

    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def _gun_mask(size: tuple[int, int]) -> Image.Image:
    """A very rough rifle silhouette, drawn at 4x and downsampled."""
    w, h = size
    ss = 4
    m = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(m)

    def P(pts):
        return [(int(x * w * ss), int(y * h * ss)) for x, y in pts]

    # barrel + receiver + stock
    d.rounded_rectangle(P([(0.30, 0.44), (0.97, 0.54)]), radius=int(0.012 * h * ss), fill=255)
    d.rounded_rectangle(P([(0.22, 0.40), (0.58, 0.60)]), radius=int(0.02 * h * ss), fill=255)
    d.polygon(P([(0.06, 0.43), (0.24, 0.41), (0.24, 0.62), (0.08, 0.66)]), fill=255)
    # magazine
    d.polygon(P([(0.38, 0.58), (0.49, 0.58), (0.46, 0.80), (0.35, 0.78)]), fill=255)
    # grip
    d.polygon(P([(0.23, 0.56), (0.32, 0.56), (0.30, 0.76), (0.24, 0.74)]), fill=255)
    # front sight
    d.rectangle(P([(0.88, 0.38), (0.90, 0.46)]), fill=255)
    return m.resize(size, Image.LANCZOS)


class ProceduralProvider:
    """Deterministic, offline paint-seed renderer."""

    name = "procedural"

    def __init__(self, native: tuple[int, int] = (320, 214)) -> None:
        self.native = native
        self._mask = _gun_mask(native)
        self._cache: dict[tuple[str, int], Image.Image] = {}

    def _field(self, rng: np.random.Generator) -> np.ndarray:
        w, h = self.native

        def octave(cells_y: int, cells_x: int) -> np.ndarray:
            grid = (rng.random((cells_y, cells_x)) * 255).astype(np.uint8)
            return (
                np.asarray(
                    Image.fromarray(grid, "L").resize((w, h), Image.BICUBIC),
                    dtype=np.float32,
                )
                / 255.0
            )

        return 0.55 * octave(4, 6) + 0.30 * octave(9, 14) + 0.15 * octave(18, 28)

    def render(self, skin: Skin, seed: int) -> Image.Image:
        key = (skin.key, seed)
        if key in self._cache:
            return self._cache[key].copy()

        if not SEED_MIN <= seed <= SEED_MAX:
            raise ValueError(f"paint seed {seed} outside printable ASCII range")

        w, h = self.native
        rng = np.random.default_rng((seed * 2654435761 + _crc(skin.key)) & 0xFFFFFFFF)
        field = self._field(rng)

        hue = ((seed * 47 + _crc(skin.key)) % 360) / 360.0
        dark = np.array(_hsv(hue, 0.65, 0.22), dtype=np.float32)
        mid = np.array(_hsv(hue + 0.11, 0.80, 0.55), dtype=np.float32)
        hot = np.array(_hsv(hue + 0.27, 0.85, 0.98), dtype=np.float32)
        gold = np.array(_hsv(hue + 0.55, 0.55, 0.85), dtype=np.float32)

        # soft 4-stop palette ramp -> looks like case-hardened / fade patterns
        t = field[..., None]
        col = np.where(t < 0.30, dark + (mid - dark) * (t / 0.30), mid)
        hi = np.clip((t - 0.30) / 0.30, 0, 1)
        col = np.where((t >= 0.30) & (t < 0.60), mid + (hot - mid) * hi, col)
        hi2 = np.clip((t - 0.60) / 0.40, 0, 1)
        col = np.where(t >= 0.60, hot + (gold - hot) * (hi2 * 0.55), col)

        # seeded paint splashes / droplets
        splash = Image.new("L", (w, h), 0)
        sd = ImageDraw.Draw(splash)
        for _ in range(3 + seed % 6):
            cx, cy = rng.uniform(0.05, 0.95) * w, rng.uniform(0.05, 0.95) * h
            r = rng.uniform(0.015, 0.09) * min(w, h)
            sd.ellipse([cx - r, cy - r * 0.7, cx + r, cy + r * 0.7], fill=255)
        splash = splash.filter(ImageFilter.GaussianBlur(1.2))
        smask = np.asarray(splash, dtype=np.float32)[..., None] / 255.0
        splash_col = np.array(_hsv(hue + rng.uniform(0.4, 0.6), 0.85, 1.0), dtype=np.float32)
        col = col * (1 - 0.75 * smask) + splash_col * (0.75 * smask)

        # lighting gradient
        y = np.linspace(0.82, 1.12, h, dtype=np.float32)[:, None, None]
        col = np.clip(col * y, 0, 255)

        canvas = np.zeros((h, w, 3), dtype=np.float32)
        canvas[:] = (16, 16, 20)
        mask = np.asarray(self._mask, dtype=np.float32)[..., None] / 255.0
        canvas = canvas * (1 - mask) + col * mask

        img = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), "RGB")
        self._cache[key] = img
        return img.copy()

    def thumb(self, skin: Skin, seed: int, size: int = 64) -> Image.Image:
        return self.render(skin, seed).resize((size, size), Image.LANCZOS)

    def has(self, skin: Skin, seed: int) -> bool:
        return True


# --------------------------------------------------------------------------
# Faithful provider backed by a local render gallery
# --------------------------------------------------------------------------


class RefsMissing(RuntimeError):
    pass


@dataclass
class PatternWikiRefs:
    """Look up real pattern.wiki renders in a local, read-only gallery.

    Layout::

        refs/
          aq_oiled__weapon_ak47/
            71.webp
            71.thumb64.png
            87.webp
            ...

    The gallery is expected to exist on disk before the program starts.  This
    class never downloads anything.  ``root=None`` means "use the default
    local gallery".
    """

    root: str | Path | None = None
    crop_watermark: bool = True
    thumb_cache: str | Path | None = None
    name = "refs"

    def __post_init__(self) -> None:
        root = self.root if self.root is not None else default_refs_root()
        if root is None:
            raise RefsMissing(
                "no local reference gallery found. Put renders under "
                "refs/<pattern_id>__<weapon_id>/<seed>.png, pass --refs DIR, "
                "or set ASCII2SKIN_REFS."
            )
        self.root = Path(root)
        self._thumbs: dict[tuple[str, int, int], Image.Image] = {}
        self._available: dict[str, tuple[int, ...]] = {}

    # -- lookup -------------------------------------------------------------

    def _dir(self, skin: Skin) -> Path:
        return self.root / skin.key

    def path_for(self, skin: Skin, seed: int) -> Path | None:
        d = self._dir(skin)
        for ext in IMAGE_EXTS:
            p = d / f"{seed}{ext}"
            if p.is_file():
                return p
        return None

    def has(self, skin: Skin, seed: int) -> bool:
        return self.path_for(skin, seed) is not None

    def available_seeds(self, skin: Skin) -> tuple[int, ...]:
        """All seeds that have a render on disk (cached per skin)."""
        cached = self._available.get(skin.key)
        if cached is not None:
            return cached
        d = self._dir(skin)
        seeds: set[int] = set()
        try:
            for p in d.iterdir():
                if p.suffix.lower() not in IMAGE_EXTS:
                    continue
                stem = p.stem
                if stem.isdigit():
                    seeds.add(int(stem))
        except OSError:
            pass
        value = tuple(sorted(seeds))
        self._available[skin.key] = value
        return value

    def missing_seeds(
        self,
        skin: Skin,
        seeds: Iterable[int] = DEFAULT_SEEDS,
    ) -> tuple[int, ...]:
        have = set(self.available_seeds(skin))
        return tuple(seed for seed in seeds if seed not in have)

    def complete(
        self,
        skins: Sequence[Skin] = DEFAULT_SKINS,
        seeds: Iterable[int] = DEFAULT_SEEDS,
    ) -> bool:
        wanted = set(seeds)
        return all(wanted.issubset(self.available_seeds(skin)) for skin in skins)

    def coverage(
        self,
        skins: Sequence[Skin] = DEFAULT_SKINS,
        seeds: Iterable[int] = DEFAULT_SEEDS,
    ) -> dict[str, int]:
        wanted = set(seeds)
        return {
            skin.key: len(wanted.intersection(self.available_seeds(skin)))
            for skin in skins
        }

    # -- rendering ----------------------------------------------------------

    def _prepare(self, img: Image.Image, skin: Skin) -> Image.Image:
        img = img.convert("RGB")
        cw, ch = skin.cropped_size
        if self.crop_watermark and img.height > ch:
            img = img.crop((0, 0, min(cw, img.width), ch))
        return img

    def render(self, skin: Skin, seed: int) -> Image.Image:
        p = self.path_for(skin, seed)
        if p is None:
            raise RefsMissing(
                f"no local reference image for {skin.key} seed {seed} under "
                f"{self.root}."
            )
        with Image.open(p) as im:
            return self._prepare(im, skin)

    def thumb(self, skin: Skin, seed: int, size: int = 64) -> Image.Image:
        ck = (skin.key, seed, size)
        if ck in self._thumbs:
            return self._thumbs[ck]

        d = self._dir(skin)
        tp = None
        for ext in (".png", ".webp"):
            candidate = d / f"{seed}.thumb{size}{ext}"
            if candidate.is_file():
                tp = candidate
                break
        if tp is not None:
            with Image.open(tp) as im:
                th = im.convert("RGB")
        else:
            th = self.render(skin, seed).resize((size, size), Image.LANCZOS)
            # Prefer writing the cache next to the render; fall back to the
            # user cache when the gallery is read-only.
            try:
                th.save(d / f"{seed}.thumb{size}.png")
            except OSError:
                cache = Path(self.thumb_cache) if self.thumb_cache else cache_dir() / "thumbs"
                cp = cache / skin.key / f"{seed}.thumb{size}.png"
                try:
                    cp.parent.mkdir(parents=True, exist_ok=True)
                    th.save(cp)
                except OSError:
                    pass
        self._thumbs[ck] = th
        return th


# Friendly alias: the provider is no longer specific to a remote site.
LocalRefs = PatternWikiRefs


class FallbackProvider:
    """Local renders when present, synthetic renders otherwise (offline)."""

    name = "auto"

    def __init__(
        self,
        refs: PatternWikiRefs,
        fallback: ProceduralProvider | None = None,
    ) -> None:
        self.refs = refs
        self.fallback = fallback or ProceduralProvider()

    def has(self, skin: Skin, seed: int) -> bool:
        return True

    def render(self, skin: Skin, seed: int) -> Image.Image:
        if self.refs.has(skin, seed):
            try:
                return self.refs.render(skin, seed)
            except (OSError, RefsMissing):
                pass
        return self.fallback.render(skin, seed)

    def thumb(self, skin: Skin, seed: int, size: int = 64) -> Image.Image:
        if self.refs.has(skin, seed):
            try:
                return self.refs.thumb(skin, seed, size)
            except (OSError, RefsMissing):
                pass
        return self.fallback.thumb(skin, seed, size)


def default_provider() -> PatternWikiRefs | FallbackProvider | ProceduralProvider:
    """Best available offline provider (faithful gallery when complete)."""
    root = default_refs_root()
    if root is None:
        return ProceduralProvider()
    refs = PatternWikiRefs(root)
    if refs.complete():
        return refs
    return FallbackProvider(refs)


def gallery_status(
    root: str | Path | None = None,
    skins: Sequence[Skin] = DEFAULT_SKINS,
    seeds: Iterable[int] = DEFAULT_SEEDS,
) -> dict:
    """Machine-readable summary used by ``ascii2skin refs``."""
    root = Path(root) if root is not None else default_refs_root()
    if root is None:
        raise RefsMissing("no local reference gallery found")
    refs = PatternWikiRefs(root)
    seeds = tuple(seeds)
    rows = []
    for skin in skins:
        missing = refs.missing_seeds(skin, seeds)
        rows.append(
            {
                "key": skin.key,
                "name": skin.name,
                "model": skin.model,
                "available": len(seeds) - len(missing),
                "expected": len(seeds),
                "missing": list(missing),
            }
        )
    complete = all(row["available"] == row["expected"] for row in rows)
    unique = {row["key"]: row["available"] for row in rows}
    return {
        "root": str(root),
        "seeds": [seeds[0], seeds[-1]],
        "total": sum(unique.values()),
        "expected_total": len(unique) * len(seeds),
        "complete": complete,
        "skins": rows,
    }
