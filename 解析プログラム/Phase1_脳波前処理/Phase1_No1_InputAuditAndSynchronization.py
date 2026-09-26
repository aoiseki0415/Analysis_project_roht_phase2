#!/usr/bin/env python3
"""Audit EEG/behavior input and create synchronization manifests."""

from __future__ import annotations

import argparse

from phase1_pipeline import (
    audit_participant,
    choose_ids,
    configure_logging,
    resolve_project_paths,
    write_audit_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--participant-id", action="append", dest="participant_ids")
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument(
        "--skip-local-data-output",
        action="store_true",
        help=(
            "比較検証用に、ローカルの解析用マニフェストを保存せず"
            "OneDriveの入力監査成果だけを作成する。"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = resolve_project_paths()
    ids = choose_ids(paths, args.participant_ids, args.first_only)
    for participant_id in ids:
        log_path = (
            paths.onedrive_root
            / "Phase1_脳波前処理"
            / "No1_InputAuditAndSynchronization"
            / f"ID{participant_id}_run.log"
        )
        logger = configure_logging(log_path)
        audit = audit_participant(paths, participant_id, logger)
        local_path, qc_path = write_audit_outputs(
            paths,
            participant_id,
            audit,
            save_local_manifest=not args.skip_local_data_output,
        )
        logger.info("入力監査出力: %s | %s", local_path, qc_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
