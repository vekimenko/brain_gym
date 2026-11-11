#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

from app.cli import build_parser
from app.config import load_env
from db.bootstrap import bootstrap
from workflows.live_mode import run_live_mode
from workflows.offline_mode import run_offline_mode


load_env()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not any([args.url, args.youtube, args.file, args.text]):
        parser.error("Provide an article source using --url, --youtube, --file, or --text.")

    if args.model:
        os.environ["LLM_MODEL"] = args.model
    if args.grade_model:
        os.environ["LLM_GRADE_MODEL"] = args.grade_model

    bootstrap()
    if args.mode == "offline":
        run_offline_mode(args)
    else:
        run_live_mode(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSession interrupted. Progress was saved to SQLite.")
        sys.exit(0)
    except Exception as exc:  # pragma: no cover
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
