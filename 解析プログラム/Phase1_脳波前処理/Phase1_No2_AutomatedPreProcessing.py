#!/usr/bin/env python3
"""Run automated Phase 1 preprocessing for selected participant IDs."""

from __future__ import annotations

import argparse
import json

from phase1_pipeline import (
    choose_ids,
    configure_logging,
    preprocess_participant,
    resolve_project_paths,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--participant-id", action="append", dest="participant_ids")
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument(
        "--approved-bad-channel",
        action="append",
        default=[],
        help=(
            "利用者が明示的に除去を許可した候補チャンネル。候補ごとに繰り返し指定する。"
            "指定がない候補は保持したまま処理を続ける。"
        ),
    )
    parser.add_argument(
        "--retained-bad-channel",
        action="append",
        default=[],
        help=(
            "候補figureを確認したうえで、利用者が保持すると決定したチャンネル。"
            "候補ごとに繰り返し指定する。"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = resolve_project_paths()
    ids = choose_ids(paths, args.participant_ids, args.first_only)
    exit_code = 0
    for participant_id in ids:
        log_path = (
            paths.onedrive_root
            / "Phase1_脳波前処理"
            / "No2_AutomatedPreProcessing"
            / f"ID{participant_id}"
            / f"ID{participant_id}_run.log"
        )
        logger = configure_logging(log_path)
        result = preprocess_participant(
            paths,
            participant_id,
            approved_bad_channels=args.approved_bad_channel,
            retained_bad_channels=args.retained_bad_channel,
            logger=logger,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["status"] != "complete":
            exit_code = 2
            break
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
