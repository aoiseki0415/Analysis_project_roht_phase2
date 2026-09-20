"""Smoke tests for the reproducible project environment."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / "解析プログラム" / "verify_environment.py"
SPEC = importlib.util.spec_from_file_location("verify_environment", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFY_ENVIRONMENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY_ENVIRONMENT)


def test_numerical_stack() -> None:
    VERIFY_ENVIRONMENT.verify_numerical_stack()


def test_mne_ica() -> None:
    VERIFY_ENVIRONMENT.verify_mne_ica()
