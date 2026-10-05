#!/usr/bin/env python3
"""Phase 5 No1: correlate DEQS with the paired RT eye-drop effect."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd
from scipy import stats

SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PHASE2_SCRIPT = (
    REPOSITORY_ROOT
    / "解析プログラム"
    / "Phase2_行動データ解析"
    / "Phase2_No1_ReactionTime.py"
)
PRODUCTS = {
    "CCube": ("C Cube", "#C84A4A"),
    "VRohtoPremium": ("V Rohto Premium", "#E58A2B"),
}


def _load_phase2_module():
    spec = importlib.util.spec_from_file_location("phase2_no1_runtime", PHASE2_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import Phase 2 implementation: {PHASE2_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PHASE2 = _load_phase2_module()
DEFAULT_OUTPUT_ROOT = PHASE2.DEFAULT_OUTPUT_ROOT
DEFAULT_RAW_ROOT = PHASE2.DEFAULT_RAW_ROOT


def _canonical_product(value: str) -> str:
    return PHASE2.normalize_product(str(value))[0]


def load_manifest(path: Path) -> list:
    specs = PHASE2.load_manifest(path)
    if len(specs) != 40:
        raise ValueError(f"Expected 40 participants after excluding ID130, found {len(specs)}")
    pair_ids = [item.pair_id for item in specs]
    if len(set(pair_ids)) != len(pair_ids):
        raise ValueError("Manifest contains duplicate participant pairs")
    if any("130" in {item.first_session_id, item.second_session_id} for item in specs):
        raise ValueError("ID130/230 must not be included")
    counts = pd.Series([_canonical_product(item.product) for item in specs]).value_counts()
    if counts.to_dict() != {"VRohtoPremium": 20, "CCube": 20}:
        raise ValueError(f"Expected 20 participants per product, found {counts.to_dict()}")
    return specs


def load_deqs_scores(path: Path, specs: list) -> pd.DataFrame:
    source = pd.read_csv(path)
    aliases = {
        "ParticipantID": "Participant_ID",
        "DegreeScoreSum": "Degree_score_sum",
        "ValidItemCount": "Valid_item_count",
        "DEQS_Total_Score": "DEQS_score_source",
        "EyeDropGroup": "Product_source",
    }
    source = source.rename(columns=aliases)
    required = {"Participant_ID", "Degree_score_sum", "Valid_item_count"}
    missing = sorted(required - set(source.columns))
    if missing:
        raise ValueError(f"DEQS score file is missing columns: {missing}")
    source["Participant_ID"] = source["Participant_ID"].astype(str)
    source["Degree_score_sum"] = pd.to_numeric(source["Degree_score_sum"], errors="raise")
    source["Valid_item_count"] = pd.to_numeric(source["Valid_item_count"], errors="raise")
    if (source["Valid_item_count"] < 10).any():
        bad = source.loc[source["Valid_item_count"] < 10, "Participant_ID"].tolist()
        raise ValueError(f"DEQS valid response count is below 10: {bad}")
    source["DEQS_score"] = (
        source["Degree_score_sum"] / source["Valid_item_count"] * 25.0
    )
    if "DEQS_score_source" in source:
        supplied = pd.to_numeric(source["DEQS_score_source"], errors="raise")
        if not np.allclose(supplied, source["DEQS_score"], atol=0.01, rtol=0.0):
            raise ValueError("Supplied DEQS score differs from DegreeScoreSum/ValidItemCount*25")

    manifest_rows = []
    for item in specs:
        manifest_rows.append(
            {
                "Participant_ID": item.first_session_id,
                "Pair_ID": item.pair_id,
                "First_session_ID": item.first_session_id,
                "Second_session_ID": item.second_session_id,
                "EyeDrop_session_ID": item.drops_session_id,
                "Control_session_ID": item.control_session_id,
                "Product": _canonical_product(item.product),
            }
        )
    manifest = pd.DataFrame(manifest_rows)
    merged = manifest.merge(source, on="Participant_ID", how="left", validate="one_to_one")
    if merged["DEQS_score"].isna().any():
        missing_ids = merged.loc[merged["DEQS_score"].isna(), "Participant_ID"].tolist()
        raise ValueError(f"Missing DEQS scores for IDs: {missing_ids}")
    if len(source) != len(merged):
        extras = sorted(set(source["Participant_ID"]) - set(manifest["Participant_ID"]))
        raise ValueError(f"DEQS score file has unexpected IDs: {extras}")
    return merged[
        [
            "Product",
            "Pair_ID",
            "Participant_ID",
            "First_session_ID",
            "Second_session_ID",
            "EyeDrop_session_ID",
            "Control_session_ID",
            "Degree_score_sum",
            "Valid_item_count",
            "DEQS_score",
        ]
    ].sort_values(["Product", "Pair_ID"]).reset_index(drop=True)


def recompute_phase2_set_means(specs: list, raw_root: Path) -> pd.DataFrame:
    results = []
    for item in specs:
        product = _canonical_product(item.product)
        drops = PHASE2.process_session(raw_root, item.drops_session_id, "目薬あり", product)
        control = PHASE2.process_session(raw_root, item.control_session_id, "コントロール", product)
        results.append({"participant": item, "drops": drops, "control": control})
    tables = []
    for product in PRODUCTS:
        values, _ = PHASE2.build_set_mean_quantification(
            results, product, trial_start=1, trial_end=320, variant="AllTrials"
        )
        tables.append(values)
    return pd.concat(tables, ignore_index=True)


def load_phase2_saved_values(output_root: Path) -> pd.DataFrame:
    directory = (
        output_root
        / "Phase2_行動データ解析"
        / "No1_ReactionTime"
        / "Sub"
        / "tables"
        / "SetMeanQuantification"
    )
    tables = []
    for product in PRODUCTS:
        path = directory / f"No1_RT_SetMeanQuantification_{product}_AllTrials_ParticipantValues.csv"
        if not path.is_file():
            raise FileNotFoundError(f"Phase 2 participant-values file not found: {path}")
        tables.append(pd.read_csv(path, dtype={"Pair_ID": str}))
    return pd.concat(tables, ignore_index=True)


def compare_phase2_values(recomputed: pd.DataFrame, saved: pd.DataFrame) -> pd.DataFrame:
    keys = ["Product", "Pair_ID", "Set"]
    value_columns = [
        "EyeDrop_set_mean_RT_ms",
        "Control_set_mean_RT_ms",
        "EyeDrop_valid_trial_count",
        "Control_valid_trial_count",
    ]
    left = recomputed[keys + value_columns].copy()
    right = saved[keys + value_columns].copy()
    merged = left.merge(right, on=keys, suffixes=("_recomputed", "_phase2"), validate="one_to_one")
    if len(merged) != len(left) or len(merged) != len(right):
        raise ValueError("Phase 2 consistency comparison has missing or extra key rows")
    all_match = np.ones(len(merged), dtype=bool)
    for column in value_columns:
        a = pd.to_numeric(merged[f"{column}_recomputed"], errors="coerce").to_numpy(float)
        b = pd.to_numeric(merged[f"{column}_phase2"], errors="coerce").to_numpy(float)
        match = np.isclose(a, b, atol=1e-9, rtol=0.0, equal_nan=True)
        merged[f"{column}_difference"] = a - b
        merged[f"{column}_match"] = match
        all_match &= match
    merged["All_values_match"] = all_match
    merged["Used_for_Phase5_EyeDropEffect"] = merged["Set"].isin([1, 6])
    if not all_match.all():
        failed = merged.loc[~merged["All_values_match"], keys].to_dict("records")
        raise ValueError(f"Phase 5 RT values do not reproduce Phase 2: {failed[:10]}")
    return merged.sort_values(keys).reset_index(drop=True)


def build_analysis_dataset(deqs: pd.DataFrame, values: pd.DataFrame) -> pd.DataFrame:
    selected = values.loc[values["Set"].isin([1, 6])].copy()
    wide = selected.pivot(
        index=["Product", "Pair_ID"],
        columns="Set",
        values=[
            "EyeDrop_set_mean_RT_ms",
            "Control_set_mean_RT_ms",
            "EyeDrop_valid_trial_count",
            "Control_valid_trial_count",
        ],
    )
    wide.columns = [f"{name}_Set{set_number}" for name, set_number in wide.columns]
    wide = wide.reset_index()
    data = deqs.merge(wide, on=["Product", "Pair_ID"], how="left", validate="one_to_one")
    data["EyeDrop_Set6_to_Set1_ratio"] = (
        data["EyeDrop_set_mean_RT_ms_Set6"] / data["EyeDrop_set_mean_RT_ms_Set1"]
    )
    data["Control_Set6_to_Set1_ratio"] = (
        data["Control_set_mean_RT_ms_Set6"] / data["Control_set_mean_RT_ms_Set1"]
    )
    data["Eye_Drop_Effect_pp"] = (
        data["Control_Set6_to_Set1_ratio"] - data["EyeDrop_Set6_to_Set1_ratio"]
    ) * 100.0
    required = [
        "EyeDrop_set_mean_RT_ms_Set1",
        "EyeDrop_set_mean_RT_ms_Set6",
        "Control_set_mean_RT_ms_Set1",
        "Control_set_mean_RT_ms_Set6",
    ]
    data["Included_in_correlation"] = np.isfinite(data[required]).all(axis=1)
    data["Exclusion_reason"] = ""
    for index, row in data.loc[~data["Included_in_correlation"]].iterrows():
        missing = [column.replace("_set_mean_RT_ms", "") for column in required if not np.isfinite(row[column])]
        data.at[index, "Exclusion_reason"] = "Required Phase 2 mean RT missing: " + ", ".join(missing)
    return data.sort_values(["Product", "Pair_ID"]).reset_index(drop=True)


def correlation_statistics(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for product in PRODUCTS:
        subset = data.loc[
            (data["Product"] == product) & data["Included_in_correlation"]
        ]
        x = subset["DEQS_score"].to_numpy(float)
        y = subset["Eye_Drop_Effect_pp"].to_numpy(float)
        result = stats.pearsonr(x, y)
        ci = result.confidence_interval(confidence_level=0.95)
        slope, intercept, _, _, _ = stats.linregress(x, y)
        rows.append(
            {
                "Product": product,
                "N": len(subset),
                "Pearson_r": float(result.statistic),
                "Raw_two_sided_p": float(result.pvalue),
                "Pearson_r_CI95_lower": float(ci.low),
                "Pearson_r_CI95_upper": float(ci.high),
                "OLS_slope_pp_per_DEQS_point": float(slope),
                "OLS_intercept_pp": float(intercept),
                "Multiple_comparison_correction": "なし（探索的解析）",
            }
        )
    return pd.DataFrame(rows)


def _regression_mean_ci(x: np.ndarray, y: np.ndarray, x_grid: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    slope, intercept, _, _, _ = stats.linregress(x, y)
    fitted = intercept + slope * x_grid
    predicted = intercept + slope * x
    dof = len(x) - 2
    residual_se = math.sqrt(float(np.sum((y - predicted) ** 2)) / dof)
    x_mean = float(np.mean(x))
    sxx = float(np.sum((x - x_mean) ** 2))
    critical = float(stats.t.ppf(0.975, dof))
    se_mean = residual_se * np.sqrt(1.0 / len(x) + (x_grid - x_mean) ** 2 / sxx)
    return fitted, fitted - critical * se_mean, fitted + critical * se_mean


def plot_correlations(data: pd.DataFrame, statistics: pd.DataFrame, output_root: Path) -> list[Path]:
    included = data.loc[data["Included_in_correlation"]]
    max_abs = float(np.nanmax(np.abs(included["Eye_Drop_Effect_pp"].to_numpy(float))))
    y_limit = max(10.0, math.ceil((max_abs * 1.10) / 5.0) * 5.0)
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    paths = []
    for product, (label, color) in PRODUCTS.items():
        subset = included.loc[included["Product"] == product]
        x = subset["DEQS_score"].to_numpy(float)
        y = subset["Eye_Drop_Effect_pp"].to_numpy(float)
        stat = statistics.loc[statistics["Product"] == product].iloc[0]
        x_grid = np.linspace(0.0, 100.0, 300)
        fitted, lower, upper = _regression_mean_ci(x, y, x_grid)
        figure, axis = plt.subplots(figsize=(8, 7))
        axis.fill_between(x_grid, lower, upper, color=color, alpha=0.18, linewidth=0)
        axis.plot(x_grid, fitted, color=color, linewidth=2.5)
        axis.scatter(x, y, s=90, color=color, edgecolor="white", linewidth=1.2, zorder=3)
        axis.axhline(0.0, color="#B0B0B0", linewidth=1.2, zorder=0)
        axis.set_xlim(0.0, 100.0)
        axis.set_xticks(np.arange(0.0, 101.0, 20.0))
        axis.set_ylim(-y_limit, y_limit)
        axis.yaxis.set_major_locator(MaxNLocator(nbins=6))
        axis.set_xlabel("DEQS Score", fontsize=28, labelpad=14)
        axis.set_ylabel("Eye Drop Effect (percentage points)", fontsize=28, labelpad=14)
        axis.set_title(label, fontsize=22, pad=16)
        axis.tick_params(axis="both", labelsize=20, width=1.5, length=6)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.text(
            0.04,
            0.96,
            f"N = {int(stat['N'])}\nr = {stat['Pearson_r']:.3f}\np = {stat['Raw_two_sided_p']:.3f}",
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=18,
        )
        figure.tight_layout()
        product_dir = output_root / product
        product_dir.mkdir(parents=True, exist_ok=True)
        path = product_dir / f"No1_DEQS_EyeDropEffect_Correlation_{product}.png"
        figure.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(figure)
        paths.append(path)
    return paths


def run(args: argparse.Namespace) -> dict[str, object]:
    specs = load_manifest(args.manifest)
    deqs = load_deqs_scores(args.deqs_scores, specs)
    recomputed = recompute_phase2_set_means(specs, args.raw_root)
    saved = load_phase2_saved_values(args.phase2_output_root)
    consistency = compare_phase2_values(recomputed, saved)
    dataset = build_analysis_dataset(deqs, recomputed)
    stats_table = correlation_statistics(dataset)
    expected_n = stats_table.set_index("Product")["N"].to_dict()
    if expected_n != {"CCube": 19, "VRohtoPremium": 19}:
        raise ValueError(f"Expected N=19 per product after required-set exclusion, found {expected_n}")

    no1_root = args.output_root / "Phase5_相関・その他" / "No1_DEQS_RT_EyeDropEffect"
    table_dir = no1_root / "Sub" / "tables"
    log_dir = no1_root / "Sub" / "logs"
    table_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "deqs_scores": table_dir / "No1_DEQS_Scores.csv",
        "phase2_consistency": table_dir / "No1_Phase2_RT_ConsistencyCheck.csv",
        "analysis_dataset": table_dir / "No1_DEQS_RT_EyeDropEffect_AnalysisDataset.csv",
        "statistics": table_dir / "No1_CorrelationStatistics.csv",
    }
    deqs.to_csv(files["deqs_scores"], index=False, encoding="utf-8-sig")
    consistency.to_csv(files["phase2_consistency"], index=False, encoding="utf-8-sig")
    dataset.to_csv(files["analysis_dataset"], index=False, encoding="utf-8-sig")
    stats_table.to_csv(files["statistics"], index=False, encoding="utf-8-sig")
    figures = plot_correlations(dataset, stats_table, no1_root)
    summary = {
        "analysis": "Phase5 No1 DEQS and RT eye-drop-effect correlation",
        "completed_at": datetime.now().astimezone().isoformat(),
        "participant_count": len(specs),
        "included_count_by_product": expected_n,
        "excluded_pairs": dataset.loc[
            ~dataset["Included_in_correlation"], ["Pair_ID", "Product", "Exclusion_reason"]
        ].to_dict("records"),
        "deqs_snapshot_is_fixed_for_reruns": True,
        "phase2_exact_match": bool(consistency["All_values_match"].all()),
        "phase2_comparison_tolerance": {"atol": 1e-9, "rtol": 0.0},
        "rt_definition": "KeyPress(ms) - TiltOnset(ms), non-Sys",
        "rt_trial_rule": "RT < 200 ms is NaN; no upper exclusion",
        "eye_drop_effect": "(Control Set6/Set1 - EyeDrop Set6/Set1) * 100",
        "correlation": "Pearson, two-sided raw p, 95% CI",
        "local_processed_data_created": False,
        "outputs": {
            **{key: str(value) for key, value in files.items()},
            "figures": [str(path) for path in figures],
        },
    }
    log_path = log_dir / "No1_DEQS_RT_EyeDropEffect_RunSummary.json"
    log_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Final read-back guards against partial or malformed output writes.
    for path in [*files.values(), *figures, log_path]:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Output verification failed: {path}")
    round_trip = pd.read_csv(files["analysis_dataset"])
    if len(round_trip) != 40 or int(round_trip["Included_in_correlation"].sum()) != 38:
        raise RuntimeError("Analysis dataset read-back validation failed")
    expected_effect = (
        round_trip["Control_set_mean_RT_ms_Set6"]
        / round_trip["Control_set_mean_RT_ms_Set1"]
        - round_trip["EyeDrop_set_mean_RT_ms_Set6"]
        / round_trip["EyeDrop_set_mean_RT_ms_Set1"]
    ) * 100.0
    if not np.allclose(
        expected_effect,
        round_trip["Eye_Drop_Effect_pp"],
        atol=1e-12,
        rtol=0.0,
        equal_nan=True,
    ):
        raise RuntimeError("Eye Drop Effect read-back formula validation failed")
    round_trip_stats = correlation_statistics(round_trip)
    saved_stats = pd.read_csv(files["statistics"])
    for column in [
        "Pearson_r",
        "Raw_two_sided_p",
        "Pearson_r_CI95_lower",
        "Pearson_r_CI95_upper",
    ]:
        if not np.allclose(
            round_trip_stats[column], saved_stats[column], atol=1e-12, rtol=0.0
        ):
            raise RuntimeError(f"Correlation read-back validation failed: {column}")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--deqs-scores", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--phase2-output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


if __name__ == "__main__":
    print(json.dumps(run(parse_args()), ensure_ascii=False, indent=2))
