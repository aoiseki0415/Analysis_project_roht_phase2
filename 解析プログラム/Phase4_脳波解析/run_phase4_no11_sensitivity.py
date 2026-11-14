#!/usr/bin/env python3
"""Add only the explicitly requested paired No11/Pz sensitivity group outputs.

The all-participant outputs, source No10 caches, individual figures and other
analyses are protected. This is post-hoc participant selection, not an automated
artifact diagnosis or a change to the primary inclusion policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib.figure
import matplotlib.text
import numpy as np
import pandas as pd
import phase4_no11_cached_analysis as adapter
import run_phase4_no11 as primary

SUFFIX = "SpecifiedPairsExcluded"
VERSION = "20261114_no11_paired_sensitivity_v1"
PRODUCTS = ("CCube", "VRohtoPremium")
EXCLUDED_PAIRS_BY_PRODUCT = {
    "CCube": frozenset({"132-232", "140-240", "141-241"}),
    "VRohtoPremium": frozenset({"131-231"}),
}
MANIFEST = primary.ROOTS[0] / "Sub/tables/ParticipantManifest.csv"
RECORD = primary.LOGS / f"No11_{SUFFIX}_Execution.json"
VALIDATION = primary.LOGS / f"No11_{SUFFIX}_IndependentValidation.json"
DELIVERY = primary.LOGS / f"No11_{SUFFIX}_DeliveryVerification.json"
TESTS = primary.LOGS / f"No11_{SUFFIX}_Tests.xml"
REASON = "User-specified post-hoc sensitivity; not a validated artifact diagnosis"
TOKYO = ZoneInfo("Asia/Tokyo")


def output_paths(stem: str, product: str, output_root: Path | None = None) -> dict[str, Path]:
    if stem not in primary.STEMS or product not in PRODUCTS:
        raise ValueError("Unknown No11 analysis or product")
    root = (output_root or primary.source.DEFAULT_OUTPUT_ROOT) / "Phase4_脳波解析" / stem
    quant = root / product / "SetQuantification" / SUFFIX
    tables = root / "Sub/tables/SetQuantification" / SUFFIX
    return {
        "grand_png": root / product / "GrandAverage"
        / f"{stem}_GrandAverage_{product}_{SUFFIX}.png",
        "grand_csv": root / "Sub/tables/GrandAverage"
        / f"{stem}_GrandAverage_Values_{product}_{SUFFIX}.csv",
        "set_png": quant / f"{stem}_SetQuantification_{product}_{SUFFIX}.png",
        "all_png": quant / f"{stem}_AllSetsQuantification_{product}_{SUFFIX}.png",
        "set_stats": quant / f"{stem}_SetQuantification_Statistics_{product}_{SUFFIX}.csv",
        "values": tables / f"{stem}_Quantification_Values_{product}_{SUFFIX}.csv",
        "all_stats": tables / f"{stem}_AllSetsQuantification_Statistics_{product}_{SUFFIX}.csv",
    }


def selection_path(stem: str, output_root: Path | None = None) -> Path:
    return (output_root or primary.source.DEFAULT_OUTPUT_ROOT) / "Phase4_脳波解析" / stem / (
        f"Sub/tables/{stem}_{SUFFIX}_CohortSelection.csv"
    )


def allowed_outputs() -> set[Path]:
    paths = {RECORD}
    for stem, root in zip(primary.STEMS, primary.ROOTS, strict=True):
        for product in PRODUCTS:
            paths.update(output_paths(stem, product).values())
        paths.add(selection_path(stem))
        paths.add(root / "Sub/logs" / f"{stem}_{SUFFIX}_RunSummary.json")
    return paths


def verify_source_audit(path: Path, specs: list[Any]) -> dict[str, Any]:
    audit = json.loads(path.read_text(encoding="utf-8"))
    if (audit.get("matched_pairs"), audit.get("matched_sessions"), audit.get("mismatches")) != (
        40, 80, 0
    ):
        raise ValueError("Current full40-pair/80-session mapping audit required")
    checked = datetime.fromisoformat(audit.get("checked_at", ""))
    if checked.tzinfo is None or checked.astimezone(TOKYO).date() != datetime.now(TOKYO).date():
        raise ValueError("Source audit must have today's timezone-aware checked_at")
    if audit.get("manifest_sha256") != primary.digest(MANIFEST):
        raise ValueError("Manifest hash differs from current source audit")
    normalization = audit.get("request_normalization", {})
    if (
        normalization.get("original") != "14-240"
        or normalization.get("canonical") != "140-240"
        or normalization.get("verified") is not True
        or not normalization.get("evidence")
    ):
        raise ValueError("Live confirmation of 14-240 -> 140-240 is required")
    matching = [spec for spec in specs if "240" in (
        spec.first_session_id, spec.second_session_id
    )]
    if len(matching) != 1 or matching[0].pair_id != "140-240":
        raise ValueError("Session240 must map uniquely to 140-240")
    if primary.source.normalize_product(matching[0].product)[0] != "CCube":
        raise ValueError("Canonical 140-240 product mismatch")
    requested = audit.get("explicit_requested_exclusions", [])
    manifest_by_pair = {spec.pair_id: spec for spec in specs}
    expected_pairs = {pair for pairs in EXCLUDED_PAIRS_BY_PRODUCT.values() for pair in pairs}
    request_pairs = [f"{row.get('first_session_id')}-{row.get('second_session_id')}"
                     for row in requested]
    if len(request_pairs) != 4 or set(request_pairs) != expected_pairs:
        raise ValueError("Source audit requested exclusion set differs from fixed cohort")
    for pair, row in zip(request_pairs, requested, strict=True):
        participant = manifest_by_pair.get(pair)
        product = row.get("product")
        if (participant is None or product not in EXCLUDED_PAIRS_BY_PRODUCT
                or pair not in EXCLUDED_PAIRS_BY_PRODUCT[product]
                or primary.source.normalize_product(participant.product)[0] != product
                or participant.drops_session_id != str(row.get("drops_session_id"))):
            raise ValueError(f"Source audit exclusion conditions differ from manifest: {pair}")
    return audit


def select_items(
    items: list[dict[str, Any]], specs: list[Any]
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Select whole pairs without dropping/reordering the source manifest."""
    identities = [item["spec"].pair_id for item in items]
    spec_ids = [spec.pair_id for spec in specs]
    if len(identities) != len(set(identities)) or len(spec_ids) != len(set(spec_ids)):
        raise ValueError("Duplicate pair identity")
    if not set(identities).issubset(spec_ids):
        raise ValueError("Input pair not in source manifest")
    actual = {item["spec"].pair_id: item["product_dir"] for item in items}
    for product, excluded in EXCLUDED_PAIRS_BY_PRODUCT.items():
        for pair in excluded:
            if actual.get(pair) != product:
                raise ValueError(f"Specified pair absent or product mismatch: {pair}")
    retained = []
    for item in items:
        product = primary.source.normalize_product(item["spec"].product)[0]
        if actual[item["spec"].pair_id] != product:
            raise ValueError("Item/manifest product mismatch")
        if item["spec"].pair_id not in EXCLUDED_PAIRS_BY_PRODUCT[product]:
            retained.append(item)
    rows = []
    for spec in specs:
        product = primary.source.normalize_product(spec.product)[0]
        eligible = spec.pair_id in actual
        excluded = spec.pair_id in EXCLUDED_PAIRS_BY_PRODUCT[product]
        rows.append({
            "Product": product,
            "PairID": spec.pair_id,
            "EyeDropSessionID": spec.drops_session_id,
            "ControlSessionID": spec.control_session_id,
            "PrimaryAnalysisEligible": eligible,
            "SpecifiedPairExcluded": excluded,
            "Included": eligible and not excluded,
            "Reason": (
                "Existing Set1 baseline unavailable" if not eligible
                else REASON if excluded else "Retained"
            ),
        })
    if any(not any(item["product_dir"] == product for item in retained) for product in PRODUCTS):
        raise ValueError("Each product must retain at least one pair")
    return retained, pd.DataFrame(rows)


def load_analysis_items(specs: list[Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    absolute = adapter.build_absolute_engine()
    change = adapter.build_change_engine(absolute)
    absolute.validate_participant_specs(specs, production_batch=True)
    absolute_items = [absolute.load_pair_item(spec, absolute.DEFAULT_CACHE_ROOT) for spec in specs]
    for item in absolute_items:
        for condition in ("eye_drop", "control"):
            absolute._channel_index(item[condition], "Pz")
    change_items, baseline_summary = change.preflight(specs, change.DEFAULT_CACHE_ROOT, True)
    analyses = {}
    for engine, items, expected in (
        (absolute, absolute_items, {"CCube": 17, "VRohtoPremium": 19}),
        (change, change_items, {"CCube": 17, "VRohtoPremium": 18}),
    ):
        retained, selection = select_items(items, specs)
        counts = {product: sum(item["product_dir"] == product for item in retained)
                  for product in PRODUCTS}
        if counts != expected:
            raise ValueError(f"Unexpected retained cohort: {engine.ANALYSIS_STEM}: {counts}")
        analyses[engine.ANALYSIS_STEM] = (engine, retained, selection)
    return analyses, baseline_summary


def absolute_grand_axis(engine: Any, frames: list[pd.DataFrame]) -> tuple[float, np.ndarray]:
    fraction = engine.DEFAULT_GRAND_AVERAGE_TARGET_FRACTION
    values = [
        frame[f"{condition}_Mean_PSD_uV2_per_Hz"]
        + frame[f"{condition}_SEM_PSD_uV2_per_Hz"].fillna(0.0)
        for frame in frames for condition in ("EyeDrop", "Control")
    ]
    upper = max(engine._nice_upper(value.to_numpy(), fraction)[0] for value in values)
    _, ticks = engine._nice_upper(np.array([upper * fraction]), fraction)
    if ticks[-1] != upper:
        ticks = np.arange(0.0, upper + (ticks[1] - ticks[0]) * .01, ticks[1] - ticks[0])
    return upper, ticks


@contextmanager
def capture_plot_metadata(records: list[dict[str, Any]], permitted: set[Path]):
    """Record actual artists at save-time, without changing plotting behavior."""
    original = matplotlib.figure.Figure.savefig

    def savefig(figure, filename, *args, **kwargs):
        path = Path(filename)
        if path.resolve() not in {item.resolve() for item in permitted}:
            raise ValueError("Attempted unexpected sensitivity figure output")
        axes = [{
            "ylim": list(axis.get_ylim()),
            "yticks": axis.get_yticks().tolist(),
            "ylabel": axis.get_ylabel(),
            "xlabel": axis.get_xlabel(),
            "xticklabels": [label.get_text() for label in axis.get_xticklabels()],
            "texts": [{"text": text.get_text(), "x": text.get_position()[0],
                       "y": text.get_position()[1], "fontsize": text.get_fontsize(),
                       "fontfamily": text.get_fontfamily()} for text in axis.texts],
        } for axis in figure.axes]
        fonts = sorted({family for text in figure.findobj(matplotlib.text.Text)
                        for family in text.get_fontfamily()})
        if fonts != ["Arial"]:
            raise ValueError(f"Unexpected figure font families: {fonts}")
        result = original(figure, filename, *args, **kwargs)
        records.append({"path": str(path), "axes": axes, "panel_count": len(axes),
                        "font_families": fonts, "sha256": primary.digest(path)})
        return result

    matplotlib.figure.Figure.savefig = savefig
    try:
        yield
    finally:
        matplotlib.figure.Figure.savefig = original


def write_analysis(engine: Any, items: list[dict[str, Any]], selection: pd.DataFrame) -> dict:
    stem = engine.ANALYSIS_STEM
    is_change = stem == adapter.CHANGE_STEM
    frames = {product: engine.build_grand_average(items, product)[0] for product in PRODUCTS}
    upper, ticks = (engine.grand_average_axis(list(frames.values())) if is_change
                    else absolute_grand_axis(engine, list(frames.values())))
    outputs = {}
    for product in PRODUCTS:
        paths = output_paths(stem, product)
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        frame = frames[product]
        plot_options = {"common_limit" if is_change else "common_upper": upper,
                        "common_ticks": ticks}
        engine.plot_grand_average(frame, product, paths["grand_png"], **plot_options)
        frame.to_csv(paths["grand_csv"], index=False)
        values = engine.build_quantification(items, product)
        set_stats, all_stats = engine.quantification_statistics(values)
        plot_set = engine.plot_quantification if is_change else engine.plot_set_quantification
        plot_all = (engine.plot_overall_quantification if is_change
                    else engine.plot_all_sets_quantification)
        plot_set(values, set_stats, product, paths["set_png"])
        plot_all(values, all_stats, product, paths["all_png"])
        for key, table in (("values", values), ("set_stats", set_stats), ("all_stats", all_stats)):
            table.to_csv(paths[key], index=False)
        columns = [f"{condition}_{'PSDChange_pct' if is_change else 'PSD_uV2_per_Hz'}"
                   for condition in ("EyeDrop", "Control")]
        paired_n = {str(number): int(np.isfinite(
            values.loc[values["Set"] == number, columns].to_numpy(float)
        ).all(axis=1).sum()) for number in [1, 2, 3, 4, 5, 6, "All Sets"]}
        shade_outside = {}
        metric = "PSDChange_pct" if is_change else "PSD_uV2_per_Hz"
        for condition in ("EyeDrop", "Control"):
            mean = frame[f"{condition}_Mean_{metric}"].to_numpy(float)
            sem = frame[f"{condition}_SEM_{metric}"].to_numpy(float)
            shade_outside[condition] = int(((mean + sem > upper) | (
                mean - sem < (-upper if is_change else 0)
            )).sum())
        outputs[product] = {
            "paths": {key: str(value) for key, value in paths.items()},
            "retained_pair_ids": [item["spec"].pair_id for item in items
                                  if item["product_dir"] == product],
            "excluded_pair_ids": sorted(EXCLUDED_PAIRS_BY_PRODUCT[product]),
            "paired_n": paired_n, "grand_y_limit": float(upper),
            "grand_y_ticks": ticks.tolist(), "shade_points_outside_axes": shade_outside,
        }
    path = selection_path(stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    selection.to_csv(path, index=False)
    summary = {"version": VERSION, "analysis_stem": stem, "cohort": SUFFIX,
               "focus_channel": "Pz", "frequencies_hz": [8, 9, 10], "reason": REASON,
               "selection_csv": str(path), "outputs": outputs,
               "status": "generated_pending_independent_and_visual_verification"}
    primary.save(primary.PHASE / stem / "Sub/logs" / f"{stem}_{SUFFIX}_RunSummary.json", summary)
    return summary


def protected_snapshot() -> dict[str, Any]:
    return {
        "primary_no11": {
            path: attributes for root in primary.ROOTS
            for path, attributes in primary.inventory(root, hashes=True).items()
            if Path(path) not in allowed_outputs() | {VALIDATION, DELIVERY, TESTS}
        },
        "source_cache": primary.inventory(primary.source.DEFAULT_CACHE_ROOT, hashes=True),
        "other_analyses": primary.protected_inventory(),
    }


def execute(audit_path: Path, *, preflight_only: bool = False, replace: bool = False) -> dict:
    commit = primary.git_check()
    specs = primary.source.load_manifest(MANIFEST)
    primary.source.validate_participant_specs(specs, production_batch=True)
    audit = verify_source_audit(audit_path, specs)
    analyses, baseline_summary = load_analysis_items(specs)
    if preflight_only:
        return {"status": "preflight_passed", "analyses": {
            stem: {product: sum(item["product_dir"] == product for item in items)
                   for product in PRODUCTS} for stem, (_, items, _) in analyses.items()
        }}
    existing = sorted(path for path in allowed_outputs() if path.exists())
    if existing and not replace:
        raise RuntimeError(
            "Sensitivity outputs already exist; explicit --replace-existing required"
        )
    record = {
        "status": "running", "version": VERSION,
        "started_at": datetime.now(TOKYO).isoformat(), "implementation_base_commit": commit,
        "source_audit": audit, "baseline_preflight": baseline_summary,
        "protected_before": protected_snapshot(), "plots": [], "analyses": {},
        "code_hashes": {
            str(path.relative_to(primary.REPO)): primary.digest(path)
            for path in (*primary.SCRIPTS.glob("*no11*.py"),
                         primary.SCRIPTS / "Phase4_No1_FmTheta.py",
                         primary.SCRIPTS / "Phase4_No1_sub_FmThetaChange.py",
                         primary.SCRIPTS / "phase4_band_variant_config.py")
        },
        "cloud_sync": "Authorized local OneDrive write/readback; server sync not verified",
        "replaces_existing_sensitivity_only": replace,
        "prior_sensitivity_hashes": {str(path): primary.digest(path) for path in existing},
    }
    primary.save(RECORD, record)
    try:
        png_paths = {path for path in allowed_outputs() if path.suffix == ".png"}
        with capture_plot_metadata(record["plots"], png_paths):
            for stem, (engine, items, selection) in analyses.items():
                record["analyses"][stem] = write_analysis(engine, items, selection)
        if protected_snapshot() != record["protected_before"]:
            raise RuntimeError("Protected primary outputs, caches or earlier analyses changed")
        if {Path(row["path"]) for row in record["plots"]} != png_paths:
            raise RuntimeError("Incomplete sensitivity figure set")
        record.update(
            status="generated_pending_independent_and_visual_verification",
            generated_at=datetime.now(TOKYO).isoformat(), protected_unchanged=True,
            output_files=[{"path": str(path), "sha256": primary.digest(path)}
                          for path in sorted(allowed_outputs() - {RECORD})],
        )
    except Exception as error:
        record.update(status="failed", error=repr(error), failed_at=datetime.now(TOKYO).isoformat())
        primary.save(RECORD, record)
        raise
    primary.save(RECORD, record)
    return record


def complete(review_path: Path) -> dict:
    """Confirm generated artifacts, independent audit, review, and remote Git delivery."""
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    if record.get("status") != "generated_pending_independent_and_visual_verification":
        raise RuntimeError("Successful sensitivity generation must precede final verification")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("status") != "passed" or review.get("tests_passed") is not True:
        raise RuntimeError("Successful tests, visual review and document readback required")
    report = Path(review["test_report"]["path"])
    if primary.digest(report) != review["test_report"]["sha256"]:
        raise RuntimeError("Test report changed")
    suites = ET.parse(report).getroot()
    if not list(suites.iter("testcase")) or any(
        list(suites.iter(tag)) for tag in ("failure", "error")
    ):
        raise RuntimeError("JUnit report does not confirm passing tests")
    for relative, executed_hash in record["code_hashes"].items():
        if primary.digest(primary.REPO / relative) != executed_hash:
            raise RuntimeError(f"Executed code changed: {relative}")
    for output in record["output_files"]:
        if primary.digest(Path(output["path"])) != output["sha256"]:
            raise RuntimeError(f"Generated artifact changed: {output['path']}")
    validation_evidence = review.get("independent_validation", {})
    if (validation_evidence.get("path") != str(VALIDATION)
            or primary.digest(VALIDATION) != validation_evidence.get("sha256")):
        raise RuntimeError("Independent validation evidence missing or changed")
    if json.loads(VALIDATION.read_text(encoding="utf-8")).get("status") != "passed":
        raise RuntimeError("Independent validation did not pass")
    required_pngs = {str(path) for path in allowed_outputs() if path.suffix == ".png"}
    reviewed = review.get("visual_checks", [])
    if {item["path"] for item in reviewed} != required_pngs or len(reviewed) != 12:
        raise RuntimeError("Visual confirmation of all 12 additional figures required")
    for item in reviewed:
        if item.get("status") != "passed" or primary.digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Visual review missing or changed")
    for section in ("document_checks", "notion_checks"):
        if not review.get(section) or any(item.get("status") != "passed"
                                          for item in review[section]):
            raise RuntimeError("Document/Notion readback incomplete")
    if protected_snapshot() != record["protected_before"]:
        raise RuntimeError("Protected inputs or primary artifacts changed")
    import validate_phase4_no11_sensitivity_outputs as validator

    repeated = {"caches": [], "tables": [], "groups": [], "images": [],
                "png_counts": {}, "plot_metadata": []}
    validator.run(SimpleNamespace(
        manifest=MANIFEST, cache_root=primary.source.DEFAULT_CACHE_ROOT,
        output_root=primary.source.DEFAULT_OUTPUT_ROOT, execution_report=RECORD,
    ), repeated)
    if repeated.get("status") != "passed":
        raise RuntimeError("Delivery-time independent reconstruction failed")
    head = primary.git_check()
    remote = primary.subprocess.check_output(
        ["git", "ls-remote", "origin", "refs/heads/main"], cwd=primary.REPO, text=True
    ).split()[0]
    if head != remote:
        raise RuntimeError("Remote Git commit mismatch")
    for relative, expected_hash in record["code_hashes"].items():
        committed = primary.subprocess.check_output(
            ["git", "show", f"HEAD:{relative}"], cwd=primary.REPO
        )
        if hashlib.sha256(committed).hexdigest() != expected_hash:
            raise RuntimeError("Executed analysis/validation code is not committed")
    for item in review["document_checks"]:
        path = Path(item["path"]).resolve()
        if not path.is_relative_to(primary.REPO) or primary.digest(path) != item["sha256"]:
            raise RuntimeError("Reviewed repository file changed or outside scope")
        committed = primary.subprocess.check_output(
            ["git", "show", f"HEAD:{path.relative_to(primary.REPO).as_posix()}"], cwd=primary.REPO
        )
        if hashlib.sha256(committed).hexdigest() != item["sha256"]:
            raise RuntimeError("Reviewed repository file is not committed")
    TESTS.parent.mkdir(parents=True, exist_ok=True)
    TESTS.write_bytes(report.read_bytes())
    if primary.digest(TESTS) != review["test_report"]["sha256"]:
        raise RuntimeError("Durable test report copy changed")
    delivery = {**review, "test_report": {"path": str(TESTS), "sha256": primary.digest(TESTS)},
                "completed_at": datetime.now(TOKYO).isoformat(),
                "git_commit": head, "verified_remote_commit": remote,
                "delivery_time_independent_reconstruction": "passed",
                "protected_unchanged": True, "cloud_sync": record["cloud_sync"]}
    primary.save(DELIVERY, delivery)
    record.update(status="completed", final_git_commit=head, delivery_verification=str(DELIVERY))
    primary.save(RECORD, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-source-audit", type=Path)
    parser.add_argument("--review-manifest", type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--complete-verification", action="store_true")
    parser.add_argument("--replace-existing", action="store_true",
                        help="Explicitly rerender this sensitivity only; never primary outputs")
    args = parser.parse_args()
    if args.complete_verification:
        if not args.review_manifest:
            parser.error("--review-manifest required")
        record = complete(args.review_manifest)
    else:
        if not args.manifest_source_audit:
            parser.error("--manifest-source-audit required")
        record = execute(args.manifest_source_audit, preflight_only=args.preflight_only,
                         replace=args.replace_existing)
    print(json.dumps({"status": record["status"], "record": str(RECORD)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
