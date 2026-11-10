from __future__ import annotations

import colorsys
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

import phase4_iaf_figures as module  # noqa: E402


def _inputs(number: int = 8, product: str = "VRohtoPremium") -> dict:
    frequency = np.arange(10, 401) / 10
    count = 6
    psd = np.stack([
        3 / frequency + (index + 2) * np.exp(-((frequency - 10) / 0.8) ** 2)
        for index in range(count)
    ])
    return {
        "analysis_number": number, "product": product, "frequencies_hz": frequency,
        "drops_psd": psd, "control_psd": psd * 2,
        "drops_iaf_hz": np.full(count, 10.0), "control_iaf_hz": np.full(count, 10.1),
    }


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("number", [8, 9])
def test_panel_design_and_independent_eighty_percent_y_scales(number: int) -> None:
    data = _inputs(number)
    # Maximum is deliberately outside alpha; the entire displayed 1–30 Hz matters.
    data["drops_psd"][0, 0] = 100
    data["control_psd"][1, 200] = 250
    # A large saved but undisplayed frequency must not affect the axes.
    data["drops_psd"][0, -1] = 1e6
    fig = module.build_three_panel_figure(**data)
    count = len(data["drops_iaf_hz"])
    assert len(fig.axes) == 3
    assert fig.get_size_inches().tolist() == [27, 10]
    assert fig.dpi == 180
    for ax, top in zip(fig.axes[:2], [125, 312.5], strict=True):
        assert ax.get_ylim() == (0, top)
        assert ax.get_xlim() == (1, 30)
        assert ax.get_xticks().tolist() == [1, 5, 10, 15, 20, 25, 30]
        assert 3 <= len(ax.get_yticks()) <= 6
        assert all(0 <= value <= top for value in ax.get_yticks())
        assert ax.get_xlabel() == "Frequency (Hz)"
        assert ax.get_ylabel() == "PSD (µV²/Hz)"
        assert len(ax.lines) == count + 2
        assert ax.lines[0].get_linewidth() == 2.5
        assert ax.lines[0].get_alpha() == 1
        assert [line.get_xdata()[0] for line in ax.lines[-2:]] == [8, 15]
        assert all(line.get_linestyle() == ":" for line in ax.lines[-2:])
        assert ax.get_legend().get_frame_on() is False
    iaf = fig.axes[2]
    assert iaf.get_ylim() == (7.5, 15.5)
    assert iaf.get_xlim() == (0.75, count + 0.25)
    assert iaf.get_yticks().tolist() == list(range(8, 16))
    assert iaf.get_xlabel() == "Set"
    assert iaf.get_ylabel() == "IAF (Hz)"
    expected_ch = "Pz" if number == 8 else "Fz"
    assert iaf.get_title() == f"{expected_ch} — Alpha Peak Frequency"
    assert [line.get_color() for line in iaf.lines] == [
        module.FIGURE_CONFIG["eye_drop_colors"][number]["VRohtoPremium"], "#402B5D"
    ]
    for line in iaf.lines:
        assert line.get_linewidth() == 3
        assert line.get_markersize() == 10
        assert line.get_markeredgewidth() == 1
        assert line.get_markeredgecolor() == "white"
    for ax in fig.axes:
        assert ax.get_box_aspect() == 1
        assert not ax.spines["top"].get_visible()
        assert not ax.spines["right"].get_visible()
        assert ax.xaxis.label.get_fontsize() == 28
        assert ax.yaxis.label.get_fontsize() == 28
        assert ax.title.get_fontsize() == 26
        assert all(t.get_fontsize() == 20 for t in ax.get_xticklabels() + ax.get_yticklabels())
    for text in fig.findobj(Text):
        assert text.get_fontfamily() == ["Arial"]
    assert fig.subplotpars.left == 0.052
    assert fig.subplotpars.right == 0.985
    assert fig.subplotpars.bottom == 0.19
    assert fig.subplotpars.top == 0.88
    assert fig.subplotpars.wspace == 0.30
    assert fig._suptitle is None


@pytest.mark.parametrize("count", [6])
def test_hls_gradient_has_fixed_bright_to_dark_order(count: int) -> None:
    palette = module.segment_colors("#5689CF", count)
    hue_light_sat = np.array([colorsys.rgb_to_hls(*rgb) for rgb in palette])
    np.testing.assert_allclose(hue_light_sat[:, 1], np.linspace(0.80, 0.22, count))
    np.testing.assert_allclose(hue_light_sat[:, 0], hue_light_sat[0, 0])
    np.testing.assert_allclose(hue_light_sat[:, 2], hue_light_sat[0, 2])


def test_setwise_fz_legend_order_missing_rows_and_no_nan_bridge() -> None:
    data = _inputs(9)
    data["drops_psd"][2] = np.nan
    data["drops_iaf_hz"][2] = np.nan
    original_psd = data["drops_psd"].copy()
    fig = module.build_three_panel_figure(**data)
    labels = [text.get_text() for text in fig.axes[0].get_legend().get_texts()]
    assert labels == [
        "Set 1", "Set 2", "Set 3 unavailable", "Set 4", "Set 5", "Set 6",
    ]
    assert fig.axes[0].get_legend()._ncols == 1
    assert len(fig.axes[0].lines[2].get_xdata()) == 291
    assert np.isnan(fig.axes[0].lines[2].get_ydata()).all()
    assert np.isfinite(fig.axes[1].lines[2].get_ydata()).all()
    np.testing.assert_allclose(data["drops_psd"], original_psd, equal_nan=True)
    np.testing.assert_allclose(fig.axes[2].lines[0].get_ydata(), data["drops_iaf_hz"])
    # Matplotlib restarts the connected path after the missing point.
    path_segments = list(fig.axes[2].lines[0].get_path().iter_segments(remove_nans=True))
    assert sum(code == MplPath.MOVETO for _, code in path_segments) == 2
    assert [text.get_text() for text in fig.axes[2].get_xticklabels()] == [
        str(number) for number in range(1, 7)
    ]
    assert len(fig.texts) == 0


def test_empty_and_zero_psd_remain_distinguished_without_imputation() -> None:
    data = _inputs()
    data["drops_psd"][:] = np.nan
    data["drops_iaf_hz"][:] = np.nan
    data["control_psd"][:] = 0
    data["control_iaf_hz"][:] = np.nan
    fig = module.build_three_panel_figure(**data)
    assert fig.axes[0].get_ylim() == (0, 1)
    assert fig.axes[1].get_ylim() == (0, 1)
    assert fig.axes[0].texts[0].get_text() == "No usable PSD"
    assert fig.axes[1].texts[0].get_text() == "Zero PSD"
    assert all("unavailable" in text.get_text() for text in fig.axes[0].get_legend().get_texts())
    assert not any(
        "unavailable" in text.get_text() for text in fig.axes[1].get_legend().get_texts()
    )
    assert np.isnan(fig.axes[2].lines[0].get_ydata()).all()


@pytest.mark.parametrize("number", [8, 9])
def test_save_real_pixel_dimensions_and_close(tmp_path: Path, number: int) -> None:
    filename = tmp_path / f"synthetic_no{number}.png"
    figures_before = plt.get_fignums()
    with matplotlib.rc_context({"savefig.bbox": "tight"}):
        result = module.plot_pair_three_panel(output_path=filename, **_inputs(number))
    assert plt.get_fignums() == figures_before
    assert result["dimensions_px"] == [4860, 1800]
    assert result["interval_count"] == 6
    assert result["psd_input_dataset"] == "smoothed_mean_psd_uv2_hz"
    assert result["plotting_applies_smoothing"] is False
    with Image.open(filename) as image:
        image.load()
        assert image.size == (4860, 1800)
        assert image.getpixel((0, 0))[:3] == (255, 255, 255)


def test_renderer_uses_supplied_smoothed_psd_without_a_second_smoothing() -> None:
    data = _inputs()
    # A deliberately sharp feature would change if the renderer smoothed again.
    # Whether it is a real valid smoothed spectrum is the engine's contract;
    # rendering must copy the supplied values, not reinterpret them.
    data["drops_psd"][:] = 0
    data["control_psd"][:] = 0
    data["drops_psd"][0, 91] = 8
    data["control_psd"][0, 91] = 16
    before = {key: data[key].copy() for key in ("drops_psd", "control_psd")}
    fig = module.build_three_panel_figure(**data)
    for axis, key, top in zip(fig.axes[:2], before, [10, 20], strict=True):
        for index, line in enumerate(axis.lines[:6]):
            np.testing.assert_array_equal(line.get_ydata(), before[key][index, :291])
        assert axis.get_ylim() == (0, top)
        np.testing.assert_array_equal(data[key], before[key])


@pytest.mark.parametrize("number", [8, 9])
def test_engine_render_passes_only_smoothed_rows_to_plotter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, number: int
) -> None:
    import phase4_iaf as engine

    spec = engine.ParticipantSpec("901", "902", "902", "VRohtoPremium")
    count = 6
    rows = []
    for condition in ("Eye Drop", "Control"):
        for position in range(count):
            rows.append({
                "pair_id": spec.pair_id,
                "condition": condition,
                "position": position,
                "frequency_hz": 9 + position / 10,
                # Make accidental raw-data usage conspicuous in both values/limits.
                "mean_psd": np.full(391, 1000 + position),
                "smoothed_mean_psd": np.full(391, 2 + position),
            })
    calls = []

    def capture_plot(**kwargs):
        calls.append(kwargs)
        figure_args = {key: value for key, value in kwargs.items() if key != "output_path"}
        figure = module.build_three_panel_figure(**figure_args)
        for ax in figure.axes[:2]:
            assert ax.get_ylim() == (0, (count + 1) / 0.80)
            for index, line in enumerate(ax.lines[:count]):
                np.testing.assert_array_equal(line.get_ydata(), np.full(291, 2 + index))
        return {"psd_input_dataset": "smoothed_mean_psd_uv2_hz"}

    monkeypatch.setattr(module, "plot_pair_three_panel", capture_plot)
    monkeypatch.setattr(engine, "sha256_file", lambda path: "synthetic-render-hash")
    result = engine.render_analysis(rows, [spec], tmp_path, number)
    assert len(calls) == len(result) == 1
    assert calls[0]["output_path"].parent == tmp_path / "VRohtoPremium" / "Individual"
    for prefix in ("drops", "control"):
        np.testing.assert_array_equal(
            calls[0][f"{prefix}_psd"], np.stack([np.full(391, 2 + i) for i in range(count)])
        )
        np.testing.assert_array_equal(
            calls[0][f"{prefix}_iaf_hz"], 9 + np.arange(count) / 10
        )


def test_engine_render_rejects_raw_only_rows_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import phase4_iaf as engine

    spec = engine.ParticipantSpec("901", "902", "902", "VRohtoPremium")
    rows = [
        {
            "pair_id": spec.pair_id, "condition": condition, "position": position,
            "frequency_hz": 10.0, "mean_psd": np.ones(391),
        }
        for condition in ("Eye Drop", "Control") for position in range(6)
    ]

    def forbidden_plot(**kwargs):
        pytest.fail("Old raw-only rows must never reach the current figure renderer")

    monkeypatch.setattr(module, "plot_pair_three_panel", forbidden_plot)
    with pytest.raises(KeyError, match="smoothed_mean_psd"):
        engine.render_analysis(rows, [spec], tmp_path, 8)


def test_missing_arial_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_findfont(*args, **kwargs):
        assert kwargs["fallback_to_default"] is False
        raise ValueError("Arial not installed")

    monkeypatch.setattr(module.font_manager, "findfont", fail_findfont)
    with pytest.raises(ValueError, match="Arial not installed"):
        module.build_three_panel_figure(**_inputs())


def test_invalid_shapes_or_infinite_values_fail_before_rendering() -> None:
    data = _inputs()
    data["drops_iaf_hz"] = np.full(12, 10.0)
    with pytest.raises(ValueError, match="Expected PSD shape"):
        module.build_three_panel_figure(**data)
    data = _inputs()
    data["control_psd"][0, 0] = np.inf
    with pytest.raises(ValueError, match="Infinite"):
        module.build_three_panel_figure(**data)


@pytest.mark.parametrize("top", [0.00037, 0.9, 1.1, 4.3, 30, 103, 9801])
def test_psd_y_ticks_within_limits_are_nice_and_three_to_six(top: float) -> None:
    ticks = module._psd_y_ticks(top)
    assert 3 <= len(ticks) <= 6
    assert ticks[0] == 0
    assert ticks[-1] <= top
    np.testing.assert_allclose(np.diff(ticks), np.diff(ticks)[0])


@pytest.mark.parametrize("maximum", [1e-9, 1e-4, 1e4, 1e5, 1e9, 1e12])
def test_extreme_psd_scientific_ticks_keep_labels_on_canvas(maximum: float) -> None:
    data = _inputs(9)
    data["drops_psd"][:] = maximum
    data["control_psd"][:] = maximum * 2
    fig = module.build_three_panel_figure(**data)
    renderer = fig.canvas.get_renderer()
    for index, ax in enumerate(fig.axes[:2]):
        assert ax.get_yscale() == "linear"
        assert ax.get_ylim()[1] == pytest.approx(maximum * (index + 1) / 0.80)
        assert ax.yaxis.get_offset_text().get_text().startswith("1e")
        assert ax.yaxis.get_offset_text().get_fontfamily() == ["Arial"]
        for label in [ax.yaxis.label, ax.yaxis.get_offset_text(), *ax.get_yticklabels()]:
            bounds = label.get_window_extent(renderer)
            assert bounds.x0 >= 0
            assert bounds.y0 >= 0
            assert bounds.x1 <= fig.bbox.width
            assert bounds.y1 <= fig.bbox.height
        if index:
            assert not ax.yaxis.label.get_window_extent(renderer).overlaps(
                fig.axes[index - 1].get_window_extent(renderer)
            )


def test_new_no9_preserves_former_fz_setwise_palette() -> None:
    assert module.FIGURE_CONFIG["eye_drop_colors"] == {
        8: {"CCube": "#2456A6", "VRohtoPremium": "#5689CF"},
        9: {"CCube": "#A63D46", "VRohtoPremium": "#CF7278"},
    }


@pytest.mark.parametrize("number", [10, 11])
def test_retired_analysis_numbers_rejected(number: int) -> None:
    with pytest.raises(ValueError, match="Only current"):
        module.build_three_panel_figure(**_inputs(number))


def test_retired_halfset_gradient_rejected() -> None:
    with pytest.raises(ValueError, match="6 whole-Set"):
        module.segment_colors("#5689CF", 12)
