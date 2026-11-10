from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.path import Path as MplPath
from matplotlib.text import Text
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "解析プログラム" / "Phase4_脳波解析"
sys.path.insert(0, str(SCRIPT_DIR))

import phase4_iaf_figures as individual  # noqa: E402
import phase4_iaf_grand_average_figures as module  # noqa: E402


def _inputs(number: int = 8, product: str = "VRohtoPremium") -> dict:
    count = 12 if number in (9, 11) else 6
    return {
        "analysis_number": number, "product": product, "cohort": "AllAvailable",
        "drops_mean_hz": np.linspace(0, 1, count),
        "drops_sem_hz": np.linspace(0, 0.2, count),
        "control_mean_hz": np.linspace(0, -0.6, count),
        "control_sem_hz": np.linspace(0, 0.3, count),
        "y_limit_hz": 1.5,
    }


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("number", [8, 9, 10, 11])
@pytest.mark.parametrize("product", ["CCube", "VRohtoPremium"])
def test_design_matches_individual_right_panel_and_palette(number: int, product: str) -> None:
    data = _inputs(number, product)
    fig = module.build_grand_average_figure(**data)
    assert len(fig.axes) == 1
    assert fig.get_size_inches().tolist() == [10, 10]
    assert fig.dpi == 180
    ax = fig.axes[0]
    assert ax.get_box_aspect() == 1
    assert ax.get_ylim() == (-1.5, 1.5)
    count = len(data["drops_mean_hz"])
    assert ax.get_xlim() == (0.75, count + 0.25)
    assert ax.get_xticks().tolist() == list(range(1, count + 1))
    assert ax.get_xlabel() == ("Set / Half" if count == 12 else "Set")
    assert ax.get_ylabel() == "IAF Change (Hz)"
    assert len(ax.lines) == 2
    assert [line.get_color() for line in ax.lines] == [
        individual.FIGURE_CONFIG["eye_drop_colors"][number][product], "#402B5D"
    ]
    assert len(ax.collections) == 2
    assert all(shade.get_alpha() == 0.18 for shade in ax.collections)
    for line in ax.lines:
        assert line.get_linewidth() == 3
        assert line.get_markersize() == 10
        assert line.get_markeredgewidth() == 1
        assert line.get_markeredgecolor() == "white"
    assert all(text.get_fontsize() == 17 for text in ax.get_legend().get_texts())
    assert [text.get_text() for text in ax.get_legend().get_texts()] == [
        f"Eye Drop ({module.PRODUCT_LABELS[product]})", "Control"
    ]
    assert not ax.get_legend().get_frame_on()
    assert not ax.spines["top"].get_visible()
    assert not ax.spines["right"].get_visible()
    assert ax.xaxis.label.get_fontsize() == 28
    assert ax.yaxis.label.get_fontsize() == 28
    assert ax.title.get_fontsize() == 26
    assert all(text.get_fontsize() == 20 for text in ax.get_xticklabels() + ax.get_yticklabels())
    assert 3 <= len(ax.get_yticks()) <= 6
    np.testing.assert_allclose(ax.get_yticks(), -ax.get_yticks()[::-1])
    assert "Pz" in ax.get_title() if number < 10 else "Fz" in ax.get_title()
    assert "All available participants" in ax.get_title()
    assert module.PRODUCT_LABELS[product] in ax.get_title()
    assert "N=" not in ax.get_title()
    for text in fig.findobj(Text):
        assert text.get_fontfamily() == ["Arial"]


def test_half_set_labels_and_note_are_explicit() -> None:
    fig = module.build_grand_average_figure(**_inputs(9))
    assert [text.get_text() for text in fig.axes[0].get_xticklabels()] == [
        f"{number}{half}" for number in range(1, 7) for half in ("a", "b")
    ]
    assert len(fig.texts) == 1
    assert fig.texts[0].get_text() == (
        "a: first half (0–50%)  |  b: second half (50–100%)"
    )
    assert fig.texts[0].get_position() == (0.5, 0.035)
    assert fig.texts[0].get_fontsize() == 17


def test_shared_limit_uses_both_signs_conditions_and_cohorts() -> None:
    data = [
        (np.array([0.0, 1.0]), np.array([0.0, 0.2])),
        (np.array([0.0, -2.0]), np.array([0.0, 0.4])),
        (np.array([0.0, 0.3]), np.array([0.0, 0.2])),
        (np.array([0.0, -0.6]), np.array([0.0, 0.3])),
    ]
    assert module.shared_y_limit(data) == pytest.approx(3.0)
    for cohort in module.COHORT_LABELS:
        inputs = _inputs()
        inputs.update(cohort=cohort, y_limit_hz=module.shared_y_limit(data))
        limits = module.build_grand_average_figure(**inputs).axes[0].get_ylim()
        assert limits == pytest.approx((-3, 3))


def test_no_smoothing_imputation_or_bridging_nans_and_inputs_unchanged() -> None:
    data = _inputs()
    data["drops_mean_hz"][:] = [0, 0.1, np.nan, 0.9, -0.4, 0.6]
    data["control_mean_hz"][:] = [0, -0.3, np.nan, 0.4, 0.7, -0.2]
    for key in ("drops_sem_hz", "control_sem_hz"):
        data[key][2] = np.nan
    saved = {key: value.copy() for key, value in data.items() if isinstance(value, np.ndarray)}
    fig = module.build_grand_average_figure(**data)
    for line, key in zip(
        fig.axes[0].lines, ["drops_mean_hz", "control_mean_hz"], strict=True
    ):
        np.testing.assert_array_equal(line.get_ydata(), saved[key])
        segments = list(line.get_path().iter_segments(remove_nans=True))
        assert sum(code == MplPath.MOVETO for _, code in segments) == 2
    for key, value in saved.items():
        np.testing.assert_array_equal(data[key], value)
    # Both SEM polygons also break at the missing interval.
    assert all(len(collection.get_paths()) == 2 for collection in fig.axes[0].collections)


def test_undefined_sem_keeps_finite_line_without_false_shade() -> None:
    data = _inputs()
    data["drops_sem_hz"][:] = np.nan
    data["control_sem_hz"][:] = np.nan
    assert module.shared_y_limit([
        (data["drops_mean_hz"], data["drops_sem_hz"]),
        (data["control_mean_hz"], data["control_sem_hz"]),
    ]) == pytest.approx(1.25)
    fig = module.build_grand_average_figure(**data)
    assert all(np.isfinite(line.get_ydata()).all() for line in fig.axes[0].lines)
    assert all(len(collection.get_paths()) == 0 for collection in fig.axes[0].collections)


@pytest.mark.parametrize("missing", [False, True])
def test_zero_or_no_data_has_safe_fallback_without_fabricated_values(missing: bool) -> None:
    data = _inputs()
    for key in ("drops_mean_hz", "control_mean_hz", "drops_sem_hz", "control_sem_hz"):
        data[key][:] = np.nan if missing else 0.0
    limit = module.shared_y_limit([
        (data["drops_mean_hz"], data["drops_sem_hz"]),
        (data["control_mean_hz"], data["control_sem_hz"]),
    ])
    assert limit == 1
    data["y_limit_hz"] = limit
    ax = module.build_grand_average_figure(**data).axes[0]
    assert ax.get_ylim() == (-1, 1)
    assert len(ax.texts) == int(missing)
    if missing:
        assert np.isnan(ax.lines[0].get_ydata()).all()


@pytest.mark.parametrize("limit", [0.0003, 0.028, 0.133, 0.333, 0.99, 1, 2.9, 8.75, 100])
def test_symmetric_nice_ticks(limit: float) -> None:
    ticks = module._symmetric_ticks(limit)
    assert 3 <= len(ticks) <= 6
    assert (np.abs(ticks) <= limit).all()
    np.testing.assert_allclose(ticks, -ticks[::-1])
    np.testing.assert_allclose(np.diff(ticks), np.diff(ticks)[0])


@pytest.mark.parametrize("number", [8, 9])
def test_save_readback_exact_square_canvas_and_close(tmp_path: Path, number: int) -> None:
    path = tmp_path / f"synthetic_no{number}.png"
    before = plt.get_fignums()
    with matplotlib.rc_context({"savefig.bbox": "tight"}):
        result = module.plot_grand_average(output_path=path, **_inputs(number))
    assert plt.get_fignums() == before
    assert result["dimensions_px"] == [1800, 1800]
    assert result["y_limits_hz"] == [-1.5, 1.5]
    assert result["plotting_applies_smoothing"] is False
    assert result["plotting_applies_interpolation"] is False
    assert result["font_file"].endswith("Arial.ttf")
    with Image.open(path) as image:
        image.load()
        assert image.size == (1800, 1800)
        assert image.getpixel((0, 0))[:3] == (255, 255, 255)


@pytest.mark.parametrize("change", [
    {"analysis_number": 12}, {"product": "unknown"}, {"cohort": "unknown"},
    {"y_limit_hz": 0}, {"y_limit_hz": np.nan}, {"y_limit_hz": 0.1},
    {"drops_mean_hz": [0, 1]},
    {"drops_sem_hz": [0, -1, 0, 0, 0, 0]},
    {"drops_mean_hz": [0, np.inf, 0, 0, 0, 0]},
    {"drops_mean_hz": [0, np.nan, 0, 0, 0, 0]},
])
def test_reject_malformed_or_clipped_inputs(change: dict) -> None:
    inputs = _inputs()
    inputs.update(change)
    with pytest.raises(ValueError):
        module.build_grand_average_figure(**inputs)


def test_reject_unpaired_availability_even_if_sem_also_missing() -> None:
    inputs = _inputs()
    inputs["drops_mean_hz"][1] = np.nan
    inputs["drops_sem_hz"][1] = np.nan
    with pytest.raises(ValueError, match="paired interval availability"):
        module.build_grand_average_figure(**inputs)


def test_reject_non_png_target(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="PNG"):
        module.plot_grand_average(output_path=tmp_path / "bad.pdf", **_inputs())
