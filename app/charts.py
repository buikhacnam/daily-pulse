"""Server-side SVG charts generated with Matplotlib."""

from io import StringIO

from matplotlib.backends.backend_svg import FigureCanvasSVG
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator


CHARTS = {
    "steps": ("steps", "#69b78a", "bar"),
    "sleep": ("sleep_minutes", "#a78bc7", "line"),
    "calories": ("calories", "#d8ac70", "line"),
    "heart": ("resting_heart_rate", "#de998d", "line"),
}


def chart_svg(metric: str, days: list[dict]) -> str:
    field, color, kind = CHARTS[metric]
    figure = Figure(figsize=(7, 1.75), dpi=100, facecolor="none")
    FigureCanvasSVG(figure)
    ax = figure.add_axes((0.12, 0.16, 0.865, 0.78), facecolor="none")
    values = [day.get(field) for day in days]
    if metric == "sleep":
        values = [value / 60 if value is not None else None for value in values]
    positions = list(range(len(days)))
    present = [(position, value) for position, value in zip(positions, values) if value is not None]

    if present:
        if kind == "bar":
            width = 0.62 if len(days) <= 7 else 0.7
            ax.bar([p for p, _ in present], [v for _, v in present], width=width,
                   color=["#64b486" if p == positions[-1] else "#c0e4ca" for p, _ in present],
                   linewidth=0)
            ax.set_ylim(0, max(v for _, v in present) * 1.15)
        else:
            series = [float("nan") if value is None else value for value in values]
            ax.plot(positions, series, color=color, linewidth=2, marker="o",
                    markersize=3.5 if len(days) <= 7 else 2.4,
                    markerfacecolor="white", markeredgewidth=1.4)
            low = min(v for _, v in present)
            high = max(v for _, v in present)
            padding = max((high - low) * 0.18, 0.5 if metric == "sleep" else 2)
            ax.set_ylim(low - padding, high + padding)
        ax.set_xlim(-0.5, len(days) - 0.5)
        ticks = positions if len(days) <= 7 else sorted(set([0, 7, 14, 21, len(days) - 1]))
        ax.set_xticks(ticks, [f"{int(days[i]['date'][5:7])}/{int(days[i]['date'][8:10])}" for i in ticks])
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=metric != "sleep"))
        if metric == "sleep":
            ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}h"))
        elif metric == "steps":
            ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:g}k" if value else "0"))
        else:
            ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
        ax.grid(axis="y", color="#eef1eb", linewidth=0.8)
        ax.set_axisbelow(True)
    else:
        ax.text(0.5, 0.52, "No measurements for this period", transform=ax.transAxes,
                ha="center", va="center", color="#9aa69c", fontsize=10)
        ax.set_xticks([])
        ax.set_yticks([])

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="x", length=0, labelsize=8, colors="#aab4aa", pad=8)
    ax.tick_params(axis="y", length=0, labelsize=8, colors="#aab4aa", pad=4)
    output = StringIO()
    figure.savefig(output, format="svg", transparent=True)
    return output.getvalue()
