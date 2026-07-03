"""chart tool (key: viz.chart) — pure stdlib SVG chart generator, no external deps."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from foundation import PermissionLevel
from registry import tool

# ─── palette + layout constants ────────────────────────────────────────────

_COLORS = [
    "#4e79a7", "#f28e2b", "#59a14f", "#e15759",
    "#76b7b2", "#edc948", "#b07aa1", "#ff9da7",
]

_W, _H = 560, 380              # SVG canvas size
_MT, _MR, _MB, _ML = 50, 20, 80, 70   # margins: top, right, bottom, left
_PW = _W - _ML - _MR           # plot width  = 470
_PH = _H - _MT - _MB           # plot height = 250
_MAX_BAR_W = 80.0               # pixel cap on a single bar


# ─── SVG helpers ───────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def _empty_svg(title: str, message: str) -> str:
    t, m = _esc(title or "Chart"), _esc(message)
    cx = _W // 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{_H}">'
        f'<rect width="100%" height="100%" fill="#f9f9f9"/>'
        f'<text x="{cx}" y="38" text-anchor="middle" font-family="sans-serif"'
        f' font-size="15" font-weight="bold" fill="#333">{t}</text>'
        f'<text x="{cx}" y="{_H // 2}" text-anchor="middle" font-family="sans-serif"'
        f' font-size="13" fill="#888">{m}</text>'
        f'</svg>'
    )


def _y_scale(all_vals: list[float]) -> tuple[float, float, float]:
    y_min = min(0.0, min(all_vals))
    y_max = max(0.0, max(all_vals))
    if y_max == y_min:
        y_max = y_min + 1.0
    return y_min, y_max, _PH / (y_max - y_min)


def _y_axis_svg(y_min: float, y_max: float, scale: float) -> list[str]:
    parts: list[str] = []
    for i in range(6):
        v = y_min + (y_max - y_min) * i / 5
        y = _MT + _PH - (v - y_min) * scale
        parts += [
            f'<line x1="{_ML - 4}" y1="{y:.1f}" x2="{_ML}" y2="{y:.1f}"'
            f' stroke="#999" stroke-width="1"/>',
            f'<text x="{_ML - 6}" y="{y + 4:.1f}" text-anchor="end"'
            f' font-family="sans-serif" font-size="10" fill="#666">{v:.1f}</text>',
        ]
    return parts


def _frame_svg() -> list[str]:
    return [
        f'<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<line x1="{_ML}" y1="{_MT}" x2="{_ML}" y2="{_MT + _PH}"'
        f' stroke="#ccc" stroke-width="1"/>',
        f'<line x1="{_ML}" y1="{_MT + _PH}" x2="{_ML + _PW}" y2="{_MT + _PH}"'
        f' stroke="#ccc" stroke-width="1"/>',
    ]


def _legend_svg(series: list[tuple[str, list[float]]], kind: str) -> list[str]:
    parts: list[str] = []
    ly = _MT + _PH + 42
    for si, (label, _) in enumerate(series):
        color = _COLORS[si % len(_COLORS)]
        lx = _ML + si * 130
        if kind == "bar":
            parts.append(
                f'<rect x="{lx}" y="{ly - 10}" width="12" height="12" fill="{color}"/>'
            )
            tx = lx + 16
        else:
            parts += [
                f'<line x1="{lx}" y1="{ly - 5}" x2="{lx + 18}" y2="{ly - 5}"'
                f' stroke="{color}" stroke-width="2.5"/>',
                f'<circle cx="{lx + 9}" cy="{ly - 5}" r="3" fill="{color}"/>',
            ]
            tx = lx + 24
        parts.append(
            f'<text x="{tx}" y="{ly}" font-family="sans-serif"'
            f' font-size="11" fill="#333">{_esc(label)}</text>'
        )
    return parts


def _anno_svg(title: str, x_label: str, y_label: str) -> list[str]:
    parts: list[str] = []
    if title:
        parts.append(
            f'<text x="{_W // 2}" y="32" text-anchor="middle" font-family="sans-serif"'
            f' font-size="15" font-weight="bold" fill="#222">{_esc(title)}</text>'
        )
    if x_label:
        parts.append(
            f'<text x="{_ML + _PW // 2}" y="{_H - 5}" text-anchor="middle"'
            f' font-family="sans-serif" font-size="12" fill="#444">{_esc(x_label)}</text>'
        )
    if y_label:
        cx, cy = 14, _MT + _PH // 2
        parts.append(
            f'<text x="{cx}" y="{cy}" text-anchor="middle" font-family="sans-serif"'
            f' font-size="12" fill="#444" transform="rotate(-90, {cx}, {cy})">'
            f'{_esc(y_label)}</text>'
        )
    return parts


# ─── chart renderers ───────────────────────────────────────────────────────

def _render_bar(
    series: list[tuple[str, list[float]]],
    n: int,
    title: str,
    x_label: str,
    y_label: str,
    x_labels: list[str],
) -> str:
    all_vals = [v for _, vals in series for v in vals]
    y_min, y_max, scale = _y_scale(all_vals)
    zero_y = _MT + _PH - (0.0 - y_min) * scale

    ns = len(series)
    group_w = _PW / n
    bar_w = min(group_w * 0.7 / ns, _MAX_BAR_W)
    group_pad = (group_w - bar_w * ns) / 2

    parts: list[str] = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{_H}">']
    parts += _frame_svg()
    parts.append(
        f'<line x1="{_ML}" y1="{zero_y:.1f}" x2="{_ML + _PW}" y2="{zero_y:.1f}"'
        f' stroke="#bbb" stroke-width="0.8" stroke-dasharray="4,2"/>'
    )
    parts += _y_axis_svg(y_min, y_max, scale)

    for si, (label, vals) in enumerate(series):
        color = _COLORS[si % len(_COLORS)]
        for xi, v in enumerate(vals):
            bx = _ML + xi * group_w + group_pad + si * bar_w
            bh = abs(v) * scale
            by = (zero_y - bh) if v >= 0 else zero_y
            parts.append(
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}"'
                f' fill="{color}" opacity="0.85"/>'
            )

    for xi in range(n):
        lbl = x_labels[xi] if xi < len(x_labels) else str(xi + 1)
        x = _ML + (xi + 0.5) * group_w
        parts.append(
            f'<text x="{x:.1f}" y="{_MT + _PH + 18}" text-anchor="middle"'
            f' font-family="sans-serif" font-size="10" fill="#666">{_esc(lbl)}</text>'
        )

    parts += _legend_svg(series, "bar")
    parts += _anno_svg(title, x_label, y_label)
    parts.append('</svg>')
    return "".join(parts)


def _render_line(
    series: list[tuple[str, list[float]]],
    n: int,
    title: str,
    x_label: str,
    y_label: str,
    x_labels: list[str],
) -> str:
    all_vals = [v for _, vals in series for v in vals]
    y_min, y_max, scale = _y_scale(all_vals)
    x_step = _PW / max(n - 1, 1)

    parts: list[str] = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{_H}">']
    parts += _frame_svg()
    parts += _y_axis_svg(y_min, y_max, scale)

    for si, (label, vals) in enumerate(series):
        color = _COLORS[si % len(_COLORS)]
        xs = [_ML + xi * x_step for xi in range(n)]
        ys = [_MT + _PH - (v - y_min) * scale for v in vals]
        if n > 1:
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
            parts.append(
                f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>'
            )
        for x, y in zip(xs, ys):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>')

    for xi in range(n):
        lbl = x_labels[xi] if xi < len(x_labels) else str(xi + 1)
        x = _ML + xi * x_step
        parts.append(
            f'<text x="{x:.1f}" y="{_MT + _PH + 18}" text-anchor="middle"'
            f' font-family="sans-serif" font-size="10" fill="#666">{_esc(lbl)}</text>'
        )

    parts += _legend_svg(series, "line")
    parts += _anno_svg(title, x_label, y_label)
    parts.append('</svg>')
    return "".join(parts)


# ─── schema ────────────────────────────────────────────────────────────────

class Series(BaseModel):
    label: str
    values: list[float]


class ChartIn(BaseModel):
    kind: Literal["bar", "line"]
    series: list[Series] = Field(default_factory=list)
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    x_labels: list[str] = Field(default_factory=list)


class ChartOut(BaseModel):
    svg: str
    content_type: str = "image/svg+xml"
    error: str = ""


# ─── tool ──────────────────────────────────────────────────────────────────

@tool
class ChartTool:
    name = "chart"
    domain = "viz"
    description = (
        "Takes structured data (named numeric series) and produces an SVG chart. "
        "Supports 'bar' and 'line' chart kinds. Used by the Data Analysis Expert "
        "to produce visual deliverables in reports."
    )
    input_schema = ChartIn
    output_schema = ChartOut
    permission = PermissionLevel.READ
    tags = ("viz", "chart", "data-analysis")

    async def run(self, args: ChartIn) -> ChartOut:
        try:
            clean = [s for s in args.series if s.values]
            if not clean:
                return ChartOut(
                    svg=_empty_svg(args.title, "No data to display."),
                    error="no_data",
                )
            n = min(len(s.values) for s in clean)
            series: list[tuple[str, list[float]]] = [(s.label, s.values[:n]) for s in clean]

            if args.kind == "bar":
                svg = _render_bar(series, n, args.title, args.x_label, args.y_label, args.x_labels)
            else:
                svg = _render_line(series, n, args.title, args.x_label, args.y_label, args.x_labels)
            return ChartOut(svg=svg)
        except Exception as exc:  # noqa: BLE001
            return ChartOut(
                svg=_empty_svg(args.title, "Chart generation failed."),
                error=str(exc),
            )
