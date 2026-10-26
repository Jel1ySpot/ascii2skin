"""Tests: offline round-trip, local gallery decoding, and exact reproduction
of the original `skin secret` attachment images."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ascii2skin import (
    DEFAULT_SKINS,
    FallbackProvider,
    PatternWikiRefs,
    ProceduralProvider,
    decode_raw,
    decode_sheet,
    default_provider,
    default_refs_root,
    encode,
    gallery_status,
    save,
)
from ascii2skin.providers import SEED_MAX, SEED_MIN

FLAG = "GWHT{CS_1s_th3_bes7_FP5_G@ME}"
ATT = Path(
    os.environ.get(
        "SKIN_SECRET_ATT",
        Path(__file__).resolve().parent.parent / "skin secret" / "att" / "extracted",
    )
)


def test_procedural_roundtrip(tmp_path: Path) -> None:
    provider = ProceduralProvider()
    text = "Hello, CS! 123"
    save(text, tmp_path, provider=provider, raw=True, cols=5)
    decoded = decode_sheet(tmp_path / "sheet.png", provider)
    assert "".join(d.char for d in decoded) == text
    assert all(d.mae < 1e-9 for d in decoded)


def test_refs_provider_discriminates_all_seeds(tmp_path: Path) -> None:
    """A file-backed provider must pick the right seed out of all 95."""
    paint = ProceduralProvider()
    refs = PatternWikiRefs(tmp_path / "refs")
    skins = DEFAULT_SKINS[:3]
    for skin in skins:
        d = refs.root / skin.key
        d.mkdir(parents=True, exist_ok=True)
        for seed in range(SEED_MIN, SEED_MAX + 1):
            paint.render(skin, seed).save(d / f"{seed}.png")

    text = "Az9"
    items = encode(text, refs, skins)
    decoded = decode_raw(_dump(items, tmp_path), refs, skins)
    assert "".join(d.char for d in decoded) == text
    assert all(d.mae == 0.0 for d in decoded)


def test_bundled_gallery_is_complete() -> None:
    """The shipped refs/ must cover every printable seed for every skin."""
    root = default_refs_root()
    assert root is not None, "local refs gallery not found"
    refs = PatternWikiRefs(root)
    missing = {}
    for skin in DEFAULT_SKINS:
        gaps = refs.missing_seeds(skin)
        if gaps:
            missing[skin.key] = gaps
    assert missing == {}
    assert refs.has(DEFAULT_SKINS[0], ord("G"))


def test_gallery_status_dedupes_repeated_skin() -> None:
    status = gallery_status()
    assert status["complete"] is True
    assert status["total"] == status["expected_total"] == 2660
    assert len(status["skins"]) == 29


def test_default_provider_is_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Encoding/decoding must not create a socket even with the real gallery."""

    def deny(*_args, **_kwargs):
        raise AssertionError("ascii2skin attempted network access")

    monkeypatch.setattr(socket, "socket", deny)

    text = "Az9"
    provider = default_provider()
    save(text, tmp_path, provider=provider, raw=True, cols=3)
    decoded = decode_sheet(tmp_path / "sheet.png", provider)
    assert "".join(d.char for d in decoded) == text


def test_fallback_provider_fills_missing_seeds(tmp_path: Path) -> None:
    """A partial gallery still round-trips by falling back to procedural."""
    paint = ProceduralProvider()
    refs = PatternWikiRefs(tmp_path / "refs")
    skin = DEFAULT_SKINS[0]
    d = refs.root / skin.key
    d.mkdir(parents=True, exist_ok=True)
    paint.render(skin, ord("A")).save(d / f"{ord('A')}.png")

    provider = FallbackProvider(refs)
    text = "Az"
    save(text, tmp_path, provider=provider, raw=True, cols=2)
    decoded = decode_sheet(tmp_path / "sheet.png", provider)
    assert "".join(d.char for d in decoded) == text


def _dump(items, tmp_path: Path) -> list[Path]:
    paths = []
    for it in items:
        p = tmp_path / f"item{it.index}.png"
        it.image.save(p)
        paths.append(p)
    return paths


@pytest.mark.skipif(not (ATT / "1.png").is_file(), reason="original attachment not found")
def test_reproduce_original_images(tmp_path: Path) -> None:
    """Encoding with the compressed local renders must match 1.png .. 29.png closely."""
    assert len(FLAG) == 29

    root = default_refs_root()
    assert root is not None
    refs = PatternWikiRefs(root)
    assert refs.complete()

    items = encode(FLAG, refs)
    assert [it.seed for it in items] == [ord(c) for c in FLAG]
    for i, it in enumerate(items):
        expected = np.asarray(Image.open(ATT / f"{i + 1}.png").convert("RGB"), dtype=np.int16)
        got = np.asarray(it.image.convert("RGB"), dtype=np.int16)
        assert got.shape == expected.shape
        mae = float(np.abs(got - expected).mean())
        assert mae < 2.0, f"tile {i + 1} differs (MAE={mae:.3f})"

    decoded = decode_raw(_dump(items, tmp_path), refs)
    assert "".join(d.char for d in decoded) == FLAG

    res = save(FLAG, tmp_path / "out", provider=refs)
    assert "".join(d.char for d in decode_sheet(res["sheet"], refs)) == FLAG


def test_unsupported_char() -> None:
    with pytest.raises(ValueError):
        encode("caf\u00e9", ProceduralProvider())
