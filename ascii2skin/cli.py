"""Command line interface: ``ascii2skin encode/decode/...``.

The CLI is fully offline.  Reference images are read from a local gallery and
are never downloaded by this program.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .codec import decode_raw, decode_sheet, save
from .providers import (
    SEED_MAX,
    SEED_MIN,
    FallbackProvider,
    PatternWikiRefs,
    ProceduralProvider,
    default_refs_root,
    gallery_status,
)
from .skins import DEFAULT_SKINS

EXPECTED_PER_SKIN = SEED_MAX - SEED_MIN + 1
KEY_WIDTH = max(len(s.key) for s in DEFAULT_SKINS)


def _tile(text: str) -> tuple[int, int]:
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("tile must look like 240x160") from exc


def _resolve_refs(args) -> Path | None:
    raw = getattr(args, "refs", None)
    if raw:
        path = Path(raw).expanduser()
        if not path.is_dir():
            raise SystemExit(f"refs directory not found: {path}")
        return path
    return default_refs_root()


def _provider(args):
    kind = getattr(args, "provider", "auto")
    if kind == "procedural":
        return ProceduralProvider()

    root = _resolve_refs(args)
    if kind in ("refs", "patternwiki"):
        if root is None:
            raise SystemExit(
                "no local reference gallery found; pass --refs DIR or set "
                "ASCII2SKIN_REFS (downloading was removed: this tool is offline)"
            )
        return PatternWikiRefs(root)

    # auto: faithful local gallery when complete, otherwise fill gaps offline.
    if root is None:
        return ProceduralProvider()
    refs = PatternWikiRefs(root)
    if refs.complete():
        return refs
    print(
        f"note: {root} is incomplete; missing seeds use the procedural renderer",
        file=sys.stderr,
    )
    return FallbackProvider(refs)


def _describe(provider) -> str:
    if isinstance(provider, PatternWikiRefs):
        return f"refs ({provider.root})"
    if isinstance(provider, FallbackProvider):
        return f"auto ({provider.refs.root} + procedural fill-in)"
    return provider.name


def _print_decoded(decoded) -> None:
    print("index  char  seed  skin")
    for d in decoded:
        ch = d.char if d.char.isprintable() and d.char != " " else repr(d.char)
        print(f"{d.index + 1:5d}  {ch:>4}  {d.seed:4d}  {d.skin.name}  (MAE={d.mae:.6f})")
    text = "".join(d.char for d in decoded)
    print("\ntext:", text)
    if any(d.mae > 2.0 for d in decoded):
        print("warning: some tiles matched poorly (MAE > 2); check skins/refs", file=sys.stderr)


def cmd_encode(args) -> int:
    text = sys.stdin.read() if args.text == "-" else args.text
    if not text:
        print("empty input", file=sys.stderr)
        return 2
    provider = _provider(args)
    result = save(
        text,
        args.out,
        provider=provider,
        tile=args.tile,
        cols=args.cols,
        gap=args.gap,
        labels=args.labels,
        raw=not args.no_raw,
    )
    print(f"source: {_describe(provider)}")
    print(f"sheet : {result['sheet']}")
    print(f"chars : {len(result['items'])}")
    print("seeds : " + " ".join(f"{it.char}={it.seed}" for it in result["items"]))
    return 0


def cmd_decode(args) -> int:
    provider = _provider(args)
    decoded = decode_sheet(
        args.image,
        provider=provider,
        cols=args.cols,
        tile=args.tile,
        gap=args.gap,
    )
    print(f"source: {_describe(provider)}")
    _print_decoded(decoded)
    return 0


def cmd_decode_raw(args) -> int:
    paths: list[Path] = []
    for item in args.paths:
        p = Path(item)
        if p.is_dir():
            paths.extend(sorted(p.glob("*.png")))
        else:
            paths.append(p)
    if not paths:
        print("no input images", file=sys.stderr)
        return 2
    provider = _provider(args)
    decoded = decode_raw(paths, provider=provider)
    print(f"source: {_describe(provider)}")
    _print_decoded(decoded)
    return 0


def cmd_refs(args) -> int:
    root = _resolve_refs(args)
    if root is None:
        print(
            "no local reference gallery found; pass --refs DIR or set ASCII2SKIN_REFS",
            file=sys.stderr,
        )
        return 2

    status = gallery_status(root)
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        state = "complete" if status["complete"] else "INCOMPLETE"
        print(f"refs   : {status['root']}")
        print(f"seeds  : {status['seeds'][0]}..{status['seeds'][1]} (printable ASCII)")
        print(
            f"images : {status['total']}/{status['expected_total']} "
            f"({state})"
        )
        print()
        for i, row in enumerate(status["skins"], 1):
            if row["available"] == row["expected"]:
                mark = "ok"
            else:
                missing = ", ".join(str(s) for s in row["missing"][:8])
                more = "..." if len(row["missing"]) > 8 else ""
                mark = f"missing {len(row['missing'])} ({missing}{more})"
            print(
                f"{i:2d}  {row['key']:{KEY_WIDTH}s} "
                f"{row['available']:3d}/{row['expected']:<3d} {mark}"
            )
    if args.check and not status["complete"]:
        return 1
    return 0


def cmd_skins(args) -> int:
    root = _resolve_refs(args)
    refs = PatternWikiRefs(root) if root else None
    for i, s in enumerate(DEFAULT_SKINS):
        if refs is None:
            have = "  -/-"
        else:
            have = f"{len(refs.available_seeds(s)):3d}/{EXPECTED_PER_SKIN}"
        print(f"{i + 1:2d}  {s.key:{KEY_WIDTH}s} {s.model:4s}  {s.name}  [{have}]")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ascii2skin",
        description="Encode ASCII text as CS skin Paint Seeds (the 'skin secret' algorithm).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument(
            "--provider",
            choices=["auto", "procedural", "refs", "patternwiki"],
            default="auto",
            help="auto (local refs, procedural fallback), procedural, or refs",
        )
        sp.add_argument(
            "--refs",
            help="local reference-image directory (default: $ASCII2SKIN_REFS, ./refs, or bundled refs/)",
        )

    e = sub.add_parser("encode", help="text -> sheet.png + raw/*.png")
    e.add_argument("text", help="ASCII text, or - for stdin")
    e.add_argument("-o", "--out", default="out")
    e.add_argument("--tile", type=_tile, default=(240, 160), help="WxH of one cell (default 240x160)")
    e.add_argument("--cols", type=int, default=6)
    e.add_argument("--gap", type=int, default=8)
    e.add_argument("--labels", action="store_true", help="draw cell numbers on the sheet")
    e.add_argument("--no-raw", action="store_true", help="only write sheet.png")
    common(e)
    e.set_defaults(func=cmd_encode)

    d = sub.add_parser("decode", help="decode a composed sheet.png")
    d.add_argument("image")
    d.add_argument(
        "--cols",
        type=int,
        help=(
            "images per row (default: 6 when the PNG has no layout metadata); "
            "tile width is inferred when --tile is omitted"
        ),
    )
    d.add_argument(
        "--tile",
        type=_tile,
        help="cell size WxH; inferred from --cols and 3:2 aspect when omitted",
    )
    d.add_argument("--gap", type=int, help="cell gap in pixels (default: 8)")
    common(d)
    d.set_defaults(func=cmd_decode)

    dr = sub.add_parser("decode-raw", help="decode full-resolution per-character images")
    dr.add_argument("paths", nargs="+")
    common(dr)
    dr.set_defaults(func=cmd_decode_raw)

    r = sub.add_parser("refs", help="report the local reference gallery (offline)")
    r.add_argument("--refs", help="local reference-image directory")
    r.add_argument("--json", action="store_true", help="machine-readable output")
    r.add_argument("--check", action="store_true", help="exit 1 when a seed is missing")
    r.set_defaults(func=cmd_refs)

    s = sub.add_parser("skins", help="list the skin order and local coverage")
    s.add_argument("--refs", help="local reference-image directory")
    s.set_defaults(func=cmd_skins)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
