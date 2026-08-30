"""Read-only module surface; adoption stays behind trusted host adapters."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import (
    CandidateSource,
    CapabilityNeed,
    ResearchWorkspace,
    inspect_candidate,
    inspect_internal,
    to_json,
)
from .models import ReuseError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    internal = sub.add_parser(
        "inspect", help="Inspect internal prior art; JSON to stdout"
    )
    internal.add_argument("--target", type=Path, required=True)
    internal.add_argument("--need", required=True)
    internal.add_argument("--term", action="append", default=[])
    candidate = sub.add_parser(
        "candidate", help="Acquire and statically inspect a candidate"
    )
    candidate.add_argument("--target", type=Path, required=True)
    candidate.add_argument("--source", required=True)
    candidate.add_argument("--expected-commit")
    candidate.add_argument("--allow-https-host", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_internal(
                args.target, CapabilityNeed(args.need, tuple(args.term))
            )
        else:
            source = (
                CandidateSource.https(args.source, args.expected_commit)
                if args.source.startswith("https://")
                else CandidateSource.local(Path(args.source), args.expected_commit)
            )
            with ResearchWorkspace(
                args.target, allowed_https_hosts=tuple(args.allow_https_host)
            ) as work:
                result = inspect_candidate(work.acquire(source))
        print(to_json(result))
        return 0
    except (ReuseError, OSError, UnicodeError) as exc:
        # No candidate-controlled stderr or traceback is forwarded.
        print(
            to_json(
                {
                    "status": "blocked",
                    "error_type": type(exc).__name__,
                    "message": "Inspection failed; check scope, bounds and source.",
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
