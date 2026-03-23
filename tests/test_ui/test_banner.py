"""Tests for lmcode.ui.banner — startup banner rendering."""

from __future__ import annotations

from rich.text import Text

from lmcode.ui.banner import _build_art, _status_dot, get_banner, print_banner

# ---------------------------------------------------------------------------
# _status_dot
# ---------------------------------------------------------------------------


def test_status_dot_connected() -> None:
    char, style = _status_dot(True)
    assert char == "●"
    assert "10b981" in style  # SUCCESS green


def test_status_dot_disconnected() -> None:
    char, style = _status_dot(False)
    assert char == "●"
    assert "ef4444" in style  # ERROR red


# ---------------------------------------------------------------------------
# _build_art
# ---------------------------------------------------------------------------


def test_build_art_returns_text() -> None:
    art = _build_art()
    assert isinstance(art, Text)
    # All 6 lines rendered
    assert art.plain.count("\n") == 6


# ---------------------------------------------------------------------------
# get_banner — status row content
# ---------------------------------------------------------------------------


def _panel_plain(panel: object) -> str:
    """Extract plain text from a banner Panel (Panel → Align → Text)."""
    from rich.panel import Panel as RichPanel

    assert isinstance(panel, RichPanel)
    # panel.renderable is Align; Align.renderable is the Text
    return panel.renderable.renderable.plain  # type: ignore[union-attr]


def test_get_banner_no_model_no_meta() -> None:
    panel = get_banner("1.0.0", lmstudio_connected=True)
    plain = _panel_plain(panel)
    assert "LM Studio connected" in plain
    assert "v1.0.0" in plain


def test_get_banner_with_model() -> None:
    panel = get_banner("1.0.0", model="Qwen2.5-Coder-7B", lmstudio_connected=True)
    plain = _panel_plain(panel)
    assert "Qwen2.5-Coder-7B" in plain


def test_get_banner_with_model_meta() -> None:
    panel = get_banner(
        "1.0.0",
        model="Qwen2.5-Coder-7B",
        lmstudio_connected=True,
        model_meta="llama  ·  4.5 GB  ·  32k ctx",
    )
    plain = _panel_plain(panel)
    assert "llama" in plain
    assert "4.5 GB" in plain
    assert "32k ctx" in plain


def test_get_banner_meta_absent_when_empty() -> None:
    panel_plain = _panel_plain(get_banner("1.0.0", model="M", lmstudio_connected=True))
    panel_meta = _panel_plain(
        get_banner("1.0.0", model="M", lmstudio_connected=True, model_meta="arch")
    )
    assert "arch" not in panel_plain
    assert "arch" in panel_meta


def test_get_banner_disconnected() -> None:
    panel = get_banner("0.0.1", lmstudio_connected=False)
    plain = _panel_plain(panel)
    assert "LM Studio not found" in plain


# ---------------------------------------------------------------------------
# print_banner — smoke (just ensure it doesn't raise)
# ---------------------------------------------------------------------------


def test_print_banner_smoke(capsys: object) -> None:
    print_banner("1.0.0", model="TestModel", lmstudio_connected=True, model_meta="llama  ·  4.5 GB")
    # No assertion needed — just must not raise
