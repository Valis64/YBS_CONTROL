"""CustomTkinter theme configuration utilities."""

from __future__ import annotations

import customtkinter as ctk
from typing import Optional


def configure(
    mode: str = "dark",
    color_theme: str = "dark-blue",
    scaling: Optional[float] = None,
) -> None:
    """Configure appearance mode, color theme and optional widget scaling.

    Parameters
    ----------
    mode:
        The appearance mode to set, e.g., ``"dark"`` or ``"light"``.
    color_theme:
        Name of the default color theme to apply.
    scaling:
        Optional scaling factor for widget sizes. If ``None``, scaling is
        not modified.
    """

    ctk.set_appearance_mode(mode)
    ctk.set_default_color_theme(color_theme)
    if scaling is not None:
        ctk.set_widget_scaling(scaling)
