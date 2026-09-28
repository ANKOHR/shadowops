"""Command line interface for the synthetic ShadowOps demo."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any

from .discovery import candidates, discover, implementation_spec, score_ground_truth
from .fixtures import generate_fixtures
from .model import HONESTY_NOTE


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _emit(value: Any, out: str | None) -> None:
    content = _json(value)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(content)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shadowops",
        description=f"Synthetic process discovery demo. {HONESTY_NOTE}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fixture_parser = subparsers.add_parser("fixtures", help="Generate labelled synthetic activity fixtures")
    fixture_parser.add_argument("--out", required=True, help="Directory for generated activity and ground truth")

    discover_parser = subparsers.add_parser("discover", help="Mine process sequences and write the process graph")
    discover_parser.add_argument("--in", dest="input_dir", required=True, help="Synthetic activity directory")
    discover_parser.add_argument("--out", help="Optional graph JSON output file")

    score_parser = subparsers.add_parser("score", help="Score reconstructed process sequences against fixture labels")
    score_parser.add_argument("--in", dest="input_dir", required=True, help="Synthetic activity directory")
    score_parser.add_argument("--ground-truth", required=True, help="Ground truth JSON from fixtures")
    score_parser.add_argument("--out", help="Optional score JSON output file")

    candidates_parser = subparsers.add_parser("candidates", help="Rank automation candidates with risk and evidence")
    candidates_parser.add_argument("--in", dest="input_dir", required=True, help="Synthetic activity directory")
    candidates_parser.add_argument("--out", help="Optional candidate JSON output file")

    spec_parser = subparsers.add_parser("spec", help="Build an implementation spec for a ranked candidate")
    spec_parser.add_argument("candidate", help="Candidate ID, or 'top' for the highest ranked candidate")
    spec_parser.add_argument("--in", dest="input_dir", required=True, help="Synthetic activity directory")
    spec_parser.add_argument("--out", help="Optional spec JSON output file")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s", stream=sys.stderr)
    args = _parser().parse_args(argv)
    if args.command == "fixtures":
        _emit({"honesty_note": HONESTY_NOTE, **generate_fixtures(args.out)}, None)
        return 0
    result = discover(args.input_dir)
    if args.command == "discover":
        _emit(result, args.out)
        return 0
    if args.command == "score":
        _emit(score_ground_truth(result, args.ground_truth), args.out)
        return 0
    ranked = candidates(result)
    if args.command == "candidates":
        _emit({"honesty_note": HONESTY_NOTE, "candidates": ranked}, args.out)
        return 0
    selected = ranked[0] if args.candidate == "top" and ranked else next(
        (candidate for candidate in ranked if candidate["candidate_id"] == args.candidate), None
    )
    if selected is None:
        print(f"Candidate not found: {args.candidate}", file=sys.stderr)
        return 2
    _emit(implementation_spec(selected), args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

