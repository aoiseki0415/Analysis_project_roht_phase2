"""No10-only cache provenance checks, including figure-only reruns.

These checks do not alter the PSD, masks, averaging or rendering algorithms.
The original No1–9 engines remain unchanged on disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType
from typing import Any

import h5py
import numpy as np


def install_cache_guard(engine: ModuleType) -> None:
    original_validate = engine.validate_cache
    original_load_pair = engine.load_pair_item
    original_validate_specs = engine.validate_participant_specs
    session_metadata: dict[str, dict[str, Any]] = {}

    def validate_specs(specs: list[Any], *, production_batch: bool = False) -> None:
        original_validate_specs(specs, production_batch=production_batch)
        session_metadata.clear()
        for spec in specs:
            for order, sid in enumerate((spec.first_session_id, spec.second_session_id), 1):
                session_metadata[sid] = {
                    "pair_id": spec.pair_id,
                    "session_order": order,
                    "condition": "Eye Drop" if sid == spec.drops_session_id else "Control",
                    "product": engine.normalize_product(spec.product)[0],
                }

    def validate_cache(path: Path, expected_hash: str | None = None) -> dict[str, Any]:
        with h5py.File(path, "r") as handle:
            sid = str(handle.attrs.get("participant_id"))
            if session_metadata and sid not in session_metadata:
                raise ValueError(f"{path}: session absent from the current manifest")
            for key, value in session_metadata.get(sid, {}).items():
                if handle.attrs.get(key) != value:
                    raise ValueError(f"{path}: manifest/cache {key} mismatch")
            frequencies = json.loads(handle.attrs["included_frequencies_hz"])
            if not np.array_equal(frequencies, engine.INCLUDED_FREQUENCIES_HZ):
                raise ValueError(f"{path}: No10 cache frequency band mismatch")
            fingerprints = json.loads(handle.attrs["input_fingerprints_json"])
            for source in fingerprints:
                stat = Path(source["path"]).stat()
                if (stat.st_size, stat.st_mtime_ns) != (source["size"], source["mtime_ns"]):
                    raise ValueError(f"{path}: Phase 1 source changed; stale No10 cache")
            recomputed_hash = engine.configuration_hash(fingerprints)
            if handle.attrs.get("configuration_hash") != recomputed_hash:
                raise ValueError(f"{path}: No10 configuration hash mismatch")
        return original_validate(path, expected_hash or recomputed_hash)

    def load_pair_item(spec: Any, cache_root: Path) -> dict[str, Any]:
        for order, session_id in enumerate((spec.first_session_id, spec.second_session_id), 1):
            path = engine.cache_path(cache_root, spec, session_id)
            with h5py.File(path, "r") as handle:
                expected = {
                    "participant_id": session_id,
                    "pair_id": spec.pair_id,
                    "session_order": order,
                    "condition": "Eye Drop" if session_id == spec.drops_session_id else "Control",
                    "product": engine.normalize_product(spec.product)[0],
                }
                for key, value in expected.items():
                    if handle.attrs.get(key) != value:
                        raise ValueError(f"{path}: manifest/cache {key} mismatch")
        return original_load_pair(spec, cache_root)

    engine.validate_cache = validate_cache
    engine.load_pair_item = load_pair_item
    engine.validate_participant_specs = validate_specs
