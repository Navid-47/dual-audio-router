"""
Hallmark Cobalt design tokens for the desktop UI.

Mapped from tokens.css (OKLCH source of truth). CustomTkinter needs hex/sRGB;
values are perceptual matches, not re-invented palette choices.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CobaltTokens:
    paper: str = "#F7F8FB"
    paper_2: str = "#EFF1F6"
    ink: str = "#1A2030"
    ink_2: str = "#3A4254"
    ink_3: str = "#6B7385"
    rule: str = "#D8DCE6"
    rule_2: str = "#C4CAD6"
    accent: str = "#2F6FED"
    accent_hover: str = "#2559C4"
    accent_ink: str = "#F7F8FB"
    graphite: str = "#1C2230"
    graphite_ink: str = "#E8EBF2"
    graphite_muted: str = "#9AA3B5"
    success: str = "#1F7A4A"
    success_bg: str = "#E6F4EC"
    danger: str = "#B33A3A"
    danger_hover: str = "#922F2F"
    radius_sm: int = 6
    radius_md: int = 10
    font_display: tuple[str, ...] = ("Segoe UI Semibold", "Segoe UI", "sans-serif")
    font_body: tuple[str, ...] = ("Segoe UI", "sans-serif")
    font_mono: tuple[str, ...] = ("Cascadia Mono", "Consolas", "monospace")


TOKENS = CobaltTokens()
