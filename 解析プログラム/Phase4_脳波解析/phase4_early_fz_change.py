#!/usr/bin/env python3
"""Shared, cache-only engine for Phase 4 No4/No5 early-Set Fz PSD Change."""

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
import Phase4_No1_sub_FmThetaChange as change_engine
from phase4_band_variant_config import configure_change_engine


@dataclass(frozen=True)
class EarlyBand:
    number: int
    stem: str
    parent_stem: str
    frequencies: tuple[float, ...]
    colors: tuple[str, str]
    quant_colors: tuple[str, str]


BANDS = {
    4: EarlyBand(
        4,
        "No4_FzThetaEarlyChange",
        "No1_FmTheta",
        (4.0, 5.0, 6.0, 7.0),
        ("#2679A8", "#3AA4B8"),
        ("#5A9FC3", "#70B7C3"),
    ),
    5: EarlyBand(
        5,
        "No5_FzDeltaEarlyChange",
        "No3_FrontalDelta",
        (1.0, 2.0, 3.0),
        ("#347C62", "#66A86B"),
        ("#60A184", "#87BC8B"),
    ),
}

WINDOWS = {"FullSet": 100.0, "FirstHalf": 50.0, "FirstQuarter": 25.0}
SCRIPT_VERSION = "phase4-no4-no5-fz-early-change-2026-11-08.1"


def configure(band: EarlyBand) -> None:
    """Reuse the checked No1/No3 change implementation without touching its files."""
    if band.number == 4:
        parent = theta_parent
    else:
        from Phase4_No3_FrontalDelta import engine as parent  # noqa: PLC0415

    configure_change_engine(
        change_engine,
        parent,
        analysis_stem=band.stem,
        focus_channel="Fz",
        script_version=SCRIPT_VERSION,
        include_topography=False,
    )
    ccube = ("CCube", "C Cube", band.colors[0], band.quant_colors[0])
    vrohto = ("VRohtoPremium", "V Rohto Premium", band.colors[1], band.quant_colors[1])
    parent.PRODUCTS = {
        "ccube": ccube,
        "c_cube": ccube,
        "cキューブ": ccube,
        "vrohtopremium": vrohto,
        "v_rohto_premium": vrohto,
        "vロート": vrohto,
        "vロートプレミアム": vrohto,
    }


def validate_cache_metadata(spec: Any, cache_root: Path, band: EarlyBand) -> None:
    """Verify that the existing cache belongs to this pair, condition and band."""
    parent = change_engine.no1
    for session_id in (spec.first_session_id, spec.second_session_id):
        path = parent.cache_path(cache_root, spec, session_id)
        parent.validate_cache(path)
        with h5py.File(path, "r") as handle:
            actual = {
                "participant_id": str(handle.attrs.get("participant_id")),
                "pair_id": str(handle.attrs.get("pair_id")),
                "product": str(handle.attrs.get("product")),
                "condition": str(handle.attrs.get("condition")),
            }
            expected = {
                "participant_id": session_id,
                "pair_id": spec.pair_id,
                "product": parent.normalize_product(spec.product)[0],
                "condition": "Eye Drop" if session_id == spec.drops_session_id else "Control",
            }
            if actual != expected:
                raise ValueError(f"{path}: cache identity/condition does not match manifest")
            frequencies = tuple(
                float(value) for value in json.loads(handle.attrs["included_frequencies_hz"])
            )
            if frequencies != band.frequencies:
                raise ValueError(
                    f"{path}: expected frequency bins {band.frequencies}, got {frequencies}"
                )
            if float(handle.attrs["sampling_frequency_hz"]) != 256.0:
                raise ValueError(f"{path}: sampling frequency mismatch")
            if (
                int(handle.attrs["window_samples"]) != 256
                or int(handle.attrs["step_samples"]) != 256
            ):
                raise ValueError(f"{path}: PSD window or step mismatch")
            if (
                str(handle.attrs["log3sd_scope"])
                != "session_id_x_channel_across_all_available_sets"
            ):
                raise ValueError(f"{path}: unexpected log3sd scope")
            if not str(handle.attrs.get("configuration_hash", "")):
                raise ValueError(f"{path}: missing configuration hash")


def preflight(
    specs: list[Any], cache_root: Path, band: EarlyBand
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Perform all ID/cache checks before writing any output."""
    change_engine.no1.validate_participant_specs(specs, production_batch=True)
    for spec in specs:
        validate_cache_metadata(spec, cache_root, band)
    items, summary = change_engine.preflight(specs, cache_root, True)
    if len(items) != 39 or summary["excluded_pairs"][0]["pair_id"] != "109-209":
        raise ValueError("Expected 39 pairs and only the Set-1-missing 109-209 pair excluded")
    by_product = pd.Series([item["product_dir"] for item in items]).value_counts().to_dict()
    if by_product != {"CCube": 20, "VRohtoPremium": 19}:
        raise ValueError(f"Unexpected analysable product counts: {by_product}")
    summary["products_after_set1_exclusion"] = by_product
    summary["frequency_bins_hz"] = band.frequencies
    return items, summary


def quantify_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Average unsmoothed 1-second change windows selected by real Set progress."""
    eye = item["eye_drop"]
    control = item["control"]
    fz_eye = eye.channel_names.index("Fz")
    fz_control = control.channel_names.index("Fz")
    common_sets = set(eye.source.sets) & set(control.source.sets)
    rows: list[dict[str, Any]] = []
    for set_number in range(1, 7):
        for window_name, end_progress in WINDOWS.items():
            row: dict[str, Any] = {
                "PairID": item["spec"].pair_id,
                "Product": item["product_dir"],
                "Set": set_number,
                "Window": window_name,
                "ProgressStart_pct": 0.0,
                "ProgressEnd_pct": end_progress,
                "PairedSetAvailable": set_number in common_sets,
            }
            for condition, session, channel in (
                ("EyeDrop", eye, fz_eye),
                ("Control", control, fz_control),
            ):
                if set_number not in common_sets:
                    row[f"{condition}_PSDChange_pct"] = np.nan
                    row[f"{condition}_TotalWindows"] = 0
                    row[f"{condition}_FiniteWindows"] = 0
                    continue
                source = session.source.sets[set_number]
                progress = np.asarray(source.set_progress_pct, dtype=float)
                selected = (progress >= 0.0) & (
                    (progress <= end_progress)
                    if window_name == "FullSet"
                    else (progress < end_progress)
                )
                values = change_engine.set_change_values(session, set_number, channel)
                finite = np.isfinite(values[selected])
                row[f"{condition}_TotalWindows"] = int(selected.sum())
                row[f"{condition}_FiniteWindows"] = int(finite.sum())
                row[f"{condition}_PSDChange_pct"] = (
                    float(values[selected][finite].mean()) if finite.any() else np.nan
                )
            rows.append(row)
    return rows


def quantification_table(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [row for item in items for row in quantify_item(item)]
    frame = pd.DataFrame(rows)
    set1_full = frame.loc[(frame["Set"] == 1) & (frame["Window"] == "FullSet")]
    for condition in ("EyeDrop", "Control"):
        if not np.allclose(set1_full[f"{condition}_PSDChange_pct"], 0.0, atol=1e-8):
            raise ValueError(f"Set 1 full-window {condition} PSD Change is not zero")
    return frame


def summary_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (product, window, set_number), group in frame.groupby(
        ["Product", "Window", "Set"], sort=True
    ):
        eye = group["EyeDrop_PSDChange_pct"].to_numpy(float)
        control = group["Control_PSDChange_pct"].to_numpy(float)
        paired = np.isfinite(eye) & np.isfinite(control)
        if not paired.any():
            raise ValueError(f"No paired values: {product} {window} Set{set_number}")
        rows.append(
            {
                "Product": product,
                "Window": window,
                "Set": set_number,
                "Paired_N": int(paired.sum()),
                "EyeDrop_Mean_PSDChange_pct": float(np.mean(eye[paired])),
                "Control_Mean_PSDChange_pct": float(np.mean(control[paired])),
                "EyeDrop_SD_PSDChange_pct": float(np.std(eye[paired], ddof=1)),
                "Control_SD_PSDChange_pct": float(np.std(control[paired], ddof=1)),
            }
        )
    return pd.DataFrame(rows)


def validate_fullset_reference(frame: pd.DataFrame, output_root: Path, band: EarlyBand) -> None:
    """The new full-Set means must reproduce the completed No1_sub/No3_sub values."""
    reference_stem = "No1_sub_FmThetaChange" if band.number == 4 else "No3_sub_FrontalDeltaChange"
    for product in ("CCube", "VRohtoPremium"):
        path = (
            output_root
            / "Phase4_脳波解析"
            / reference_stem
            / "Sub"
            / "tables"
            / "SetQuantification"
            / f"{reference_stem}_Quantification_Values_{product}.csv"
        )
        if not path.is_file():
            raise FileNotFoundError(f"Cannot validate completed full-Set values: {path}")
        reference = pd.read_csv(path)
        reference = reference.loc[reference["Set"].astype(str) != "All Sets"].copy()
        reference["Set"] = reference["Set"].astype(int)
        current = frame.loc[(frame["Product"] == product) & (frame["Window"] == "FullSet")]
        merged = current.merge(
            reference,
            on=["PairID", "Set"],
            how="outer",
            suffixes=("_new", "_reference"),
            indicator=True,
        )
        if not (merged["_merge"] == "both").all():
            raise ValueError(f"{product}: full-Set reference participant/Set mismatch")
        for condition in ("EyeDrop", "Control"):
            a = merged[f"{condition}_PSDChange_pct_new"].to_numpy(float)
            b = merged[f"{condition}_PSDChange_pct_reference"].to_numpy(float)
            if not np.allclose(a, b, rtol=1e-10, atol=1e-8, equal_nan=True):
                raise ValueError(f"{product}: full-Set values diverge from {reference_stem}")


def _draw_quantification_panel(
    axis: plt.Axes,
    frame: pd.DataFrame,
    product: str,
    set_number: int,
    layout: tuple[float, float, np.ndarray, float, float, float],
    *,
    show_ylabel: bool,
) -> None:
    _, product_label, _, eye_color = change_engine.no1.normalize_product(product)
    lower, upper, ticks, _, _, set_y = layout
    eye = frame["EyeDrop_PSDChange_pct"].to_numpy(float)
    control = frame["Control_PSDChange_pct"].to_numpy(float)
    paired = np.isfinite(eye) & np.isfinite(control)
    eye, control = eye[paired], control[paired]
    x = np.array([-0.32, 0.32])
    axis.bar(
        x,
        [float(eye.mean()), float(control.mean())],
        width=0.42,
        color=[eye_color, change_engine.no1.CONTROL_QUANTIFICATION_COLOR],
        alpha=0.82,
        edgecolor="#222222",
        linewidth=1.0,
        zorder=1,
    )
    jitter = np.random.default_rng(8100 + set_number).uniform(-0.055, 0.055, eye.size)
    for offset, eye_value, control_value in zip(jitter, eye, control, strict=True):
        axis.plot(
            x + offset,
            [eye_value, control_value],
            color="#777777",
            linewidth=1.2,
            alpha=0.34,
            zorder=2,
        )
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
        color=change_engine.no1.CONTROL_QUANTIFICATION_COLOR,
        alpha=0.68,
        edgecolor="white",
        linewidth=1.2,
        zorder=3,
    )
    axis.axhline(0.0, color="#9E9E9E", linewidth=1.2, zorder=0)
    axis.text(
        0, set_y, f"Set {set_number}", ha="center", va="center", fontsize=26, fontfamily="Arial"
    )
    axis.set_xlim(-0.9, 0.9)
    axis.set_ylim(lower, upper)
    axis.set_yticks(ticks)
    axis.set_xticks(x, ["Eye Drop", "Control"], fontsize=22)
    axis.text(
        x[0],
        -0.105,
        f"({product_label})",
        transform=axis.get_xaxis_transform(),
        ha="center",
        va="top",
        fontsize=18,
        fontfamily="Arial",
        clip_on=False,
    )
    axis.tick_params(axis="x", labelsize=22, width=1.5, length=6, pad=12)
    axis.tick_params(axis="y", labelsize=23, width=1.5, length=6, labelleft=True)
    if show_ylabel:
        axis.set_ylabel("PSD Change, %", fontsize=30)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def plot_quantification(frame: pd.DataFrame, product: str, window: str, path: Path) -> None:
    selected = frame.loc[(frame["Product"] == product) & (frame["Window"] == window)]
    values = selected[["EyeDrop_PSDChange_pct", "Control_PSDChange_pct"]].to_numpy(float)
    layout = change_engine._quantification_layout(values)  # noqa: SLF001
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axes = plt.subplots(1, 6, figsize=(34, 9), sharey=True)
    for set_number, axis in enumerate(axes, 1):
        _draw_quantification_panel(
            axis,
            selected.loc[selected["Set"] == set_number],
            product,
            set_number,
            layout,
            show_ylabel=set_number == 1,
        )
    titles = {
        "FullSet": "Full Set",
        "FirstHalf": "First 50% of Each Set",
        "FirstQuarter": "First 25% of Each Set",
    }
    figure.suptitle(titles[window], fontsize=26, fontfamily="Arial", y=0.995)
    figure.subplots_adjust(left=0.06, right=0.995, top=0.90, bottom=0.25, wspace=0.24)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_grand_average(
    frame: pd.DataFrame,
    product: str,
    path: Path,
    *,
    common_limit: float,
    common_ticks: np.ndarray,
) -> None:
    """Use the No1_sub design, keeping Set labels readable above SEM shading."""
    _, product_label, product_color, _ = change_engine.no1.normalize_product(product)
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axis = plt.subplots(figsize=(24, 8))
    x = frame["GlobalProgressPercent"].to_numpy(float)
    for prefix, color, label in (
        ("Control", change_engine.no1.CONTROL_COLOR, "Control"),
        ("EyeDrop", product_color, f"Eye Drop ({product_label})"),
    ):
        mean = frame[f"{prefix}_Mean_PSDChange_pct"].to_numpy(float)
        sem = frame[f"{prefix}_SEM_PSDChange_pct"].to_numpy(float)
        for set_number in range(1, 7):
            mask = frame["Set"].to_numpy(int) == set_number
            axis.fill_between(
                x[mask],
                mean[mask] - sem[mask],
                mean[mask] + sem[mask],
                color=color,
                alpha=0.18,
                linewidth=0,
            )
            axis.plot(
                x[mask],
                mean[mask],
                color=color,
                linewidth=3.0,
                label=label if set_number == 1 else None,
            )
    change_engine._configure_time_axis(axis, common_limit, common_ticks)  # noqa: SLF001
    for label in axis.texts:
        if label.get_text().startswith("Set "):
            label.set_bbox({"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 1})
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=2, frameon=False, fontsize=20)
    figure.subplots_adjust(left=0.08, right=0.99, top=0.78, bottom=0.20)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def output_paths(output_root: Path, band: EarlyBand, product: str) -> dict[str, Path]:
    root = output_root / "Phase4_脳波解析" / band.stem
    return {
        "root": root,
        "individual": root / product / "Individual",
        "grand": root / product / "GrandAverage",
        "quant": root / product / "SetQuantification",
        "baselines": root / "Sub" / "tables" / "Set1Baseline",
        "grand_values": root / "Sub" / "tables" / "GrandAverage",
        "quant_values": root / "Sub" / "tables" / "SetQuantification",
        "logs": root / "Sub" / "logs",
    }


def parse_args(band: EarlyBand) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Phase 4 No{band.number} Fz early-Set PSD Change")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--production-batch", action="store_true", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--all", action="store_true")
    return parser.parse_args()


def run(number: int) -> int:
    band = BANDS[number]
    configure(band)
    args = parse_args(band)
    parent = change_engine.no1
    cache_root = args.cache_root or parent.DEFAULT_CACHE_ROOT
    output_root = args.output_root or parent.DEFAULT_OUTPUT_ROOT
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    specs = parent.load_manifest(args.manifest)
    items, summary = preflight(specs, cache_root, band)
    logging.info("No%s preflight passed: %s pairs", number, len(items))
    if args.preflight_only:
        return 0

    # No output is touched until both the complete cache audit and the numerical
    # reproduction of the completed full-Set analysis pass.
    quant = quantification_table(items)
    validate_fullset_reference(quant, output_root, band)
    grouped = summary_table(quant)
    grand_frames = {
        product: change_engine.build_grand_average(items, product)[0]
        for product in ("CCube", "VRohtoPremium")
    }
    shared_limit, shared_ticks = change_engine.grand_average_axis(list(grand_frames.values()))
    root = output_paths(output_root, band, "CCube")["root"]
    baseline_rows = []
    for item in items:
        for condition, session in (("EyeDrop", item["eye_drop"]), ("Control", item["control"])):
            baseline_rows.append(
                {
                    "PairID": item["spec"].pair_id,
                    "SessionID": session.session_id,
                    "Product": item["product_dir"],
                    "Condition": condition,
                    "Fz_Set1Baseline_PSD_uV2_per_Hz": float(
                        session.baseline_by_channel[session.channel_names.index("Fz")]
                    ),
                }
            )
    paths0 = output_paths(output_root, band, "CCube")
    for name in ("baselines", "grand_values", "quant_values", "logs"):
        paths0[name].mkdir(parents=True, exist_ok=True)
    pd.DataFrame(baseline_rows).to_csv(
        paths0["baselines"] / f"{band.stem}_Fz_Set1Baseline.csv", index=False
    )
    quant.to_csv(paths0["quant_values"] / f"{band.stem}_PairSetWindowValues.csv", index=False)
    grouped.to_csv(paths0["quant_values"] / f"{band.stem}_GroupSetWindowSummary.csv", index=False)

    output_counts: dict[str, Any] = {}
    for product in ("CCube", "VRohtoPremium"):
        paths = output_paths(output_root, band, product)
        for name in ("individual", "grand", "quant"):
            paths[name].mkdir(parents=True, exist_ok=True)
        selected = [item for item in items if item["product_dir"] == product]
        for item in selected:
            destination = (
                paths["individual"] / f"ID{item['spec'].pair_id}_{band.stem}_Individual.png"
            )
            change_engine.plot_individual(item, destination)
        grand = grand_frames[product]
        grand.to_csv(
            paths["grand_values"] / f"{band.stem}_GrandAverage_Values_{product}.csv", index=False
        )
        plot_grand_average(
            grand,
            product,
            paths["grand"] / f"{band.stem}_GrandAverage_{product}.png",
            common_limit=shared_limit,
            common_ticks=shared_ticks,
        )
        for window in WINDOWS:
            plot_quantification(
                quant,
                product,
                window,
                paths["quant"] / f"{band.stem}_SetQuantification_{window}_{product}.png",
            )
        output_counts[product] = {
            "individual_png": len(selected),
            "grand_average_png": 1,
            "set_quantification_png": len(WINDOWS),
            "paired_n_by_set": grouped.loc[
                (grouped["Product"] == product) & (grouped["Window"] == "FullSet"),
                ["Set", "Paired_N"],
            ].to_dict("records"),
        }

    script_path = Path(__file__).resolve()
    digest = hashlib.sha256(script_path.read_bytes()).hexdigest()
    log = {
        "analysis": band.stem,
        "status": "completed",
        "completed_at": datetime.now().astimezone().isoformat(),
        "script_version": SCRIPT_VERSION,
        "shared_engine_sha256": digest,
        "manifest_source": "Notion participant-session table; anonymous IDs only",
        "input_cache_root": str(cache_root),
        "output_root": str(root),
        "preflight": summary,
        "method": (
            "Set-1-normalised Fz PSD Change; 60-s within-Set smoothing for time courses; "
            "unsmoothed FullSet/FirstHalf/FirstQuarter means"
        ),
        "inferential_statistics": "not computed; method and display pending",
        "additional_outlier_exclusion": "none",
        "fullset_reference": (
            "all pair/Set values exactly matched completed No1_sub or No3_sub CSV within tolerance"
        ),
        "output_counts": output_counts,
        "next_action": (
            "Review exploratory visual patterns before choosing any sensitivity analysis "
            "or statistics"
        ),
    }
    (paths0["logs"] / f"{band.stem}_RunSummary.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logging.info("No%s completed: %s", number, root)
    return 0
