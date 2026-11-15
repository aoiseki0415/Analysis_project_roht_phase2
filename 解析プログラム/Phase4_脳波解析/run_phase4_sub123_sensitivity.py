#!/usr/bin/env python3
"""Cache-only, additive representative-channel sensitivity for No1/2/2-2/3 sub.

Selections are read from the current canonical attention document, then checked
against a fresh source/condition audit. No participant IDs are embedded here.
Main, individual, topography and source-cache artifacts are protected by hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo

import h5py
import matplotlib.figure
import matplotlib.text
import numpy as np
import pandas as pd
from phase4_band_variant_config import configure_change_engine
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
ATTENTION = REPO / "docs/解析上の注意事項.md"
ORIGIN = "https://github.com/aoiseki0415/Analysis_project_roht_phase2.git"
VERSION = "20261116_sub123_specified_pairs_v1"
SUFFIX = "SpecifiedPairsExcluded"
TOKYO = ZoneInfo("Asia/Tokyo")
PRODUCTS = ("CCube", "VRohtoPremium")
ANALYSES = {
    "no1": ("No1_sub_FmThetaChange", "No1_sub", "Phase4_No1_FmTheta.py", "Fz"),
    "no2": ("No2_sub_OccipitalAlphaChange", "No2_sub", "Phase4_No2_OccipitalAlpha.py", "Oz"),
    "no2-pz": (
        "No2-2_sub_OccipitalAlphaChange_Pz", "No2-2_sub", "Phase4_No2_OccipitalAlpha.py", "Pz"
    ),
    "no3": ("No3_sub_FrontalDeltaChange", "No3_sub", "Phase4_No3_FrontalDelta.py", "Fz"),
}
REASON = "User-confirmed qualitative signal-quality concern; not a proven artifact diagnosis"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def isolated(filename: str, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load engine {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def temporary_module(name: str, module: ModuleType):
    """Run existing band wrappers unchanged, without polluting other engines."""
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        yield
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def build_engine(key: str) -> ModuleType:
    stem, _, parent_file, channel = ANALYSES[key]
    parent = isolated("Phase4_No1_FmTheta.py", f"_sub123_{key}_parent")
    if parent_file != "Phase4_No1_FmTheta.py":
        with temporary_module("Phase4_No1_FmTheta", parent):
            isolated(parent_file, f"_sub123_{key}_parent_wrapper")
    with temporary_module("Phase4_No1_FmTheta", parent):
        engine = isolated("Phase4_No1_sub_FmThetaChange.py", f"_sub123_{key}_change")
    configure_change_engine(engine, parent, analysis_stem=stem, focus_channel=channel,
                            script_version=VERSION, include_topography=False)
    return engine


def documented_exclusions(path: Path = ATTENTION) -> dict[str, dict[str, set[str]]]:
    text = path.read_text(encoding="utf-8")
    marker = "## Phase 4 sub被験者除外の現行指定（2026-11-16）"
    if text.count(marker) != 1:
        raise ValueError("Unique current exclusion section is required")
    section = text.split(marker, 1)[1].split("\n## ", 1)[0]
    result = {}
    for key, (_, label, _, _) in ANALYSES.items():
        rows = [line for line in section.splitlines() if line.startswith(f"| {label}（")]
        if len(rows) != 1:
            raise ValueError(f"Unique current cohort row required: {label}")
        cells = rows[0].split("|")
        groups = {}
        for product, cell in (("VRohtoPremium", cells[2]), ("CCube", cells[3])):
            pairs = re.findall(r"(\d+)[–−-](\d+)", cell)
            if not pairs and "なし" not in cell:
                raise ValueError(f"Unreadable exclusion specification: {label}/{product}")
            canonical = {f"{first}-{second}" for first, second in pairs}
            if len(canonical) != len(pairs):
                raise ValueError("Duplicate pair in canonical selection")
            groups[product] = canonical
        result[key] = groups
    return result


def verify_source_audit(path: Path, manifest: Path, exclusions: dict) -> dict:
    audit = json.loads(path.read_text(encoding="utf-8"))
    if (audit.get("matched_pairs"), audit.get("matched_sessions"), audit.get("mismatches")) != (
        40, 80, 0
    ):
        raise ValueError("A current full 40-pair/80-session condition audit is required")
    checked = datetime.fromisoformat(audit.get("checked_at", ""))
    if checked.tzinfo is None or checked.astimezone(TOKYO).date() != datetime.now(TOKYO).date():
        raise ValueError("Source audit must be checked today with timezone")
    if audit.get("manifest_sha256") != digest(manifest):
        raise ValueError("Manifest changed after source audit")
    expected = {ANALYSES[key][0]: {p: sorted(v) for p, v in groups.items()}
                for key, groups in exclusions.items()}
    if audit.get("explicit_exclusions") != expected:
        raise ValueError("Live source audit and canonical exclusion sets differ")
    return audit


def select_items(items: list[dict], specs: list, exclusions: dict[str, set[str]],
                 *, normalize=None):
    identities = [item["spec"].pair_id for item in items]
    spec_ids = [spec.pair_id for spec in specs]
    if len(identities) != len(set(identities)) or len(spec_ids) != len(set(spec_ids)):
        raise ValueError("Duplicate pair identity")
    if not set(identities).issubset(spec_ids):
        raise ValueError("Input pair not present in manifest")
    actual = {item["spec"].pair_id: item["product_dir"] for item in items}
    for product, pairs in exclusions.items():
        for pair in pairs:
            if actual.get(pair) != product:
                raise ValueError(f"Specified pair absent or product mismatch: {pair}")
    selected = {product: [item for item in items if item["product_dir"] == product
                          and item["spec"].pair_id not in excluded]
                for product, excluded in exclusions.items() if excluded}
    if not selected or any(not cohort for cohort in selected.values()):
        raise ValueError("Each requested additional product must retain participants")
    rows = []
    for spec in specs:
        # Manifest product spelling is normalized upstream and recorded from items
        # where possible; the source normalizer is supplied by the caller below.
        product = normalize(spec.product)[0] if normalize else spec.product
        if eligible_product := actual.get(spec.pair_id):
            if product != eligible_product:
                raise ValueError("Item/manifest product mismatch")
        eligible = spec.pair_id in actual
        excluded = spec.pair_id in exclusions.get(product, set())
        requested = bool(exclusions.get(product, set()))
        rows.append({"Product": product, "PairID": spec.pair_id,
                     "EyeDropSessionID": spec.drops_session_id,
                     "ControlSessionID": spec.control_session_id,
                     "PrimaryAnalysisEligible": eligible, "AdditionalProductRequested": requested,
                     "SpecifiedPairExcluded": excluded,
                     "Included": requested and eligible and not excluded,
                     "Reason": ("Existing Set1 baseline unavailable" if not eligible else
                                "No additional cohort for this product" if not requested else
                                REASON if excluded else "Retained")})
    return selected, pd.DataFrame(rows)


def output_paths(root: Path, stem: str, product: str) -> dict[str, Path]:
    base = root / "Phase4_脳波解析" / stem
    quant = base / product / "SetQuantification" / SUFFIX
    tables = base / "Sub/tables/SetQuantification"
    return {
        "grand_png": base / product / "GrandAverage"
        / f"{stem}_GrandAverage_{product}_{SUFFIX}.png",
        "grand_csv": base / "Sub/tables/GrandAverage"
        / f"{stem}_GrandAverage_Values_{product}_{SUFFIX}.csv",
        "set_png": quant / f"{stem}_SetQuantification_{product}_{SUFFIX}.png",
        "all_png": quant / f"{stem}_AllSetsQuantification_{product}_{SUFFIX}.png",
        "set_stats": quant / f"{stem}_SetQuantification_Statistics_{product}_{SUFFIX}.csv",
        "values": tables / f"{stem}_Quantification_Values_{product}_{SUFFIX}.csv",
        "all_stats": tables / f"{stem}_AllSetsQuantification_Statistics_{product}_{SUFFIX}.csv",
    }


def support_paths(root: Path, stem: str) -> dict[str, Path]:
    base = root / "Phase4_脳波解析" / stem / "Sub"
    return {
        "selection": base / "tables/SetQuantification" / f"{stem}_CohortSelection_{SUFFIX}.csv",
        "record": base / "logs" / f"{stem}_{SUFFIX}_RunSummary.json",
    }


def inventory(root: Path, ignored: set[Path] | None = None) -> dict[str, dict]:
    ignored = {p.resolve() for p in ignored or set()}
    return {str(p): {"sha256": digest(p), "size": p.stat().st_size}
            for p in sorted(root.rglob("*")) if p.is_file() and p.name != ".DS_Store"
            and p.resolve() not in ignored}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.write_text(content, encoding="utf-8")
    if path.read_text(encoding="utf-8") != content:
        raise RuntimeError("JSON readback mismatch")


def cache_provenance(engine: ModuleType, specs: list) -> list[dict]:
    parent = engine.no1
    records = []
    for spec in specs:
        for sid in (spec.first_session_id, spec.second_session_id):
            path = parent.cache_path(parent.DEFAULT_CACHE_ROOT, spec, sid)
            with h5py.File(path, "r") as handle:
                attrs = handle.attrs
                expected_condition = "Eye Drop" if sid == spec.drops_session_id else "Control"
                if (str(attrs["participant_id"]) != sid or str(attrs["pair_id"]) != spec.pair_id
                        or str(attrs["condition"]) != expected_condition
                        or parent.normalize_product(str(attrs["product"]))[0]
                        != parent.normalize_product(spec.product)[0]):
                    raise ValueError(f"Cache identity/condition mismatch: {path}")
                settings = dict(parent.analysis_configuration())
                # Original No1 cache predates only these descriptive hash keys.
                if parent.ANALYSIS_STEM == "No1_FmTheta":
                    settings.pop("analysis_stem")
                    settings.pop("focus_channel")
                payload = {"configuration": settings,
                           "inputs": json.loads(str(attrs["input_fingerprints_json"]))}
                expected = hashlib.sha256(json.dumps(
                    payload, sort_keys=True, separators=(",", ":")
                ).encode()).hexdigest()
                if str(attrs["configuration_hash"]) != expected:
                    raise ValueError(f"Cache configuration/input hash mismatch: {path}")
                if not np.array_equal(json.loads(str(attrs["included_frequencies_hz"])),
                                      parent.INCLUDED_FREQUENCIES_HZ):
                    raise ValueError("Cache frequency-bin mismatch")
            records.append({"path": str(path), "sha256": digest(path),
                            "configuration_hash": expected})
    return records


@contextmanager
def capture_plots(records: list, allowed: set[Path]):
    original = matplotlib.figure.Figure.savefig
    allowed = {p.resolve() for p in allowed}

    def save(figure, filename, *args, **kwargs):
        path = Path(filename)
        if path.resolve() not in allowed:
            raise ValueError("Out-of-scope figure path")
        fonts = sorted({family for text in figure.findobj(matplotlib.text.Text)
                        for family in text.get_fontfamily()})
        if fonts != ["Arial"]:
            raise ValueError(f"Unexpected fonts: {fonts}")
        axes = [{"ylim": list(ax.get_ylim()), "yticks": ax.get_yticks().tolist(),
                 "xlabel": ax.get_xlabel(), "ylabel": ax.get_ylabel(),
                 "texts": [{"text": t.get_text(), "position": list(t.get_position()),
                            "fontsize": t.get_fontsize()} for t in ax.texts]}
                for ax in figure.axes]
        result = original(figure, filename, *args, **kwargs)
        with Image.open(path) as image:
            image.load()
        records.append({"path": str(path), "sha256": digest(path),
                        "font_families": fonts, "axes": axes})
        return result

    matplotlib.figure.Figure.savefig = save
    try:
        yield
    finally:
        matplotlib.figure.Figure.savefig = original


def execute_analysis(key: str, manifest: Path, audit: dict, exclusions: dict,
                     *, preflight_only: bool, replace: bool) -> dict:
    engine = build_engine(key)
    root, stem = engine.DEFAULT_OUTPUT_ROOT, engine.ANALYSIS_STEM
    specs = engine.no1.load_manifest(manifest)
    source = cache_provenance(engine, specs)
    items, baseline = engine.preflight(specs, engine.DEFAULT_CACHE_ROOT, True)
    # Normalize audit identities without modifying the source manifest.
    selected, selection = select_items(items, specs, exclusions,
                                       normalize=engine.no1.normalize_product)
    if preflight_only:
        return {"status": "preflight_passed", "analysis_stem": stem,
                "retained": {p: len(v) for p, v in selected.items()}, "baseline": baseline}
    paths_by_product = {p: output_paths(root, stem, p) for p in selected}
    support = support_paths(root, stem)
    allowed = set(support.values()) | {p for paths in paths_by_product.values()
                                       for p in paths.values()}
    if not replace and any(p.exists() for p in allowed):
        raise RuntimeError("Additional outputs exist; --replace-existing required")
    phase = root / "Phase4_脳波解析"
    # All analyses can be regenerated sequentially without treating a sibling's
    # authorized new sensitivity files as changes to protected primary results.
    batch_allowed = set()
    for batch_key, groups in documented_exclusions().items():
        batch_stem = ANALYSES[batch_key][0]
        batch_allowed.update(support_paths(root, batch_stem).values())
        for product, pairs in groups.items():
            if pairs:
                batch_allowed.update(output_paths(root, batch_stem, product).values())
    before = inventory(phase, batch_allowed)
    record = {"status": "running", "version": VERSION, "analysis_stem": stem,
              "focus_channel": engine.FOCUS_CHANNEL,
              "frequencies_hz": engine.no1.INCLUDED_FREQUENCIES_HZ.tolist(),
              "started_at": datetime.now(TOKYO).isoformat(), "source_audit": audit,
              "manifest": str(manifest), "source_cache": source, "baseline_preflight": baseline,
              "selection_csv": str(support["selection"]), "protected_before": before,
              "protected_exceptions": sorted(str(p) for p in batch_allowed),
              "reason": REASON, "scope": "Grand-average/Set/AllSets; both conditions/all Sets",
              "topography_modified": False, "plots": [], "outputs": {},
              "canonical_selection_sha256": digest(ATTENTION),
              "axis_scope": "Shared among products generated in this additional analysis only",
              "cloud_sync": "Local authorized OneDrive save/readback; server sync not verified"}
    record["implementation_base_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    record["code_hashes"] = {
        str(path.relative_to(REPO)): digest(path) for path in (
            Path(__file__).resolve(), SCRIPTS / "Phase4_No1_FmTheta.py",
            SCRIPTS / "Phase4_No1_sub_FmThetaChange.py",
            SCRIPTS / ANALYSES[key][2], SCRIPTS / "phase4_band_variant_config.py",
            SCRIPTS.parent / "paired_statistics.py",
        )
    }
    write_json(support["record"], record)
    try:
        grands = {p: engine.build_grand_average(v, p)[0] for p, v in selected.items()}
        limit, ticks = engine.grand_average_axis(list(grands.values()))
        pngs = {p for p in allowed if p.suffix == ".png"}
        with capture_plots(record["plots"], pngs):
            for product, cohort in selected.items():
                paths = paths_by_product[product]
                for path in paths.values():
                    path.parent.mkdir(parents=True, exist_ok=True)
                grand = grands[product]
                engine.plot_grand_average(grand, product, paths["grand_png"],
                                          common_limit=limit, common_ticks=ticks)
                values = engine.build_quantification(cohort, product)
                set_stats, all_stats = engine.quantification_statistics(values)
                engine.plot_quantification(values, set_stats, product, paths["set_png"])
                engine.plot_overall_quantification(values, all_stats, product, paths["all_png"])
                for name, table in (("grand_csv", grand), ("values", values),
                                    ("set_stats", set_stats), ("all_stats", all_stats)):
                    table.to_csv(paths[name], index=False)
                    if len(pd.read_csv(paths[name])) != len(table):
                        raise RuntimeError(f"CSV readback mismatch: {paths[name]}")
                cols = ["EyeDrop_PSDChange_pct", "Control_PSDChange_pct"]
                record["outputs"][product] = {
                    "paths": {k: str(p) for k, p in paths.items()},
                    "excluded_pair_ids": sorted(exclusions[product]),
                    "retained_pair_ids": [i["spec"].pair_id for i in cohort],
                    "paired_n": {str(n): int(np.isfinite(
                        values.loc[values["Set"] == n, cols].to_numpy(float)
                    ).all(axis=1).sum()) for n in [1, 2, 3, 4, 5, 6, "All Sets"]},
                    "grand_y_limit": float(limit), "grand_y_ticks": ticks.tolist(),
                    "shade_points_outside_axes": {
                        condition: int((
                            (grand[f"{condition}_Mean_PSDChange_pct"]
                             + grand[f"{condition}_SEM_PSDChange_pct"] > limit)
                            | (grand[f"{condition}_Mean_PSDChange_pct"]
                               - grand[f"{condition}_SEM_PSDChange_pct"] < -limit)
                        ).sum()) for condition in ("EyeDrop", "Control")
                    },
                }
        selection.to_csv(support["selection"], index=False)
        if inventory(phase, batch_allowed) != before:
            raise RuntimeError("Protected outputs changed")
        if any(digest(Path(row["path"])) != row["sha256"] for row in source):
            raise RuntimeError("Source cache changed")
        if {Path(row["path"]) for row in record["plots"]} != pngs:
            raise RuntimeError("Expected PNGs missing")
        record.update(status="generated_pending_independent_and_visual_verification",
                      protected_unchanged=True, completed_at=datetime.now(TOKYO).isoformat(),
                      output_files=[{"path": str(p), "sha256": digest(p)}
                                    for p in sorted(allowed - {support["record"]})])
    except Exception as error:
        record.update(status="failed", error=repr(error))
        write_json(support["record"], record)
        raise
    write_json(support["record"], record)
    return record


def legacy_paths(key: str, root: Path) -> list[Path]:
    """Enumerate only the old No2 extra cohort, never primary or topology paths."""
    if key not in {"no2", "no2-pz"}:
        return []
    stem = ANALYSES[key][0]
    base = root / "Phase4_脳波解析" / stem
    candidates = []
    for relative in ("VRohtoPremium/GrandAverage", "VRohtoPremium/SetQuantification",
                     "Sub/tables/GrandAverage", "Sub/tables/SetQuantification"):
        candidates.extend(p for p in (base / relative).rglob(f"{stem}_*ExcludePair*.csv"))
        candidates.extend(p for p in (base / relative).rglob(f"{stem}_*ExcludePair*.png"))
    return sorted(candidates)


def retire_legacy(key: str, review_path: Path) -> dict:
    """Require explicit verified review before retiring old additional artifacts."""
    engine = build_engine(key)
    root, stem = engine.DEFAULT_OUTPUT_ROOT, engine.ANALYSIS_STEM
    support = support_paths(root, stem)
    record = json.loads(support["record"].read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("status") != "passed" or review.get("analysis_stem") != stem:
        raise ValueError("Passed analysis-specific independent/visual review required")
    expected_png = {row["path"]: row["sha256"] for row in record["plots"]}
    if review.get("reviewed_png_sha256") != expected_png:
        raise ValueError("Review must name every current PNG and exact hash")
    if not review.get("independent_validation_passed"):
        raise ValueError("Independent numerical validation must pass first")
    for row in record["output_files"]:
        if digest(Path(row["path"])) != row["sha256"]:
            raise ValueError("Output changed after generation")
    retired = []
    base = root / "Phase4_脳波解析" / stem
    for old in legacy_paths(key, root):
        fingerprint = digest(old)
        if old.suffix == ".png":
            old.unlink()
            destination = None
        else:
            destination = base / "Sub/history/BeforeSpecifiedPairsExcluded_20261116"
            destination /= old.relative_to(base)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and digest(destination) != fingerprint:
                raise RuntimeError("Different historical artifact already exists")
            shutil.move(str(old), str(destination))
        retired.append({"old": str(old), "sha256": fingerprint,
                        "archived_to": str(destination) if destination else None})
    record["legacy_retirement"] = {"review": str(review_path), "files": retired,
                                   "at": datetime.now(TOKYO).isoformat()}
    write_json(support["record"], record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", choices=[*ANALYSES, "all"], default="all")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source-audit", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--replace-existing", action="store_true")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--retire-legacy", action="store_true")
    args = parser.parse_args()
    actual_root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=REPO, text=True
    ).strip()
    origin = subprocess.check_output(
        ["git", "remote", "get-url", "origin"], cwd=REPO, text=True
    ).strip()
    if actual_root != str(REPO) or origin != ORIGIN:
        raise RuntimeError("Repository boundary mismatch")
    if args.retire_legacy:
        if args.analysis == "all" or not args.review:
            parser.error("Legacy retirement needs one --analysis and --review")
        results = [retire_legacy(args.analysis, args.review)]
    else:
        if not args.manifest or not args.source_audit:
            parser.error("--manifest and --source-audit are required")
        exclusions = documented_exclusions()
        audit = verify_source_audit(args.source_audit, args.manifest, exclusions)
        keys = list(ANALYSES) if args.analysis == "all" else [args.analysis]
        results = [execute_analysis(key, args.manifest, audit, exclusions[key],
                                    preflight_only=args.preflight_only,
                                    replace=args.replace_existing) for key in keys]
    print(json.dumps([{k: row[k] for k in ("analysis_stem", "status")}
                      for row in results], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
