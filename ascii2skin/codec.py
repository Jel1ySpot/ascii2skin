"""The `skin secret` codec: ASCII text <-> paint seeds <-> images."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo

from .providers import SEED_MAX, SEED_MIN, default_provider
from .skins import DEFAULT_SKINS, Skin

BG = (16, 16, 20)  # pattern.wiki background colour
META_KEY = "ascii2skin"


@dataclass
class CharImage:
    index: int
    char: str
    seed: int
    skin: Skin
    image: Image.Image


@dataclass
class DecodedChar:
    index: int
    char: str
    seed: int
    skin: Skin
    mae: float


# --------------------------------------------------------------------------
# encoding
# --------------------------------------------------------------------------


def char_to_seed(ch: str) -> int:
    if len(ch) != 1:
        raise ValueError("char_to_seed expects exactly one character")
    seed = ord(ch)
    if not SEED_MIN <= seed <= SEED_MAX:
        raise ValueError(
            f"character {ch!r} (ord={seed}) is outside printable ASCII "
            f"{SEED_MIN}..{SEED_MAX}"
        )
    return seed


def seed_to_char(seed: int) -> str:
    return chr(seed)


def encode(
    text: str,
    provider=None,
    skins: Sequence[Skin] = DEFAULT_SKINS,
) -> list[CharImage]:
    """Map every character to (skin, paint seed=ord(char)) and render it."""
    provider = provider or default_provider()
    if not skins:
        raise ValueError("need at least one skin")
    out: list[CharImage] = []
    for i, ch in enumerate(text):
        seed = char_to_seed(ch)
        skin = skins[i % len(skins)]
        out.append(CharImage(i, ch, seed, skin, provider.render(skin, seed)))
    return out


# --------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------


def fit_tile(img: Image.Image, tile: tuple[int, int], bg=BG) -> Image.Image:
    """Letterbox `img` into exactly `tile` pixels (deterministic)."""
    tw, th = tile
    w, h = img.size
    scale = min(tw / w, th / h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    resized = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (tw, th), bg)
    canvas.paste(resized, ((tw - nw) // 2, (th - nh) // 2))
    return canvas


def compose(
    items: Sequence[CharImage],
    tile: tuple[int, int] = (240, 160),
    cols: int = 6,
    gap: int = 8,
    bg=BG,
    labels: bool = False,
    skins: Sequence[Skin] = DEFAULT_SKINS,
) -> tuple[Image.Image, dict]:
    """Contact-sheet of all characters, plus geometry metadata."""
    if not items:
        raise ValueError("nothing to compose")
    n = len(items)
    if cols <= 0 or cols > n:
        cols = n
    rows = math.ceil(n / cols)
    tw, th = tile
    W = cols * tw + (cols + 1) * gap
    H = rows * th + (rows + 1) * gap
    sheet = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(sheet)

    for k, it in enumerate(items):
        r, c = divmod(k, cols)
        x = gap + c * (tw + gap)
        y = gap + r * (th + gap)
        sheet.paste(fit_tile(it.image, tile, bg), (x, y))
        if labels:
            draw.rectangle([x, y, x + 46, y + 14], fill=bg)
            draw.text((x + 3, y + 2), f"#{k + 1}", fill=(200, 200, 200))

    meta = {
        "v": 1,
        "count": n,
        "cols": cols,
        "rows": rows,
        "tile": [tw, th],
        "gap": gap,
        "bg": list(bg),
        "skins": [it.skin.key for it in items],
        "seeds": [it.seed for it in items],
    }
    return sheet, meta


def save(
    text: str,
    out_dir: str | Path,
    provider=None,
    skins: Sequence[Skin] = DEFAULT_SKINS,
    tile: tuple[int, int] = (240, 160),
    cols: int = 6,
    gap: int = 8,
    labels: bool = False,
    raw: bool = True,
) -> dict:
    provider = provider or default_provider()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    items = encode(text, provider, skins)
    sheet, meta = compose(items, tile, cols, gap, labels=labels, skins=skins)

    pnginfo = PngInfo()
    pnginfo.add_text(META_KEY, json.dumps(meta))
    sheet_path = out_dir / "sheet.png"
    sheet.save(sheet_path, pnginfo=pnginfo)

    if raw:
        raw_dir = out_dir / "raw"
        raw_dir.mkdir(exist_ok=True)
        # remove stale raw tiles from earlier runs
        for old in raw_dir.glob("*.png"):
            old.unlink()
        for it in items:
            it.image.save(raw_dir / f"{it.index + 1:02d}.png")

    (out_dir / "manifest.json").write_text(
        json.dumps(
            {
                "text": text,
                "seed_chars": [{"index": it.index + 1, "char": it.char, "seed": it.seed} for it in items],
                "layout": meta,
                "sheet": str(sheet_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    return {"sheet": sheet_path, "meta": meta, "items": items}


# --------------------------------------------------------------------------
# decoding
# --------------------------------------------------------------------------


def _mae(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return float("inf")
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def decode_tile(
    img: Image.Image,
    skin: Skin,
    provider=None,
    tile_size: tuple[int, int] | None = None,
    seeds: Iterable[int] = range(SEED_MIN, SEED_MAX + 1),
    thumb: int = 64,
    top_k: int = 8,
) -> tuple[int, float]:
    """Brute-force which paint seed produced `img` for this skin.

    ``tile_size`` must be given when `img` is a letterboxed sheet cell; omit it
    when `img` is a full native-resolution render.
    """
    provider = provider or default_provider()
    target = fit_tile(img, tile_size) if tile_size else img.convert("RGB")
    target_thumb = np.asarray(target.resize((thumb, thumb), Image.LANCZOS), dtype=np.int16)

    scored: list[tuple[float, int]] = []
    for seed in seeds:
        if not provider.has(skin, seed):
            continue
        cand_thumb = np.asarray(provider.thumb(skin, seed, thumb), dtype=np.int16)
        scored.append((_mae(target_thumb, cand_thumb), seed))
    if not scored:
        raise RuntimeError(f"no candidate renders available for {skin.key}")
    scored.sort()

    best_seed, best_mae = scored[0][1], float("inf")

    def check(seed: int) -> bool:
        """Verify one seed at full resolution; True when it is pixel-exact."""
        nonlocal best_seed, best_mae
        cand = provider.render(skin, seed)
        cand = fit_tile(cand, tile_size) if tile_size else cand.convert("RGB")
        m = _mae(np.asarray(target), np.asarray(cand))
        if m < best_mae:
            best_seed, best_mae = seed, m
        return m == 0.0

    checked: set[int] = set()
    for _, seed in scored[: max(1, top_k)]:
        checked.add(seed)
        if check(seed):
            return best_seed, best_mae

    # The 64px prefilter is approximate (letterboxing/resampling).  If no
    # pixel-exact candidate was found, fall back to a full-resolution search
    # instead of silently returning a near-miss.
    if best_mae > 0.01:
        for _, seed in scored:
            if seed in checked:
                continue
            if check(seed):
                break
    return best_seed, best_mae


def decode_raw(
    paths: Sequence[str | Path],
    provider=None,
    skins: Sequence[Skin] = DEFAULT_SKINS,
) -> list[DecodedChar]:
    provider = provider or default_provider()
    out: list[DecodedChar] = []
    for i, p in enumerate(paths):
        skin = skins[i % len(skins)]
        with Image.open(p) as im:
            seed, mae = decode_tile(im.convert("RGB"), skin, provider)
        out.append(DecodedChar(i, chr(seed), seed, skin, mae))
    return out


def decode_sheet(
    path: str | Path,
    provider=None,
    skins: Sequence[Skin] = DEFAULT_SKINS,
    cols: int | None = None,
    tile: tuple[int, int] | None = None,
    gap: int | None = None,
) -> list[DecodedChar]:
    provider = provider or default_provider()
    meta = None
    with Image.open(path) as src:
        raw_meta = src.info.get(META_KEY)
        if raw_meta:
            meta = json.loads(raw_meta)
        im = src.convert("RGB")
        im.load()

    if meta:
        cols = cols or meta["cols"]
        tile = tile or tuple(meta["tile"])
        gap = gap if gap is not None else meta["gap"]
        skin_by_key = {s.key: s for s in skins}
        skin_seq = [skin_by_key.get(k) for k in meta["skins"]]
        if any(s is None for s in skin_seq):
            raise RuntimeError("sheet references skins not present in the provided skin list")
        n = meta["count"]
    else:
        if cols is None or tile is None:
            raise RuntimeError(
                "no ascii2skin metadata in this PNG; pass --cols and --tile explicitly"
            )
        gap = 8 if gap is None else gap
        n = None
        skin_seq = None

    tw, th = tile
    gap = int(gap)
    if n is None:
        per_row = (im.width - gap) // (tw + gap)
        rows = (im.height - gap) // (th + gap)
        n = per_row * rows
        cols = per_row

    out: list[DecodedChar] = []
    for k in range(n):
        r, c = divmod(k, cols)
        x = gap + c * (tw + gap)
        y = gap + r * (th + gap)
        cell = im.crop((x, y, x + tw, y + th))
        skin = skin_seq[k] if skin_seq else skins[k % len(skins)]
        seed, mae = decode_tile(cell, skin, provider, tile_size=(tw, th))
        out.append(DecodedChar(k, chr(seed), seed, skin, mae))
    return out
