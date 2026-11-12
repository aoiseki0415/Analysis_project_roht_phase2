"""No10_sub only: add user-specified pair-exclusion group figures.

The full-cohort results and topographies are never replaced by this helper.
All numerical and plotting functions are the same configured No1_sub engine.
This is a post-hoc sensitivity analysis, not a general noise exclusion rule.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd

SUFFIX = "SpecifiedPairsExcluded"
EXCLUDED_PAIRS_BY_PRODUCT = {
    "CCube": frozenset({"120-220"}),
    "VRohtoPremium": frozenset({"131-231", "133-233"}),
}
EXCLUSION_REASON = (
    "User-specified post-hoc sensitivity after persistent PSD Change elevations "
    "were observed in the previous 8-11 Hz analysis; not a validated artifact diagnosis"
)


def select_sensitivity_cohorts(
    items: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], pd.DataFrame]:
    """Check product/pair identity, then remove entire paired sessions from groups."""
    identities = [item["spec"].pair_id for item in items]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate pair in No10_sub sensitivity input")
    actual = {item["spec"].pair_id: item["product_dir"] for item in items}
    for product, excluded in EXCLUDED_PAIRS_BY_PRODUCT.items():
        for pair in excluded:
            if pair not in actual:
                raise ValueError(f"No10_sub sensitivity requires specified pair {pair}")
            if actual[pair] != product:
                raise ValueError(f"No10_sub sensitivity product mismatch for pair {pair}")
    selected: dict[str, list[dict[str, Any]]] = {}
    selection_rows = []
    for product, excluded in EXCLUDED_PAIRS_BY_PRODUCT.items():
        selected[product] = []
        for item in items:
            if item["product_dir"] != product:
                continue
            pair = item["spec"].pair_id
            keep = pair not in excluded
            if keep:
                selected[product].append(item)
            selection_rows.append(
                {
                    "Product": product,
                    "PairID": pair,
                    "Included": keep,
                    "Scope": "Grand-average, Set and All Sets quantification; both conditions",
                    "Reason": "Retained" if keep else EXCLUSION_REASON,
                }
            )
        if not selected[product]:
            raise ValueError(f"No retained pairs for {product} sensitivity analysis")
    return selected, pd.DataFrame(selection_rows)


def write_sensitivity_group_outputs(
    engine: ModuleType,
    items: list[dict[str, Any]],
    output_root: Path,
    *,
    run_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add two products × three PNGs, recomputing axes and paired statistics."""
    selected, selection = select_sensitivity_cohorts(items)
    grand_by_product = {
        product: engine.build_grand_average(cohort, product)[0]
        for product, cohort in selected.items()
    }
    common_limit, common_ticks = engine.grand_average_axis(list(grand_by_product.values()))
    stem = engine.ANALYSIS_STEM
    outputs: dict[str, Any] = {}
    for product, cohort in selected.items():
        paths = engine.output_directories(output_root, product)
        quant_directory = paths["quantification"] / SUFFIX
        for directory in (
            paths["grand"], paths["grand_tables"], paths["quantification_tables"],
            paths["logs"], quant_directory,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        grand = grand_by_product[product]
        grand_png = paths["grand"] / f"{stem}_GrandAverage_{product}_{SUFFIX}.png"
        grand_csv = paths["grand_tables"] / f"{stem}_GrandAverage_Values_{product}_{SUFFIX}.csv"
        engine.plot_grand_average(
            grand, product, grand_png,
            common_limit=common_limit, common_ticks=common_ticks,
        )
        grand.to_csv(grand_csv, index=False)

        quant = engine.build_quantification(cohort, product)
        set_stats, overall_stats = engine.quantification_statistics(quant)
        quant_png = quant_directory / f"{stem}_SetQuantification_{product}_{SUFFIX}.png"
        overall_png = quant_directory / f"{stem}_AllSetsQuantification_{product}_{SUFFIX}.png"
        engine.plot_quantification(quant, set_stats, product, quant_png)
        engine.plot_overall_quantification(quant, overall_stats, product, overall_png)
        quant_csv = (
            paths["quantification_tables"]
            / f"{stem}_Quantification_Values_{product}_{SUFFIX}.csv"
        )
        set_stats_csv = (
            quant_directory / f"{stem}_SetQuantification_Statistics_{product}_{SUFFIX}.csv"
        )
        overall_stats_csv = (
            paths["quantification_tables"]
            / f"{stem}_AllSetsQuantification_Statistics_{product}_{SUFFIX}.csv"
        )
        quant.to_csv(quant_csv, index=False)
        set_stats.to_csv(set_stats_csv, index=False)
        overall_stats.to_csv(overall_stats_csv, index=False)
        paired_n = {}
        for set_number in [*range(1, engine.N_SETS + 1), "All Sets"]:
            section = quant.loc[quant["Set"] == set_number]
            paired_n[str(set_number)] = int(
                np.isfinite(section[["EyeDrop_PSDChange_pct", "Control_PSDChange_pct"]])
                .all(axis=1).sum()
            )
        outputs[product] = {
            "excluded_pair_ids": sorted(EXCLUDED_PAIRS_BY_PRODUCT[product]),
            "retained_pair_ids": sorted(item["spec"].pair_id for item in cohort),
            "valid_pairs": len(cohort),
            "paired_n": paired_n,
            "grand_average": str(grand_png),
            "grand_average_values": str(grand_csv),
            "set_quantification": str(quant_png),
            "all_sets_quantification": str(overall_png),
            "quantification_values": str(quant_csv),
            "set_statistics": str(set_stats_csv),
            "all_sets_statistics": str(overall_stats_csv),
            "grand_y_limit": float(common_limit),
            "grand_y_ticks": common_ticks.tolist(),
        }
    paths = engine.output_directories(output_root, "CCube")
    selection_path = (
        paths["quantification_tables"] / f"{stem}_CohortSelection_{SUFFIX}.csv"
    )
    selection.to_csv(selection_path, index=False)
    summary = {
        "script_version": engine.SCRIPT_VERSION,
        "parent_cache_configuration_version": engine.no1.CACHE_CONFIGURATION_VERSION,
        "included_frequencies_hz": engine.no1.INCLUDED_FREQUENCIES_HZ.tolist(),
        "git_commit": engine.git_revision(),
        "completed_at": datetime.now().astimezone().isoformat(),
        "analysis": "User-specified post-hoc paired sensitivity analysis",
        "reason": EXCLUSION_REASON,
        "excluded_scopes": "Both sessions/all Sets, group curves and quantification only",
        "unchanged_scopes": "Full-cohort results, individual results, all topographies and cache",
        "grand_y_rule": "Shared across sensitivity products; mean-line max absolute / 0.70",
        "quantification_rule": "Post-mask unsmoothed change; existing M-based layout recalculated",
        "statistical_rule": "Paired two-sided t; raw p PNG; Set2-6 Bonferroni/Holm/BH CSV",
        "cohort_selection": str(selection_path),
        "run_context": run_context or {
            "source": "Same invocation as the full-cohort RunSummary.json",
        },
        "outputs": outputs,
    }
    engine.write_log(paths["logs"] / f"{stem}_{SUFFIX}_RunSummary.json", summary)
    return summary


def install_sensitivity_group_outputs(engine: ModuleType) -> None:
    """Extend only this configured No10_sub process, not the shared engine source."""
    original_write_group = engine.write_group

    def write_group(items: list[dict[str, Any]], output_root: Path) -> dict[str, Any]:
        # A pilot can contain just one pair. Full production is validated as 39
        # analysable pairs upstream and therefore cannot silently skip this addition.
        production_size = len(items) == engine.no1.PRODUCTION_PARTICIPANT_COUNT - 1
        if production_size:
            select_sensitivity_cohorts(items)
        outputs = original_write_group(items, output_root)
        if production_size:
            summary = write_sensitivity_group_outputs(engine, items, output_root)
            for product, result in summary["outputs"].items():
                outputs[product]["specified_pair_sensitivity"] = result
        else:
            logging.info("No10_sub pilot: automatic full-cohort sensitivity not requested")
        return outputs

    engine.write_group = write_group


def sensitivity_main(engine: ModuleType) -> int:
    """Explicit cache-only rerender of the six additional sensitivity figures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sensitivity-only", action="store_true", required=True)
    parser.add_argument(
        "--participant", action="append", type=engine.no1.parse_participant, default=[]
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--cache-root", type=Path, default=engine.DEFAULT_CACHE_ROOT)
    parser.add_argument("--output-root", type=Path, default=engine.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--production-batch", action="store_true")
    args = parser.parse_args()
    specs = list(args.participant)
    if args.manifest:
        specs.extend(engine.no1.load_manifest(args.manifest))
    if not specs:
        parser.error("Provide --participant or --manifest")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    items, preflight_summary = engine.preflight(specs, args.cache_root, args.production_batch)
    write_sensitivity_group_outputs(
        engine, items, args.output_root,
        run_context={
            "mode": "sensitivity-only",
            "manifest": str(args.manifest) if args.manifest else None,
            "cache_root": str(args.cache_root),
            "preflight": preflight_summary,
        },
    )
    logging.info("No10_sub specified-pair sensitivity outputs completed")
    return 0
