#!/usr/bin/env python3
"""Run automated Phase 1 preprocessing for selected participant IDs."""

from __future__ import annotations

import argparse
import json

from phase1_pipeline import (
    choose_ids,
    configure_logging,
    participant_output_directory_name,
    preprocess_participant,
    regenerate_interactive_html_outputs,
    resolve_project_paths,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--participant-id", action="append", dest="participant_ids")
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument(
        "--regenerate-html-only",
        action="store_true",
        help="保存済みICAを再利用し、全時間帯の確認HTMLだけを再生成する。",
    )
    parser.add_argument(
        "--output-label",
        help=(
            "比較検証などの特別実行だけで、出力IDフォルダ名へ付けるラベル。"
            "通常実行では指定しない。"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = resolve_project_paths()
    ids = choose_ids(paths, args.participant_ids, args.first_only)
    exit_code = 0
    for participant_id in ids:
        output_directory = participant_output_directory_name(
            participant_id, args.output_label
        )
        log_path = (
            paths.onedrive_root
            / "Phase1_脳波前処理"
            / "No2_AutomatedPreProcessing"
            / output_directory
            / f"ID{participant_id}_run.log"
        )
        logger = configure_logging(log_path)
        if args.regenerate_html_only:
            result = regenerate_interactive_html_outputs(
                paths,
                participant_id,
                logger=logger,
                output_label=args.output_label,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            continue
        result = preprocess_participant(
            paths,
            participant_id,
            logger=logger,
            output_label=args.output_label,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["status"] != "complete":
            exit_code = 2
            break
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
