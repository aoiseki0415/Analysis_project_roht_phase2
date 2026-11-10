"""No8–9 paired IAF Change grand-averages from immutable saved v3 estimates.

This module never calls Welch, spectral smoothing, or peak estimation.  The
command line has fixed production roots; parameterized helpers enable synthetic
tests without writing outside pytest's temporary directory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
from phase4_iaf import (
    ANALYSES,
    DEFAULT_CACHE_ROOT,
    DEFAULT_OUTPUT_ROOT,
    SCHEMA,
    config_hash,
    sha256_file,
    write_json,
)

VERSION = "phase4-iaf-change-grand-average-2026-11-10-v3-scoped"
BASE = DEFAULT_OUTPUT_ROOT / "Phase4_脳波解析"
CONDITIONS = ("Eye Drop", "Control")
PRODUCTS = ("CCube", "VRohtoPremium")
COHORTS = ("AllAvailable", "SelectedParticipants")
ADOPTION = "Grand-average採用（追加選別版）"
SELECTION_SCHEMA = "phase4-iaf-selection-setwise-2026-11-10-v3"
ACTIVE_SELECTION_ANALYSES = {"8": "Pz", "9": "Fz"}
SELECTED_COUNTS = {
    8: {"CCube": 12, "VRohtoPremium": 10},
    9: {"CCube": 11, "VRohtoPremium": 10},
}
KEYS = ["pair_id", "condition", "position"]
TABLE_NAMES = ("ParticipantIAFChange.csv", "GroupSummary.csv", "InclusionByInterval.csv")


def interval_labels(number: int) -> list[str]:
    if number not in ANALYSES:
        raise ValueError("Unknown IAF analysis")
    return [str(i) for i in range(1, 7)]


def read_manifest(path: Path) -> dict[str, dict[str, str]]:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = ("first_session_id", "second_session_id", "drops_session_id", "product")
    if set(frame.columns) != set(required) or len(frame) != 40:
        raise ValueError("Manifest requires exactly 40 pairs and four correspondence columns")
    pairs: dict[str, dict[str, str]] = {}
    sessions = []
    for row in frame.to_dict("records"):
        first, second, drops = (row[k] for k in required[:3])
        if not all(re.fullmatch(r"[0-9]+", x) for x in (first, second, drops)):
            raise ValueError("Manifest session IDs must be numeric strings")
        if first == second or drops not in (first, second) or row["product"] not in PRODUCTS:
            raise ValueError("Invalid session, condition or product correspondence")
        pair = f"{first}-{second}"
        if pair in pairs:
            raise ValueError("Duplicate participant pair")
        pairs[pair] = {
            **row,
            "Eye Drop": drops,
            "Control": second if drops == first else first,
        }
        sessions.extend((first, second))
    if len(set(sessions)) != 80 or Counter(r["product"] for r in pairs.values()) != dict.fromkeys(
        PRODUCTS, 20
    ):
        raise ValueError("Manifest requires 80 distinct sessions and 20 pairs per product")
    return pairs


def load_selection(
    json_path: Path,
    csv_path: Path,
    manifest: dict[str, dict[str, str]],
    *,
    expected_schema: str = SELECTION_SCHEMA,
    expected_counts: dict[int, dict[str, int]] | None = None,
) -> pd.DataFrame:
    expected_counts = SELECTED_COUNTS if expected_counts is None else expected_counts
    record = json.loads(json_path.read_text(encoding="utf-8"))
    if (
        record.get("schema") != expected_schema
        or record.get("active_analyses") != ACTIVE_SELECTION_ANALYSES
        or set(record.get("manual_exclusions", {})) != set(ACTIVE_SELECTION_ANALYSES)
    ):
        raise ValueError("Selection schema/active analysis mapping is not current No8/9")
    if record.get("status") != "final":
        raise ValueError("Only a finalized selection is accepted")
    frame = pd.DataFrame(record["decisions"]).astype(str)
    counterpart = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    required = {
        "analysis_number",
        "channel",
        "product",
        "pair_id",
        ADOPTION,
        "採否確定状態",
        "利用者指定追加除外",
        "採否理由",
    }
    if set(frame.columns) != required or set(counterpart.columns) != required:
        raise ValueError("Frozen selection columns mismatch")
    keys = ["analysis_number", "pair_id"]
    if len(frame) != 80 or frame.duplicated(keys).any():
        raise ValueError("Selection requires exactly 80 distinct No/pair decisions")
    pd.testing.assert_frame_equal(
        frame.sort_values(keys).reset_index(drop=True).sort_index(axis=1),
        counterpart.sort_values(keys).reset_index(drop=True).sort_index(axis=1),
    )
    for number, (channel, _, _) in ANALYSES.items():
        subset = frame.loc[frame.analysis_number == str(number)]
        if set(subset.pair_id) != set(manifest) or not subset.channel.eq(channel).all():
            raise ValueError("Selection No/channel/pair mismatch")
        manual = record["manual_exclusions"][str(number)]
        if set(manual) != set(PRODUCTS):
            raise ValueError("Manual exclusions product keys mismatch")
        for row in subset.to_dict("records"):
            if row["product"] != manifest[row["pair_id"]]["product"]:
                raise ValueError("Selection product does not match manifest")
            if row[ADOPTION] not in ("する", "しない") or row["採否確定状態"] != "確定":
                raise ValueError("Selection decision is not final binary adoption")
            is_manual = row["pair_id"] in manual[row["product"]]
            if row["利用者指定追加除外"] != ("あり" if is_manual else "なし"):
                raise ValueError("Manual exclusion flag mismatch")
            if is_manual and row[ADOPTION] != "しない":
                raise ValueError("Manually excluded pair cannot be selected")
        for product in PRODUCTS:
            named = manual[product]
            if len(named) != len(set(named)) or any(
                p not in manifest or manifest[p]["product"] != product for p in named
            ):
                raise ValueError("Manual exclusion pair/product mismatch")
            count = int(((subset[ADOPTION] == "する") & (subset["product"] == product)).sum())
            if count != expected_counts[number][product]:
                raise ValueError("Frozen selected cohort count mismatch")
    frame["analysis_number"] = frame.analysis_number.astype(int)
    return frame


def validate_estimates(
    frame: pd.DataFrame, number: int, manifest: dict[str, dict[str, str]]
) -> pd.DataFrame:
    """Check saved values and correspondence; do not estimate a new peak."""
    frame = frame.copy()
    required = {
        "pair_id",
        "session_id",
        "condition",
        "product",
        "analysis_number",
        "channel",
        "set_number",
        "interval",
        "position",
        "frequency_hz",
        "quality",
        "peak_input_dataset",
        "smoothing_points",
        "smoothing_passes",
    }
    if not required.issubset(frame.columns):
        raise ValueError("Missing saved estimate columns")
    for key in ("pair_id", "session_id", "condition", "product", "channel", "interval"):
        frame[key] = frame[key].astype(str)
    labels = interval_labels(number)
    if len(frame) != len(manifest) * 2 * len(labels) or frame.duplicated(KEYS).any():
        raise ValueError("Estimate count or pair-condition-position duplicate")
    if set(frame.pair_id) != set(manifest):
        raise ValueError("Estimate participant set differs from manifest")
    if (
        not frame.analysis_number.eq(number).all()
        or not frame.channel.eq(ANALYSES[number][0]).all()
    ):
        raise ValueError("Estimate analysis/channel mismatch")
    if not (
        frame.peak_input_dataset.eq("smoothed_mean_psd_uv2_hz").all()
        and frame.smoothing_points.eq(5).all()
        and frame.smoothing_passes.eq(1).all()
    ):
        raise ValueError("Estimate does not use the current once-smoothed v3 method")
    for pair, person in manifest.items():
        pp = frame.loc[frame.pair_id == pair]
        if set(pp.condition) != set(CONDITIONS) or not pp["product"].eq(person["product"]).all():
            raise ValueError("Estimate product/conditions mismatch")
        for condition in CONDITIONS:
            cc = pp.loc[pp.condition == condition].sort_values("position")
            if not cc.session_id.eq(person[condition]).all() or list(cc.position) != list(
                range(1, len(labels) + 1)
            ):
                raise ValueError("Estimate session correspondence or fixed interval grid mismatch")
            observed = [
                str(int(r.set_number)) + (r.interval if r.interval != "whole" else "")
                for r in cc.itertuples()
            ]
            if observed != labels or not cc.interval.eq("whole").all():
                raise ValueError("Estimate Set/half ordering mismatch")
    values = frame.frequency_hz.to_numpy(dtype=float)
    if np.isinf(values).any():
        raise ValueError("Infinite IAF is invalid, not a missing value")
    finite = np.isfinite(values)
    if not np.all((values[finite] >= 8) & (values[finite] <= 15)) or not np.allclose(
        values[finite] * 10, np.round(values[finite] * 10), rtol=0, atol=1e-10
    ):
        raise ValueError("Saved IAF is outside the 8–15 Hz, 0.1 Hz grid")
    if (
        not frame.loc[finite, "quality"].eq("ok").all()
        or frame.loc[~finite, "quality"].eq("ok").any()
    ):
        raise ValueError("Saved availability and quality disagree")
    return frame.sort_values(KEYS).reset_index(drop=True)


def read_stored_cache_iaf(
    paths: list[Path], manifest: dict[str, dict[str, str]]
) -> dict[int, pd.DataFrame]:
    """Read only saved peak attributes, never raw EEG or periodogram arrays."""
    rows: dict[int, list[dict[str, Any]]] = {n: [] for n in ANALYSES}
    seen = set()
    for path in paths:
        with h5py.File(path, "r") as handle:
            attrs = handle.attrs
            if attrs.get("schema") != SCHEMA or attrs.get("calc_config_sha256") != config_hash():
                raise ValueError("Unknown cache schema or computation configuration")
            if not bool(attrs.get("complete", False)):
                raise ValueError("Incomplete IAF cache")
            pair, sid, condition, product = (
                str(attrs[k]) for k in ("pair_id", "session_id", "condition", "product")
            )
            if pair not in manifest or condition not in CONDITIONS or sid in seen:
                raise ValueError("Cache has unknown or duplicate session")
            person = manifest[pair]
            if sid != person[condition] or product != person["product"]:
                raise ValueError("Cache condition/product correspondence mismatch")
            for key in ("first_session_id", "second_session_id", "drops_session_id"):
                if str(attrs[key]) != person[key]:
                    raise ValueError("Cache participant metadata mismatch")
            seen.add(sid)
            for number, (channel, _, _) in ANALYSES.items():
                for position, label in enumerate(interval_labels(number), 1):
                    set_number = int(label[0])
                    interval = "whole"
                    if f"Set{set_number}" in handle:
                        peak = handle[f"Set{set_number}/{interval}/peaks/{channel}"]
                        frequency = float(peak.attrs["frequency_hz"])
                        quality = str(peak.attrs["quality"])
                    else:
                        frequency, quality = np.nan, "missing_set"
                    rows[number].append(
                        {
                            "pair_id": pair,
                            "session_id": sid,
                            "condition": condition,
                            "product": product,
                            "position": position,
                            "frequency_hz": frequency,
                            "quality": quality,
                        }
                    )
    expected_sessions = {person[c] for person in manifest.values() for c in CONDITIONS}
    if seen != expected_sessions:
        raise ValueError("Cache must contain every manifest session exactly once")
    return {n: pd.DataFrame(rr).sort_values(KEYS).reset_index(drop=True) for n, rr in rows.items()}


def assert_hashes(fingerprints: dict[str, str]) -> None:
    for name, expected in fingerprints.items():
        path = Path(name)
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"Protected input changed: {path}")


def preflight(
    base: Path, cache_root: Path, manifest_path: Path
) -> tuple[dict[int, pd.DataFrame], pd.DataFrame, dict[str, str]]:
    manifest = read_manifest(manifest_path)
    review = base / ANALYSES[8][2] / "Sub/PeakClarityReview"
    selection_json = review / "GrandAverageSelection_Final.json"
    selection_csv = review / "GrandAverageSelection_Final.csv"
    selection_log = base / ANALYSES[8][2] / "Sub/logs/PeakClarityReview_SelectionFinalized.json"
    frozen = json.loads(selection_log.read_text(encoding="utf-8"))
    for path in (selection_json, selection_csv):
        if frozen.get("outputs_sha256", {}).get(str(path)) != sha256_file(path):
            raise ValueError("Final selection does not match its frozen audit hash")
    selection = load_selection(selection_json, selection_csv, manifest)
    caches = sorted(cache_root.glob("*.h5"))
    if len(caches) != 80:
        raise ValueError("Expected exactly 80 saved IAF caches")
    protected = [manifest_path, selection_json, selection_csv, selection_log, *caches]
    frames = {}
    for number, (channel, _, folder) in ANALYSES.items():
        root = base / folder
        saved_manifest = root / "Sub/tables/ParticipantManifest.csv"
        if read_manifest(saved_manifest) != manifest:
            raise ValueError("The two saved participant manifests disagree")
        estimates = root / f"Sub/tables/No{number}_IAF_Estimates.csv"
        frames[number] = validate_estimates(
            pd.read_csv(estimates, dtype={"session_id": str, "pair_id": str}), number, manifest
        )
        protected.extend((saved_manifest, estimates))
        tag = "SetwiseIAF"
        for pair, person in manifest.items():
            path = (
                root
                / person["product"]
                / "Individual"
                / (f"Pair{pair}_No{number}_{channel}_{tag}_ThreePanel.png")
            )
            if not path.is_file():
                raise ValueError("Expected protected individual PNG is missing")
            protected.append(path)
    fingerprints = {str(path): sha256_file(path) for path in protected}
    stored = read_stored_cache_iaf(caches, manifest)
    columns = [
        "pair_id",
        "session_id",
        "condition",
        "product",
        "position",
        "frequency_hz",
        "quality",
    ]
    for number, frame in frames.items():
        pd.testing.assert_frame_equal(
            frame[columns],
            stored[number][columns],
            check_dtype=False,
            check_exact=False,
            rtol=0,
            atol=1e-12,
        )
        for pair in selection.loc[
            (selection.analysis_number == number) & (selection[ADOPTION] == "する"), "pair_id"
        ]:
            baseline = frame.loc[(frame.pair_id == pair) & (frame.position == 1), "frequency_hz"]
            if not np.isfinite(baseline).all():
                raise ValueError("Frozen selected participant has unavailable baseline")
    assert_hashes(fingerprints)
    return frames, selection, fingerprints


def compute_tables(
    estimates: pd.DataFrame, selection: pd.DataFrame, number: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Difference first, then equal-participant mean; paired OR never edits IAF."""
    labels = interval_labels(number)
    participant_rows, inclusion_rows = [], []
    decisions = selection.loc[selection.analysis_number == number].set_index("pair_id")
    if set(decisions.index) != set(estimates.pair_id) or decisions.index.has_duplicates:
        raise ValueError("Selection/estimate participant mismatch")
    for pair in sorted(estimates.pair_id.unique()):
        pp = estimates.loc[estimates.pair_id == pair]
        product = pp["product"].iloc[0]
        selected = decisions.loc[pair, ADOPTION] == "する"
        if decisions.loc[pair, "product"] != product:
            raise ValueError("Selection product mismatch")
        values = np.stack(
            [
                pp.loc[pp.condition == condition]
                .sort_values("position")
                .frequency_hz.to_numpy(float)
                for condition in CONDITIONS
            ]
        )
        if values.shape != (2, len(labels)):
            raise ValueError("Invalid fixed interval shape")
        baselines = values[:, 0]
        baseline_available = bool(np.isfinite(baselines).all())
        paired_available = np.isfinite(values).all(axis=0)
        differences = values - baselines[:, None]
        for position, label in enumerate(labels, 1):
            paired = bool(paired_available[position - 1])
            for ci, condition in enumerate(CONDITIONS):
                source = pp.loc[(pp.condition == condition) & (pp.position == position)].iloc[0]
                change = float(differences[ci, position - 1])
                participant_rows.append(
                    {
                        "analysis_number": number,
                        "channel": ANALYSES[number][0],
                        "product": product,
                        "pair_id": pair,
                        "session_id": source.session_id,
                        "condition": condition,
                        "position": position,
                        "interval_label": label,
                        "saved_iaf_hz": float(values[ci, position - 1]),
                        "baseline_interval": labels[0],
                        "baseline_iaf_hz": float(baselines[ci]),
                        "iaf_change_hz": change,
                        "source_quality": source.quality,
                        "both_baselines_finite": baseline_available,
                        "both_interval_iaf_finite": paired,
                        "selected_participant": bool(selected),
                        "included_all_available": baseline_available and paired,
                        "included_selected_participants": baseline_available
                        and paired
                        and selected,
                    }
                )
            for cohort in COHORTS:
                cohort_member = cohort == "AllAvailable" or selected
                included = baseline_available and paired and cohort_member
                reasons = []
                if not cohort_member:
                    reasons.append("not_in_final_selected_cohort")
                if not baseline_available:
                    reasons.append("paired_baseline_missing")
                if not paired:
                    reasons.append("paired_interval_missing")
                inclusion_rows.append(
                    {
                        "analysis_number": number,
                        "channel": ANALYSES[number][0],
                        "product": product,
                        "cohort": cohort,
                        "pair_id": pair,
                        "position": position,
                        "interval_label": label,
                        "selected_participant": bool(selected),
                        "cohort_member": bool(cohort_member),
                        "both_baselines_finite": baseline_available,
                        "both_interval_iaf_finite": paired,
                        "included": bool(included),
                        "exclusion_reason": ";".join(reasons),
                        "final_selection_reason": decisions.loc[pair, "採否理由"],
                    }
                )
    participants = pd.DataFrame(participant_rows)
    inclusion = pd.DataFrame(inclusion_rows)
    group_rows = []
    for product in PRODUCTS:
        for cohort, inclusion_key in zip(
            COHORTS, ("included_all_available", "included_selected_participants"), strict=True
        ):
            for position, label in enumerate(labels, 1):
                included = participants.loc[
                    (participants["product"] == product)
                    & (participants.position == position)
                    & participants[inclusion_key]
                ]
                for condition in CONDITIONS:
                    values = included.loc[
                        included.condition == condition, "iaf_change_hz"
                    ].to_numpy(float)
                    n = len(values)
                    if not np.isfinite(values).all():
                        raise AssertionError("Nonfinite change entered group mean")
                    mean = float(np.mean(values)) if n else np.nan
                    sd = float(np.std(values, ddof=1)) if n >= 2 else np.nan
                    group_rows.append(
                        {
                            "analysis_number": number,
                            "channel": ANALYSES[number][0],
                            "product": product,
                            "cohort": cohort,
                            "condition": condition,
                            "position": position,
                            "interval_label": label,
                            "baseline_interval": labels[0],
                            "mean_iaf_change_hz": mean,
                            "sd_iaf_change_hz": sd,
                            "sem_iaf_change_hz": sd / np.sqrt(n) if n >= 2 else np.nan,
                            "n": n,
                        }
                    )
    groups = pd.DataFrame(group_rows)
    for _, group in groups.groupby(["product", "cohort", "position"]):
        if len(group) != 2 or group.n.nunique() != 1:
            raise AssertionError("Paired group counts are unequal")
    baseline = groups.loc[(groups.position == 1) & (groups.n > 0)]
    if not baseline.mean_iaf_change_hz.eq(0).all():
        raise AssertionError("Baseline changes must equal zero")
    return participants, groups, inclusion


def assert_output_path(path: Path, base: Path = BASE) -> None:
    """Reject symlink/path escapes, and any writes outside the four No roots."""
    resolved = path.resolve()
    allowed = [base / ANALYSES[n][2] for n in ANALYSES]
    if not any(resolved.is_relative_to(root.resolve()) for root in allowed):
        raise ValueError("Output escapes authorized No8–9 folders")
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError("Output root symlink escapes Phase4")


def write_table(path: Path, frame: pd.DataFrame) -> None:
    assert_output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial.csv")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig", float_format="%.17g")
    os.replace(temporary, path)
    saved = pd.read_csv(path, keep_default_na=False, dtype=str)
    if len(saved) != len(frame) or list(saved.columns) != list(frame.columns):
        raise AssertionError("Written table failed shape readback")


def figure_path(number: int, product: str, cohort: str) -> Path:
    return (
        BASE
        / ANALYSES[number][2]
        / product
        / "GrandAverage"
        / f"No{number}_{ANALYSES[number][0]}_IAFChange_{product}_{cohort}.png"
    )


def render_groups(
    groups: pd.DataFrame,
    number: int,
    products: tuple[str, ...] = PRODUCTS,
    cohorts: tuple[str, ...] = COHORTS,
) -> list[dict[str, Any]]:
    from phase4_iaf_grand_average_figures import plot_grand_average, shared_y_limit

    outputs = []
    for product in products:
        pp = groups.loc[groups["product"] == product]
        series = []
        arrays = {}
        for cohort in COHORTS:
            arrays[cohort] = {}
            for condition, prefix in zip(CONDITIONS, ("drops", "control"), strict=True):
                cc = pp.loc[(pp.cohort == cohort) & (pp.condition == condition)].sort_values(
                    "position"
                )
                mean, sem = (
                    cc[key].to_numpy(float) for key in ("mean_iaf_change_hz", "sem_iaf_change_hz")
                )
                arrays[cohort][f"{prefix}_mean_hz"] = mean
                arrays[cohort][f"{prefix}_sem_hz"] = sem
                series.append((mean, sem))
        limit = shared_y_limit(series)
        for cohort in cohorts:
            path = figure_path(number, product, cohort)
            assert_output_path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            metadata = plot_grand_average(
                output_path=path,
                analysis_number=number,
                product=product,
                cohort=cohort,
                y_limit_hz=limit,
                **arrays[cohort],
            )
            outputs.append({"path": str(path), "sha256": sha256_file(path), "render": metadata})
    return outputs


def _verify_saved_tables(root: Path, tables: tuple[pd.DataFrame, ...]) -> dict[str, str]:
    hashes = {}
    for name, expected in zip(TABLE_NAMES, tables, strict=True):
        path = root / "Sub/tables/GrandAverage" / name
        observed = pd.read_csv(
            path,
            dtype={
                "session_id": str,
                "pair_id": str,
                "interval_label": str,
                "baseline_interval": str,
            },
            keep_default_na=True,
        )
        # pandas maps blank reasons to NaN. Normalize only those text columns.
        for column in ("exclusion_reason",):
            if column in observed:
                observed[column] = observed[column].fillna("")
        pd.testing.assert_frame_equal(
            expected, observed, check_dtype=False, check_exact=False, rtol=1e-12, atol=1e-12
        )
        hashes[str(path)] = sha256_file(path)
    return hashes


def validate_scoped_tables(
    old_tables: tuple[pd.DataFrame, ...],
    new_tables: tuple[pd.DataFrame, ...],
    products: tuple[str, ...],
    cohorts: tuple[str, ...],
) -> None:
    """Reject any out-of-scope numerical change before overwriting current tables."""
    for index, (old, new) in enumerate(zip(old_tables, new_tables, strict=True)):
        if list(old.columns) != list(new.columns) or len(old) != len(new):
            raise ValueError("Scoped update requires matching complete table shapes")
        if index == 0:
            # Selection flags may change, but saved IAF, baselines and differences never do.
            flags = ["selected_participant", "included_selected_participants"]
            pd.testing.assert_frame_equal(
                old.drop(columns=flags),
                new.drop(columns=flags),
                check_dtype=False,
                check_exact=False,
                rtol=1e-12,
                atol=1e-12,
            )
            keep = ~new["product"].isin(products)
            if "SelectedParticipants" not in cohorts:
                keep[:] = True
        elif index == 1:
            keep = ~(new["product"].isin(products) & new.cohort.isin(cohorts))
        else:
            # Global adoption/reason metadata can change on both cohort rows, not inclusion.
            metadata = ["selected_participant", "final_selection_reason"]
            keep = ~(new["product"].isin(products) & new.cohort.isin(cohorts))
            pd.testing.assert_frame_equal(
                old.loc[keep].drop(columns=metadata),
                new.loc[keep].drop(columns=metadata),
                check_dtype=False,
                check_exact=False,
                rtol=1e-12,
                atol=1e-12,
            )
            keep = ~new["product"].isin(products)
        pd.testing.assert_frame_equal(
            old.loc[keep],
            new.loc[keep],
            check_dtype=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-12,
        )


def scoped_protection(
    analyses: list[int], products: tuple[str, ...], cohorts: tuple[str, ...]
) -> dict[str, str]:
    allowed = {figure_path(n, p, c) for n in analyses for p in products for c in cohorts} | {
        BASE / ANALYSES[n][2] / "Sub/tables/GrandAverage" / name
        for n in analyses
        for name in TABLE_NAMES
    }
    protected = {}
    for _, _, folder in ANALYSES.values():
        for path in (BASE / folder).rglob("*"):
            if path.is_file() and path not in allowed:
                protected[str(path)] = sha256_file(path)
    return protected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--analysis", type=int, choices=list(ANALYSES), nargs="+", default=list(ANALYSES)
    )
    parser.add_argument(
        "--production-batch", action="store_true", help="40-pair validation is always required"
    )
    parser.add_argument("--product", choices=PRODUCTS, nargs="+", default=list(PRODUCTS))
    parser.add_argument("--cohort", choices=COHORTS, nargs="+", default=list(COHORTS))
    modes = parser.add_mutually_exclusive_group(required=True)
    for flag in ("preflight-only", "all", "figures-only"):
        modes.add_argument(f"--{flag}", action="store_true")
    args = parser.parse_args(argv)
    if len(args.analysis) != len(set(args.analysis)):
        parser.error("Duplicate analysis numbers")
    if len(args.product) != len(set(args.product)) or len(args.cohort) != len(set(args.cohort)):
        parser.error("Duplicate product/cohort scope")
    products, cohorts = tuple(args.product), tuple(args.cohort)
    scoped = (
        set(args.analysis) != set(ANALYSES)
        or set(products) != set(PRODUCTS)
        or set(cohorts) != set(COHORTS)
    )
    frames, selection, fingerprints = preflight(BASE, DEFAULT_CACHE_ROOT, args.manifest)
    computed = {n: compute_tables(frames[n], selection, n) for n in args.analysis}
    if scoped:
        fingerprints.update(scoped_protection(args.analysis, products, cohorts))
        for number, tables in computed.items():
            previous = tuple(
                pd.read_csv(
                    BASE / ANALYSES[number][2] / "Sub/tables/GrandAverage" / name,
                    dtype={
                        "pair_id": str,
                        "session_id": str,
                        "interval_label": str,
                        "baseline_interval": str,
                    },
                )
                for name in TABLE_NAMES
            )
            previous[2]["exclusion_reason"] = previous[2].exclusion_reason.fillna("")
            validate_scoped_tables(previous, tables, products, cohorts)
    summary = {
        str(n): [
            {"product": product, "cohort": cohort, "n_min": int(g.n.min()), "n_max": int(g.n.max())}
            for (product, cohort), g in computed[n][1].groupby(["product", "cohort"])
        ]
        for n in args.analysis
    }
    if args.preflight_only:
        assert_hashes(fingerprints)
        print(json.dumps({"status": "preflight_passed", "writes": 0, "cohorts": summary}))
        return 0
    run_tag = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run = {
        "version": VERSION,
        "started_utc": datetime.now(UTC).isoformat(),
        "status": "running",
        "mode": "figures-only" if args.figures_only else "all",
        "analyses": args.analysis,
        "products": list(products),
        "cohorts": list(cohorts),
        "scoped_output": scoped,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "script_sha256": {
            p.name: sha256_file(p)
            for p in (
                Path(__file__),
                Path(__file__).with_name("phase4_iaf_grand_average_figures.py"),
            )
        },
        "protected_files_sha256": fingerprints,
        "cohort_counts": summary,
        "psd_recomputed": False,
        "iaf_reestimated": False,
        "additional_smoothing": False,
        "statistical_tests": False,
        "source_schema": SCHEMA,
        "selection_schema": SELECTION_SCHEMA,
        "active_analysis_channels": ACTIVE_SELECTION_ANALYSES,
        "figure_y_limits_hz": [-1.1, 1.1],
        "figure_y_ticks_hz": [-1.0, -0.5, 0.0, 0.5, 1.0],
        "source_calc_config_sha256": config_hash(),
        "mean": "equal participant arithmetic mean of paired baseline differences",
        "sem": "sample SD (ddof=1) / sqrt(n); NaN for n<2",
        "paired_missing": "either baseline missing: whole pair; later missing: that interval only",
        "cloud_verification": (
            "local OneDrive path/readback only; server synchronization unverified"
        ),
        "outputs": [],
    }
    logs = [
        BASE / ANALYSES[n][2] / "Sub/logs" / f"IAFGrandAverage_{run_tag}.json"
        for n in args.analysis
    ]
    try:
        for path in logs:
            assert_output_path(path)
            write_json(path, run)
        for number in args.analysis:
            root = BASE / ANALYSES[number][2]
            tables = computed[number]
            if not args.figures_only:
                for name, frame in zip(TABLE_NAMES, tables, strict=True):
                    write_table(root / "Sub/tables/GrandAverage" / name, frame)
            saved_hashes = _verify_saved_tables(root, tables)
            if args.figures_only:
                # Reuse saved summary, not a fresh group-estimation result, for drawing.
                groups = pd.read_csv(root / "Sub/tables/GrandAverage/GroupSummary.csv")
            else:
                groups = tables[1]
            run["outputs"].extend(
                {"path": path, "sha256": digest} for path, digest in saved_hashes.items()
            )
            run["outputs"].extend(render_groups(groups, number, products, cohorts))
        assert_hashes(fingerprints)
        assert_hashes({item["path"]: item["sha256"] for item in run["outputs"]})
        run.update(
            status="complete", completed_utc=datetime.now(UTC).isoformat(), protected_unchanged=True
        )
    except Exception as exc:
        run.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        for path in logs:
            if path.exists():
                write_json(path, run)
        raise
    for path in logs:
        write_json(path, run)
    print(
        json.dumps(
            {"status": run["status"], "outputs": len(run["outputs"]), "logs": list(map(str, logs))}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
