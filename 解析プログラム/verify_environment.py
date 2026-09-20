"""Verify that the project's numerical-analysis and EEG stack is usable."""

from __future__ import annotations

import json
import os
import platform
from importlib import metadata

os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")

import mne
import numpy as np
import pandas as pd
from mne.preprocessing import ICA
from mne_icalabel import label_components
from scipy import stats

PACKAGES = (
    "autoreject",
    "ipykernel",
    "jupyterlab",
    "matplotlib",
    "mne",
    "mne-icalabel",
    "numpy",
    "onnxruntime",
    "openpyxl",
    "pandas",
    "pyarrow",
    "python-picard",
    "scikit-learn",
    "scipy",
    "seaborn",
    "statsmodels",
)


def verify_numerical_stack() -> None:
    """Run small deterministic calculations through NumPy, pandas, and SciPy."""
    values = np.array([1.0, 2.0, 3.0, 4.0])
    frame = pd.DataFrame({"value": values})
    assert np.isclose(frame["value"].mean(), 2.5)
    assert np.isclose(stats.zscore(values).mean(), 0.0)


def verify_mne_ica() -> dict[str, object]:
    """Fit ICA and run ICLabel on synthetic continuous EEG without writing output."""
    assert callable(mne.io.read_raw_eeglab)
    rng = np.random.default_rng(20260920)
    sampling_rate = 256.0
    n_samples = 7_680
    times = np.arange(n_samples) / sampling_rate
    channel_names = [
        "Fp1",
        "Fp2",
        "F7",
        "F3",
        "Fz",
        "F4",
        "F8",
        "T7",
        "C3",
        "Cz",
        "C4",
        "T8",
        "P7",
        "P3",
        "Pz",
        "P4",
        "P8",
        "O1",
        "O2",
    ]

    sources = rng.standard_normal((len(channel_names), n_samples))
    sources[0] += np.sin(2 * np.pi * 10 * times)
    sources[1] += 0.6 * np.sin(2 * np.pi * 6 * times)
    blink = np.zeros(n_samples)
    blink[(times > 5.0) & (times < 5.25)] = 8.0
    blink[(times > 12.0) & (times < 12.25)] = 8.0
    sources[2] += blink
    mixing = rng.normal(size=(len(channel_names), len(channel_names)))
    data = mixing @ sources

    info = mne.create_info(channel_names, sampling_rate, ch_types="eeg")
    raw = mne.io.RawArray(data * 1e-6, info, verbose=False)
    raw.set_montage("colin27_1020")
    raw.set_eeg_reference("average", projection=False, verbose=False)
    raw.filter(1.0, 100.0, verbose=False)

    ica = ICA(n_components=15, method="infomax", fit_params={"extended": True}, max_iter=500)
    ica.fit(raw, verbose=False)
    assert ica.n_components_ == 15

    labels = label_components(raw, ica, method="iclabel")
    assert len(labels["labels"]) == 15
    assert len(labels["y_pred_proba"]) == 15
    return {"components": 15, "labels": sorted(set(labels["labels"]))}


def package_versions() -> dict[str, str]:
    """Return resolved versions for the principal environment components."""
    return {name: metadata.version(name) for name in PACKAGES}


def main() -> None:
    verify_numerical_stack()
    iclabel = verify_mne_ica()
    report = {
        "status": "ok",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": package_versions(),
        "checks": [
            "numerical_stack",
            "mne_continuous_eeg",
            "mne_eeglab_reader",
            "mne_extended_infomax_ica",
            "mne_iclabel",
        ],
        "iclabel": iclabel,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
