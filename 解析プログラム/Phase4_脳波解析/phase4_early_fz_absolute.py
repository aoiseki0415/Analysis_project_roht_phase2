#!/usr/bin/env python3
"""Cache-only Phase 4 No6/No7: early-Set and between-Set absolute Fz PSD."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import h5py
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import Phase4_No1_FmTheta as theta_parent
import Phase4_No1_sub_FmThetaChange as layout_engine


@dataclass(frozen=True)
class Band:
    number: int
    stem: str
    parent_stem: str
    frequencies: tuple[float, ...]
    eye_colors: tuple[str, str]
    bar_colors: tuple[str, str]


BANDS = {
    6: Band(
        6,
        "No6_FzThetaEarlyAbsolutePSD",
        "No1_FmTheta",
        (4.0, 5.0, 6.0, 7.0),
        ("#A73F50", "#C75F69"),
        ("#BB6875", "#D6878D"),
    ),
    7: Band(
        7,
        "No7_FzDeltaEarlyAbsolutePSD",
        "No3_FrontalDelta",
        (1.0, 2.0, 3.0),
        ("#6E594F", "#96796A"),
        ("#90786B", "#AF9384"),
    ),
}
SET_WINDOWS = {"FirstHalf": 50.0, "FirstQuarter": 25.0}
BOUNDARY_WINDOWS = {"BoundaryHalf": 50.0, "BoundaryQuarter": 25.0}
VERSION = "phase4-no6-no7-absolute-2026-11-09.3"
CONTROL_BAR_COLOR = "#66547D"
SENSITIVITY_PAIR_IDS = ("101-201", "133-233")
SENSITIVITY_PRODUCT = "VRohtoPremium"
SENSITIVITY_SUFFIX = "ExcludePairs101-201_133-233"
SUPERSEDED_SENSITIVITY_SUFFIX = "ExcludePair101-201"


def parent_for(band: Band) -> Any:
    if band.number == 6:
        return theta_parent
    from Phase4_No3_FrontalDelta import engine  # noqa: PLC0415

    return engine


def _product_label(product: str) -> str:
    return "C Cube" if product == "CCube" else "V Rohto Premium"


def _product_color(band: Band, product: str, *, bar: bool) -> str:
    index = 0 if product == "CCube" else 1
    return (band.bar_colors if bar else band.eye_colors)[index]


def _load_item(spec: Any, cache_root: Path, band: Band, parent: Any) -> dict[str, Any]:
    by_id = {}
    for session_id in (spec.first_session_id, spec.second_session_id):
        path = parent.cache_path(cache_root, spec, session_id)
        parent.validate_cache(path)
        with h5py.File(path, "r") as handle:
            expected = {
                "participant_id": session_id,
                "pair_id": spec.pair_id,
                "product": parent.normalize_product(spec.product)[0],
                "condition": "Eye Drop" if session_id == spec.drops_session_id else "Control",
            }
            for key, value in expected.items():
                if str(handle.attrs.get(key)) != value:
                    raise ValueError(f"{path}: {key} does not match manifest")
            frequencies = tuple(
                float(x) for x in json.loads(handle.attrs["included_frequencies_hz"])
            )
            if frequencies != band.frequencies:
                raise ValueError(f"{path}: wrong frequency bins: {frequencies}")
            if float(handle.attrs["sampling_frequency_hz"]) != 256.0:
                raise ValueError(f"{path}: unexpected sampling frequency")
            if (
                int(handle.attrs["window_samples"]) != 256
                or int(handle.attrs["step_samples"]) != 256
            ):
                raise ValueError(f"{path}: unexpected Welch window/step")
            if (
                str(handle.attrs["log3sd_scope"])
                != "session_id_x_channel_across_all_available_sets"
            ):
                raise ValueError(f"{path}: unexpected outlier mask")
            if not str(handle.attrs.get("configuration_hash", "")):
                raise ValueError(f"{path}: missing configuration hash")
        by_id[session_id] = parent.load_session_cache(path)
        actual_sets = set(by_id[session_id].sets)
        expected_sets = set(range(1, 7)) - parent.EXPECTED_MISSING_SETS.get(session_id, set())
        if actual_sets != expected_sets:
            raise ValueError(f"{path}: unexpected Set availability {actual_sets}")
    return {
        "spec": spec,
        "product": parent.normalize_product(spec.product)[0],
        "eye": by_id[spec.drops_session_id],
        "control": by_id[spec.control_session_id],
    }


def preflight(specs: list[Any], cache_root: Path, band: Band, parent: Any) -> list[dict[str, Any]]:
    parent.validate_participant_specs(specs, production_batch=True)
    items = [_load_item(spec, cache_root, band, parent) for spec in specs]
    counts = pd.Series([item["product"] for item in items]).value_counts().to_dict()
    if counts != {"CCube": 20, "VRohtoPremium": 20}:
        raise ValueError(f"Expected 20 pairs per product, got {counts}")
    return items


def _values(session: Any, set_number: int) -> tuple[np.ndarray, np.ndarray]:
    source = session.sets[set_number]
    fz = session.channel_names.index("Fz")
    return np.asarray(source.set_progress_pct, float), np.asarray(
        source.psd_band_mean[:, fz], float
    )


def _selected_mean(values: np.ndarray, selected: np.ndarray) -> tuple[float, int, int]:
    selected_values = values[selected]
    finite = selected_values[np.isfinite(selected_values)]
    return (
        float(finite.mean()) if finite.size else np.nan,
        int(selected_values.size),
        int(finite.size),
    )


def quantify_set(item: dict[str, Any]) -> list[dict[str, Any]]:
    common = set(item["eye"].sets) & set(item["control"].sets)
    rows = []
    for set_number in range(1, 7):
        for window, end in {"FullSetQC": 100.0, **SET_WINDOWS}.items():
            row: dict[str, Any] = {
                "PairID": item["spec"].pair_id,
                "Product": item["product"],
                "Set": set_number,
                "Window": window,
                "ProgressStart_pct": 0.0,
                "ProgressEnd_pct": end,
                "PairedSetAvailable": set_number in common,
            }
            for condition, session in (("EyeDrop", item["eye"]), ("Control", item["control"])):
                mean, total, finite = np.nan, 0, 0
                if set_number in common:
                    progress, values = _values(session, set_number)
                    selected = (progress >= 0) & (
                        (progress <= end) if window == "FullSetQC" else (progress < end)
                    )
                    mean, total, finite = _selected_mean(values, selected)
                row[f"{condition}_PSD_uV2_per_Hz"] = mean
                row[f"{condition}_TotalWindows"] = total
                row[f"{condition}_FiniteWindows"] = finite
            rows.append(row)
    return rows


def quantify_boundary(item: dict[str, Any]) -> list[dict[str, Any]]:
    common = set(item["eye"].sets) & set(item["control"].sets)
    rows = []
    for to_set in range(2, 7):
        previous_set = to_set - 1
        available = {previous_set, to_set}.issubset(common)
        for window, width in BOUNDARY_WINDOWS.items():
            row: dict[str, Any] = {
                "PairID": item["spec"].pair_id,
                "Product": item["product"],
                "FromSet": previous_set,
                "ToSet": to_set,
                "Window": window,
                "PairedTransitionAvailable": available,
                "PreviousProgressStart_pct": 100.0 - width,
                "PreviousProgressEnd_pct": 100.0,
                "NextProgressStart_pct": 0.0,
                "NextProgressEnd_pct": width,
            }
            for condition, session in (("EyeDrop", item["eye"]), ("Control", item["control"])):
                for side, set_number in (("Previous", previous_set), ("Next", to_set)):
                    mean, total, finite = np.nan, 0, 0
                    if available:
                        progress, values = _values(session, set_number)
                        selected = (
                            (progress >= 100.0 - width) & (progress <= 100.0)
                            if side == "Previous"
                            else (progress >= 0) & (progress < width)
                        )
                        mean, total, finite = _selected_mean(values, selected)
                    row[f"{condition}_{side}Mean_PSD_uV2_per_Hz"] = mean
                    row[f"{condition}_{side}TotalWindows"] = total
                    row[f"{condition}_{side}FiniteWindows"] = finite
                preceding = row[f"{condition}_PreviousMean_PSD_uV2_per_Hz"]
                following = row[f"{condition}_NextMean_PSD_uV2_per_Hz"]
                row[f"{condition}_Transition_uV2_per_Hz"] = (
                    following - preceding
                    if np.isfinite(preceding) and np.isfinite(following)
                    else np.nan
                )
            eye = row["EyeDrop_Transition_uV2_per_Hz"]
            control = row["Control_Transition_uV2_per_Hz"]
            row["EyeDropMinusControl_Transition_uV2_per_Hz"] = (
                eye - control if np.isfinite(eye) and np.isfinite(control) else np.nan
            )
            rows.append(row)
    return rows


def summarize(frame: pd.DataFrame, *, boundary: bool) -> pd.DataFrame:
    keys = ["Product", "Window", "FromSet", "ToSet"] if boundary else ["Product", "Window", "Set"]
    suffix = "Transition_uV2_per_Hz" if boundary else "PSD_uV2_per_Hz"
    rows = []
    for key, group in frame.groupby(keys, sort=True):
        eye = group[f"EyeDrop_{suffix}"].to_numpy(float)
        control = group[f"Control_{suffix}"].to_numpy(float)
        paired = np.isfinite(eye) & np.isfinite(control)
        if not paired.any():
            raise ValueError(f"No paired values for {key}")
        difference = eye[paired] - control[paired]
        rows.append(
            dict(zip(keys, key, strict=True))
            | {
                "Paired_N": int(paired.sum()),
                "EyeDrop_Mean_uV2_per_Hz": float(eye[paired].mean()),
                "Control_Mean_uV2_per_Hz": float(control[paired].mean()),
                "EyeDrop_SD_uV2_per_Hz": float(eye[paired].std(ddof=1)),
                "Control_SD_uV2_per_Hz": float(control[paired].std(ddof=1)),
                "EyeDropMinusControl_Mean_uV2_per_Hz": float(difference.mean()),
            }
        )
    return pd.DataFrame(rows)


def validate_fullset_qc(frame: pd.DataFrame, output_root: Path, band: Band) -> None:
    qc = frame.loc[frame["Window"] == "FullSetQC"]
    for product in ("CCube", "VRohtoPremium"):
        path = (
            output_root
            / "Phase4_脳波解析"
            / band.parent_stem
            / "Sub"
            / "tables"
            / "SetQuantification"
            / f"{band.parent_stem}_SetQuantification_Values_{product}.csv"
        )
        reference = pd.read_csv(path, dtype={"PairID": str})
        reference = reference.loc[reference["Set"].astype(str) != "All Sets"].copy()
        reference["Set"] = reference["Set"].astype(int)
        current = qc.loc[qc["Product"] == product]
        merged = current.merge(
            reference, on=["PairID", "Set"], how="outer", suffixes=("_new", "_ref"), indicator=True
        )
        if len(merged) != 20 * 6 or not merged["_merge"].eq("both").all():
            raise ValueError(f"{product}: full-Set identity mismatch with {band.parent_stem}")
        for condition in ("EyeDrop", "Control"):
            column = f"{condition}_PSD_uV2_per_Hz"
            if not np.allclose(
                merged[f"{column}_new"],
                merged[f"{column}_ref"],
                rtol=1e-10,
                atol=1e-8,
                equal_nan=True,
            ):
                raise ValueError(f"{product}: full-Set PSD mismatch with {band.parent_stem}")


def _draw_panel(
    axis: plt.Axes,
    eye: np.ndarray,
    control: np.ndarray,
    *,
    product: str,
    band: Band,
    label: str,
    lower: float,
    upper: float,
    ticks: np.ndarray,
    seed: int,
    ylabel: str | None,
) -> None:
    paired = np.isfinite(eye) & np.isfinite(control)
    eye, control = eye[paired], control[paired]
    if not eye.size:
        raise ValueError(f"No paired data for {product} {label}")
    x = np.array([-0.32, 0.32])
    eye_color = _product_color(band, product, bar=True)
    axis.bar(
        x,
        [float(eye.mean()), float(control.mean())],
        width=0.42,
        color=[eye_color, CONTROL_BAR_COLOR],
        alpha=0.82,
        edgecolor="#222222",
        linewidth=1.0,
        zorder=1,
    )
    jitter = np.random.default_rng(seed).uniform(-0.055, 0.055, eye.size)
    for offset, e, c in zip(jitter, eye, control, strict=True):
        axis.plot(x + offset, [e, c], color="#777777", linewidth=1.2, alpha=0.34, zorder=2)
    axis.scatter(
        x[0] + jitter,
        eye,
        s=150,
        color=eye_color,
        alpha=0.68,
        edgecolor="white",
        linewidth=1.2,
        zorder=3,
    )
    axis.scatter(
        x[1] + jitter,
        control,
        s=150,
        color=CONTROL_BAR_COLOR,
        alpha=0.68,
        edgecolor="white",
        linewidth=1.2,
        zorder=3,
    )
    if lower < 0:
        axis.axhline(0, color="#9E9E9E", linewidth=1.2, zorder=0)
    axis.text(
        0,
        lower + 0.91 * (upper - lower),
        label,
        ha="center",
        va="center",
        fontsize=26,
        fontfamily="Arial",
    )
    axis.set_xlim(-0.9, 0.9)
    axis.set_ylim(lower, upper)
    axis.set_yticks(ticks)
    axis.set_xticks(x, ["Eye Drop", "Control"], fontsize=22)
    axis.text(
        x[0],
        -0.105,
        f"({_product_label(product)})",
        transform=axis.get_xaxis_transform(),
        ha="center",
        va="top",
        fontsize=18,
        fontfamily="Arial",
        clip_on=False,
    )
    axis.tick_params(axis="x", labelsize=22, width=1.5, length=6, pad=12)
    axis.tick_params(axis="y", labelsize=23, width=1.5, length=6, labelleft=True)
    if ylabel:
        axis.set_ylabel(ylabel, fontsize=30)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def plot_quantification(
    frame: pd.DataFrame,
    product: str,
    window: str,
    band: Band,
    path: Path,
    *,
    boundary: bool,
    parent: Any,
    title_suffix: str = "",
) -> None:
    selected = frame.loc[(frame["Product"] == product) & (frame["Window"] == window)]
    suffix = "Transition_uV2_per_Hz" if boundary else "PSD_uV2_per_Hz"
    values = selected[[f"EyeDrop_{suffix}", f"Control_{suffix}"]].to_numpy(float)
    if boundary:
        lower, upper, ticks, *_ = layout_engine._quantification_layout(values)  # noqa: SLF001
        panels, width = 5, 30
        ylabel = "Between-Set PSD Difference (µV²/Hz)"
    else:
        upper, ticks = parent._nice_upper(values, 0.70)  # noqa: SLF001
        lower, panels, width = 0.0, 6, 34
        ylabel = "PSD (µV²/Hz)"
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axes = plt.subplots(1, panels, figsize=(width, 9), sharey=True)
    for index, axis in enumerate(axes):
        number = index + (2 if boundary else 1)
        row = selected.loc[selected["ToSet" if boundary else "Set"] == number]
        label = f"Set {number - 1} → {number}" if boundary else f"Set {number}"
        _draw_panel(
            axis,
            row[f"EyeDrop_{suffix}"].to_numpy(float),
            row[f"Control_{suffix}"].to_numpy(float),
            product=product,
            band=band,
            label=label,
            lower=lower,
            upper=upper,
            ticks=ticks,
            seed=8600 + number,
            ylabel=ylabel if index == 0 else None,
        )
    fraction = BOUNDARY_WINDOWS[window] if boundary else SET_WINDOWS[window]
    title = (
        f"Previous Last {fraction:g}% to Next First {fraction:g}%"
        if boundary
        else f"First {fraction:g}% of Each Set"
    )
    figure.suptitle(title + title_suffix, fontsize=26, fontfamily="Arial", y=0.995)
    figure.subplots_adjust(
        left=0.07 if boundary else 0.06,
        right=0.995,
        top=0.90,
        bottom=0.25,
        wspace=0.25 if boundary else 0.24,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def output_root_for(root: Path, band: Band) -> Path:
    return root / "Phase4_脳波解析" / band.stem


def _validate_saved_pair_values(frame: pd.DataFrame, *, boundary: bool) -> None:
    """Reject incomplete or mismatched production tables before sensitivity output."""
    coordinate = ["FromSet", "ToSet"] if boundary else ["Set"]
    windows = BOUNDARY_WINDOWS if boundary else {"FullSetQC": 100.0, **SET_WINDOWS}
    suffix = "Transition_uV2_per_Hz" if boundary else "PSD_uV2_per_Hz"
    required = {
        "PairID",
        "Product",
        "Window",
        *coordinate,
        f"EyeDrop_{suffix}",
        f"Control_{suffix}",
    }
    if not required.issubset(frame.columns):
        raise ValueError(f"Saved pair table lacks columns: {sorted(required - set(frame.columns))}")
    identifiers = ["PairID", "Product", "Window", *coordinate]
    if frame[identifiers].isna().any(axis=None):
        raise ValueError("Saved pair table has a missing identifier or coordinate")
    if set(frame["Window"]) != set(windows):
        raise ValueError("Saved pair table has unexpected window names")
    if frame.duplicated(["PairID", "Product", "Window", *coordinate]).any():
        raise ValueError("Saved pair table contains duplicate pair/window coordinates")
    expected_coordinates = (
        {(start, start + 1) for start in range(1, 6)}
        if boundary
        else {(number,) for number in range(1, 7)}
    )
    expected_per_pair = len(windows) * len(expected_coordinates)
    for product in ("CCube", SENSITIVITY_PRODUCT):
        product_rows = frame.loc[frame["Product"] == product]
        if product_rows["PairID"].nunique() != 20 or len(product_rows) != 20 * expected_per_pair:
            raise ValueError(f"{product}: expected 20 complete saved pairs")
        for _, rows in product_rows.groupby("PairID"):
            observed = {
                (row.Window, *(getattr(row, key) for key in coordinate))
                for row in rows.itertuples(index=False)
            }
            expected = {(window, *point) for window in windows for point in expected_coordinates}
            if observed != expected:
                raise ValueError(f"{product}: incomplete Set/window coordinates")
    if len(frame) != 40 * expected_per_pair:
        raise ValueError("Saved pair table contains an unexpected product or row")
    for pair_id in SENSITIVITY_PAIR_IDS:
        target = frame.loc[frame["PairID"] == pair_id]
        if len(target) != expected_per_pair or set(target["Product"]) != {SENSITIVITY_PRODUCT}:
            raise ValueError(f"Sensitivity pair {pair_id} is absent or assigned to another product")


def _validate_saved_group_summary(
    pair_values: pd.DataFrame, saved_path: Path, *, boundary: bool
) -> None:
    """Ensure the pair-value source still reproduces the retained main result."""
    expected = summarize(pair_values, boundary=boundary)
    saved = pd.read_csv(saved_path)
    keys = ["Product", "Window", "FromSet", "ToSet"] if boundary else ["Product", "Window", "Set"]
    if set(saved.columns) != set(expected.columns) or len(saved) != len(expected):
        raise ValueError(f"{saved_path}: main group summary has drifted")
    merged = expected.merge(
        saved, on=keys, how="outer", suffixes=("_calculated", "_saved"), indicator=True
    )
    if len(merged) != len(expected) or not merged["_merge"].eq("both").all():
        raise ValueError(f"{saved_path}: main group coordinates have drifted")
    for column in expected.columns.difference(keys):
        if not np.allclose(
            merged[f"{column}_calculated"],
            merged[f"{column}_saved"],
            rtol=1e-10,
            atol=1e-8,
            equal_nan=True,
        ):
            raise ValueError(f"{saved_path}: main group values have drifted in {column}")


def run_excluded_pair_sensitivity(root: Path, band: Band, parent: Any) -> int:
    """Replace No7 V sensitivity from saved pair values; leave main files intact."""
    if band.number != 7:
        raise ValueError("Two-pair sensitivity is defined for No7 only")
    table_set = root / "Sub" / "tables" / "SetQuantification"
    table_boundary = root / "Sub" / "tables" / "BetweenSetQuantification"
    source_specs = [
        (table_set, "PairSetWindowValues", "GroupSetWindowSummary", False),
        (table_boundary, "PairSetTransitionValues", "GroupSetTransitionSummary", True),
    ]
    validated = []
    for folder, pair_stem, group_stem, boundary in source_specs:
        pair_path = folder / f"{band.stem}_{pair_stem}.csv"
        group_path = folder / f"{band.stem}_{group_stem}.csv"
        frame = pd.read_csv(pair_path, dtype={"PairID": str})
        _validate_saved_pair_values(frame, boundary=boundary)
        _validate_saved_group_summary(frame, group_path, boundary=boundary)
        v_rows = frame.loc[frame["Product"] == SENSITIVITY_PRODUCT]
        removed = v_rows.loc[v_rows["PairID"].isin(SENSITIVITY_PAIR_IDS)]
        filtered = v_rows.loc[~v_rows["PairID"].isin(SENSITIVITY_PAIR_IDS)].copy()
        if filtered["PairID"].nunique() != 18:
            raise ValueError("Sensitivity selection did not retain 18 V Rohto pairs")
        summary = summarize(filtered, boundary=boundary)
        original_v = summarize(v_rows, boundary=boundary)
        suffix = "Transition_uV2_per_Hz" if boundary else "PSD_uV2_per_Hz"
        coordinate = ["FromSet", "ToSet"] if boundary else ["Set"]
        removed_paired = removed.assign(
            PairedFinite=np.isfinite(removed[f"EyeDrop_{suffix}"].to_numpy(float))
            & np.isfinite(removed[f"Control_{suffix}"].to_numpy(float))
        )
        expected_reduction = removed_paired.groupby(["Window", *coordinate], sort=True)[
            "PairedFinite"
        ].sum()
        actual_reduction = original_v["Paired_N"].to_numpy() - summary["Paired_N"].to_numpy()
        if not np.array_equal(actual_reduction, expected_reduction.to_numpy()):
            raise ValueError("Paired N reduction does not match the two removed pairs")
        validated.append((folder, group_stem, boundary, pair_path, filtered, summary, original_v))
    outputs = []
    paired_counts = {}
    for folder, group_stem, boundary, _pair_path, filtered, summary, original_v in validated:
        csv_path = (
            folder / f"{band.stem}_{group_stem}_{SENSITIVITY_SUFFIX}_{SENSITIVITY_PRODUCT}.csv"
        )
        summary.to_csv(csv_path, index=False)
        outputs.append(str(csv_path))
        paired_counts["boundary" if boundary else "set"] = [
            dict(
                zip(
                    (["Window", "FromSet", "ToSet"] if boundary else ["Window", "Set"]),
                    (row.Window, row.FromSet, row.ToSet) if boundary else (row.Window, row.Set),
                    strict=True,
                )
            )
            | {"before": int(before), "after": int(row.Paired_N)}
            for row, before in zip(
                summary.itertuples(index=False), original_v["Paired_N"], strict=True
            )
        ]
        windows = BOUNDARY_WINDOWS if boundary else SET_WINDOWS
        kind = "BetweenSetQuantification" if boundary else "SetQuantification"
        for window in windows:
            png_path = (
                root
                / SENSITIVITY_PRODUCT
                / kind
                / f"{band.stem}_{kind}_{window}_{SENSITIVITY_PRODUCT}_{SENSITIVITY_SUFFIX}.png"
            )
            plot_quantification(
                filtered,
                SENSITIVITY_PRODUCT,
                window,
                band,
                png_path,
                boundary=boundary,
                parent=parent,
                title_suffix=" | Excluding Pairs 101-201 and 133-233",
            )
            outputs.append(str(png_path))
    log_path = root / "Sub" / "logs" / f"{band.stem}_{SENSITIVITY_SUFFIX}_RunSummary.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = {
        "analysis": band.stem,
        "status": "completed",
        "completed_at": datetime.now().astimezone().isoformat(),
        "script_version": VERSION,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "No7 V Rohto Premium post-hoc sensitivity only",
        "method": (
            "Original saved pair values; remove pairs 101-201 and 133-233 from both paired "
            "conditions before group summary and drawing"
        ),
        "excluded_pair_ids": list(SENSITIVITY_PAIR_IDS),
        "source_pair_csv_sha256": {
            str(pair_path): hashlib.sha256(pair_path.read_bytes()).hexdigest()
            for _, _, _, pair_path, _, _, _ in validated
        },
        "pair_count_before": 20,
        "pair_count_after": 18,
        "paired_n": paired_counts,
        "outputs": outputs,
        "main_results_modified": False,
        "inferential_statistics": "not computed; exploratory",
        "interpretation_caveat": (
            "Post-hoc sensitivity, not a global participant exclusion or causal evidence"
        ),
    }
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    superseded_paths = [
        root
        / "Sub"
        / "tables"
        / folder_name
        / f"{band.stem}_{group_stem}_{SUPERSEDED_SENSITIVITY_SUFFIX}_{SENSITIVITY_PRODUCT}.csv"
        for folder_name, group_stem in (
            ("SetQuantification", "GroupSetWindowSummary"),
            ("BetweenSetQuantification", "GroupSetTransitionSummary"),
        )
    ]
    superseded_paths.extend(
        root
        / SENSITIVITY_PRODUCT
        / kind
        / f"{band.stem}_{kind}_{window}_{SENSITIVITY_PRODUCT}_{SUPERSEDED_SENSITIVITY_SUFFIX}.png"
        for kind, windows in (
            ("SetQuantification", SET_WINDOWS),
            ("BetweenSetQuantification", BOUNDARY_WINDOWS),
        )
        for window in windows
    )
    superseded_paths.append(
        root / "Sub" / "logs" / f"{band.stem}_{SUPERSEDED_SENSITIVITY_SUFFIX}_RunSummary.json"
    )
    if not all(Path(path).is_file() and Path(path).stat().st_size > 0 for path in outputs):
        raise ValueError("New sensitivity outputs were not all saved; superseded files retained")
    for path in superseded_paths:
        path.unlink(missing_ok=True)
    logging.info("No7 V sensitivity completed: %s", root)
    return 0


def run(number: int) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    band = BANDS[number]
    parent = parent_for(band)
    parser = argparse.ArgumentParser(
        description=f"Phase 4 No{number}: Fz absolute PSD early-Set analysis"
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--production-batch", action="store_true", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--all", action="store_true")
    mode.add_argument(
        "--excluded-pairs-sensitivity-only",
        "--excluded-pair-sensitivity-only",
        dest="excluded_pair_sensitivity_only",
        action="store_true",
    )
    args = parser.parse_args()
    if args.excluded_pair_sensitivity_only:
        if args.manifest is not None:
            parser.error("--manifest is not used for saved-table sensitivity analysis")
        return run_excluded_pair_sensitivity(
            output_root_for(parent.DEFAULT_OUTPUT_ROOT, band), band, parent
        )
    if args.manifest is None:
        parser.error("--manifest is required for preflight and full analysis")
    specs = parent.load_manifest(args.manifest)
    items = preflight(specs, parent.DEFAULT_CACHE_ROOT, band, parent)
    logging.info("No%s cache/manifest preflight passed for %s pairs", number, len(items))
    if args.preflight_only:
        return 0

    set_frame = pd.DataFrame(row for item in items for row in quantify_set(item))
    boundary_frame = pd.DataFrame(row for item in items for row in quantify_boundary(item))
    validate_fullset_qc(set_frame, parent.DEFAULT_OUTPUT_ROOT, band)
    set_group = summarize(set_frame, boundary=False)
    boundary_group = summarize(boundary_frame, boundary=True)
    root = output_root_for(parent.DEFAULT_OUTPUT_ROOT, band)
    table_set = root / "Sub" / "tables" / "SetQuantification"
    table_boundary = root / "Sub" / "tables" / "BetweenSetQuantification"
    logs = root / "Sub" / "logs"
    for folder in (table_set, table_boundary, logs):
        folder.mkdir(parents=True, exist_ok=True)
    set_frame.to_csv(table_set / f"{band.stem}_PairSetWindowValues.csv", index=False)
    set_group.to_csv(table_set / f"{band.stem}_GroupSetWindowSummary.csv", index=False)
    boundary_frame.to_csv(table_boundary / f"{band.stem}_PairSetTransitionValues.csv", index=False)
    boundary_group.to_csv(
        table_boundary / f"{band.stem}_GroupSetTransitionSummary.csv", index=False
    )
    for product in ("CCube", "VRohtoPremium"):
        for window in SET_WINDOWS:
            plot_quantification(
                set_frame,
                product,
                window,
                band,
                root
                / product
                / "SetQuantification"
                / f"{band.stem}_SetQuantification_{window}_{product}.png",
                boundary=False,
                parent=parent,
            )
        for window in BOUNDARY_WINDOWS:
            plot_quantification(
                boundary_frame,
                product,
                window,
                band,
                root
                / product
                / "BetweenSetQuantification"
                / f"{band.stem}_BetweenSetQuantification_{window}_{product}.png",
                boundary=True,
                parent=parent,
            )
    log = {
        "analysis": band.stem,
        "status": "completed",
        "completed_at": datetime.now().astimezone().isoformat(),
        "script_version": VERSION,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "input_cache_root": str(parent.DEFAULT_CACHE_ROOT),
        "output_root": str(root),
        "manifest_source": "Notion participant/session table, cross-checked against cache metadata",
        "requested_pairs": len(specs),
        "analysable_pairs": len(items),
        "pairs_by_product": {"CCube": 20, "VRohtoPremium": 20},
        "additional_participant_exclusions": "none",
        "existing_masks": (
            "Phase 1 interval overlap >=1% and session-by-channel pooled log10 PSD upper 3SD"
        ),
        "method": (
            "Unsmoothed, post-mask absolute Fz PSD; Set first 50%/25% "
            "and next first minus previous last 50%/25%"
        ),
        "fullset_reference": (
            f"All 40 pairs and available Sets match completed {band.parent_stem} full-Set values"
        ),
        "missing_set_policy": (
            "Known missing Set and adjacent transitions excluded in both paired "
            "conditions; no imputation"
        ),
        "set_paired_n": set_group[["Product", "Window", "Set", "Paired_N"]].to_dict("records"),
        "boundary_paired_n": boundary_group[
            ["Product", "Window", "FromSet", "ToSet", "Paired_N"]
        ].to_dict("records"),
        "figure_counts": {"CCube": 4, "VRohtoPremium": 4},
        "inferential_statistics": "not computed; exploratory",
        "interpretation_caveat": (
            "Set boundary is not verified eye-drop timing; absolute PSD may retain "
            "between-person variation and residual artifacts"
        ),
        "next_action": (
            "Review figures before considering any participant-level sensitivity analysis"
        ),
    }
    (logs / f"{band.stem}_RunSummary.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logging.info("No%s completed: %s", number, root)
    return 0
