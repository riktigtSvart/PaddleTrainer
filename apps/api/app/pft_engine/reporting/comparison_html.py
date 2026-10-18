from html import escape

from app.pft_engine.archive.comparison import (
    FeatureDelta,
    PftArchiveComparison,
    RhriDelta,
)
from app.pft_engine.storage.repository import (
    StoredPftSample,
)


_FEATURE_LABELS = {
    "HR_PRE_MEDIAN": "PRE HR",
    "HR_P1_MEDIAN": "P1 HR",
    "HR_P2_MEDIAN": "P2 HR",

    "DELTA_HR30_P1": "P1 Δ30",
    "DELTA_HR60_P1": "P1 Δ60",
    "DELTA_HR30_P2": "P2 Δ30",
    "DELTA_HR60_P2": "P2 Δ60",

    "HRR30": "HRR30",
    "HRR60": "HRR60",
    "HRR90": "HRR90",
    "HRR120": "HRR120",
}


_SYNC_HOVER_SCRIPT = """
<script>
(() => {
    const slotsByKey = new Map();
    let activeSlots = [];

    for (
        const slot of document.querySelectorAll(
            ".hover-slot[data-hover-key]"
        )
    ) {
        const key = slot.dataset.hoverKey;

        if (!slotsByKey.has(key)) {
            slotsByKey.set(key, []);
        }

        slotsByKey.get(key).push(slot);
    }

    function clearActive() {
        for (const slot of activeSlots) {
            slot.classList.remove("is-active");
        }

        activeSlots = [];
    }

    function activate(key) {
        clearActive();

        activeSlots = (
            slotsByKey.get(key)
            ?? []
        );

        for (const slot of activeSlots) {
            slot.classList.add("is-active");
        }
    }

    document.addEventListener(
        "pointerover",
        (event) => {
            const hit = event.target.closest?.(
                ".hover-hit"
            );

            if (!hit) {
                return;
            }

            const slot = hit.closest(
                ".hover-slot"
            );

            if (!slot) {
                return;
            }

            const key = slot.dataset.hoverKey;

            if (key) {
                activate(key);
            }
        }
    );

    for (
        const chart of document.querySelectorAll(
            ".trace-chart"
        )
    ) {
        chart.addEventListener(
            "pointerleave",
            clearActive
        );
    }
})();
</script>
"""


def _feature_map(
    comparison: PftArchiveComparison,
) -> dict[str, FeatureDelta]:
    return {
        feature.name: feature
        for feature in comparison.features
    }


def _format_value(
    value: float | None,
    *,
    digits: int = 1,
) -> str:
    if value is None:
        return "—"

    return f"{value:.{digits}f}"


def _format_delta(
    value: float | None,
    *,
    digits: int = 1,
) -> str:
    if value is None:
        return "—"

    return f"{value:+.{digits}f}"


def _format_pct(
    value: float | None,
) -> str:
    if value is None:
        return "—"

    return f"{value:+.1f}%"


def _short_date(
    timestamp: str,
) -> str:
    return timestamp[:10]


def _svg_bar_chart(
    *,
    title: str,
    rows: list[
        tuple[
            str,
            float | None,
            float | None,
        ]
    ],
    unit: str,
    digits: int,
) -> str:

    usable_values = [
        value
        for _, reference, current in rows
        for value in (
            reference,
            current,
        )
        if value is not None
    ]

    if not usable_values:
        return ""

    minimum = min(
        0.0,
        min(usable_values),
    )

    maximum = max(
        0.0,
        max(usable_values),
    )

    if maximum == minimum:
        maximum = minimum + 1.0

    width_per_group = 110
    chart_width = max(
        520,
        len(rows) * width_per_group + 90,
    )

    chart_height = 310

    plot_top = 35.0
    plot_bottom = 220.0
    plot_height = (
        plot_bottom - plot_top
    )

    def y_position(
        value: float,
    ) -> float:
        return (
            plot_top
            + (
                maximum - value
            )
            / (
                maximum - minimum
            )
            * plot_height
        )

    zero_y = y_position(0.0)

    fragments: list[str] = []

    fragments.append(
        '<div class="chart-panel">'
    )

    fragments.append(
        f'<h3>{escape(title)}</h3>'
    )

    fragments.append(
        '<div class="legend">'
        '<span><i class="legend-ref"></i>'
        'Reference</span>'
        '<span><i class="legend-current"></i>'
        'Current</span>'
        '</div>'
    )

    fragments.append(
        '<div class="chart-scroll">'
    )

    fragments.append(
        f'<svg class="chart" '
        f'viewBox="0 0 {chart_width} '
        f'{chart_height}" '
        f'role="img" '
        f'aria-label="{escape(title)}">'
    )

    fragments.append(
        f'<line '
        f'x1="45" '
        f'y1="{zero_y:.2f}" '
        f'x2="{chart_width - 20}" '
        f'y2="{zero_y:.2f}" '
        f'class="axis-line"/>'
    )

    for index, (
        label,
        reference,
        current,
    ) in enumerate(rows):

        group_x = (
            65
            + index * width_per_group
        )

        for offset, value, css_class in (
            (
                0,
                reference,
                "bar-ref",
            ),
            (
                34,
                current,
                "bar-current",
            ),
        ):
            if value is None:
                continue

            value_y = y_position(
                value
            )

            bar_y = min(
                value_y,
                zero_y,
            )

            bar_height = max(
                1.0,
                abs(
                    zero_y
                    - value_y
                ),
            )

            fragments.append(
                f'<rect '
                f'x="{group_x + offset}" '
                f'y="{bar_y:.2f}" '
                f'width="26" '
                f'height="{bar_height:.2f}" '
                f'rx="4" '
                f'class="{css_class}">'
                f'<title>'
                f'{escape(label)}: '
                f'{value:.{digits}f} '
                f'{escape(unit)}'
                f'</title>'
                f'</rect>'
            )

            if value >= 0:
                text_y = (
                    bar_y - 6
                )
            else:
                text_y = (
                    bar_y
                    + bar_height
                    + 15
                )

            fragments.append(
                f'<text '
                f'x="{group_x + offset + 13}" '
                f'y="{text_y:.2f}" '
                f'class="value-label" '
                f'text-anchor="middle">'
                f'{value:.{digits}f}'
                f'</text>'
            )

        fragments.append(
            f'<text '
            f'x="{group_x + 30}" '
            f'y="252" '
            f'class="category-label" '
            f'text-anchor="middle">'
            f'{escape(label)}'
            f'</text>'
        )

    fragments.append(
        f'<text '
        f'x="12" '
        f'y="22" '
        f'class="unit-label">'
        f'{escape(unit)}'
        f'</text>'
    )

    fragments.append(
        '</svg>'
    )

    fragments.append(
        '</div>'
    )

    fragments.append(
        '</div>'
    )

    return "".join(
        fragments
    )


def _feature_chart(
    *,
    comparison: PftArchiveComparison,
    title: str,
    names: tuple[str, ...],
) -> str:

    features = _feature_map(
        comparison
    )

    rows: list[
        tuple[
            str,
            float | None,
            float | None,
        ]
    ] = []

    for name in names:
        feature = features.get(
            name
        )

        if feature is None:
            continue

        rows.append(
            (
                _FEATURE_LABELS.get(
                    name,
                    name,
                ),
                feature.reference_value,
                feature.current_value,
            )
        )

    return _svg_bar_chart(
        title=title,
        rows=rows,
        unit="bpm",
        digits=0,
    )


def _rhri_chart(
    comparison: PftArchiveComparison,
) -> str:

    by_key: dict[
        tuple[str, str],
        RhriDelta,
    ] = {
        (
            value.method,
            value.stage,
        ): value
        for value in comparison.rhri
    }

    rows = []

    for method, stage, label in (
        (
            "RHRI_LOCAL",
            "p1",
            "LOCAL P1",
        ),
        (
            "RHRI_LOCAL",
            "p2",
            "LOCAL P2",
        ),
        (
            "RHRI_SIG",
            "p1",
            "SIG P1",
        ),
        (
            "RHRI_SIG",
            "p2",
            "SIG P2",
        ),
    ):
        value = by_key.get(
            (
                method,
                stage,
            )
        )

        if value is None:
            continue

        rows.append(
            (
                label,
                value.reference_value_bpm_per_s,
                value.current_value_bpm_per_s,
            )
        )

    return _svg_bar_chart(
        title="rHRI comparison",
        rows=rows,
        unit="bpm/s",
        digits=3,
    )


def _feature_table(
    comparison: PftArchiveComparison,
) -> str:

    rows: list[str] = []

    for feature in comparison.features:

        quality = (
            f"{feature.reference_quality_grade}"
            " → "
            f"{feature.current_quality_grade}"
        )

        baseline = (
            (
                "yes"
                if (
                    feature
                    .reference_baseline_eligible
                )
                else "no"
            )
            + " → "
            + (
                "yes"
                if (
                    feature
                    .current_baseline_eligible
                )
                else "no"
            )
        )

        rows.append(
            "<tr>"
            f"<td>{escape(feature.name)}</td>"
            f"<td>{_format_value(feature.reference_value)}</td>"
            f"<td>{_format_value(feature.current_value)}</td>"
            f"<td>{_format_delta(feature.delta)}</td>"
            f"<td>{_format_pct(feature.relative_change_pct)}</td>"
            f"<td>{escape(quality)}</td>"
            f"<td>{escape(baseline)}</td>"
            "</tr>"
        )

    return (
        '<div class="table-scroll">'
        '<table>'
        '<thead>'
        '<tr>'
        '<th>Feature</th>'
        '<th>Reference</th>'
        '<th>Current</th>'
        '<th>Δ</th>'
        '<th>Change</th>'
        '<th>Quality</th>'
        '<th>Baseline eligible</th>'
        '</tr>'
        '</thead>'
        '<tbody>'
        + "".join(rows)
        + '</tbody>'
        '</table>'
        '</div>'
    )


def render_pft_comparison_html(
    *,
    comparison: PftArchiveComparison,
    reference_id: int,
    current_id: int,
    reference_samples: tuple[
        StoredPftSample, ...
    ] = (),
    current_samples: tuple[
        StoredPftSample, ...
    ] = (),
    reference_markers: dict[
        str,
        float,
    ] | None = None,
    current_markers: dict[
        str,
        float,
    ] | None = None,
) -> str:
    hr_trace = _svg_time_series_chart(
        title="HR(t)",
        reference_samples=reference_samples,
        current_samples=current_samples,
        field="hr_bpm",
        unit="bpm",
        digits=0,
        reference_markers=reference_markers,
        current_markers=current_markers,
    )

    speed_trace = _svg_time_series_chart(
        title="SPEED(t)",
        reference_samples=reference_samples,
        current_samples=current_samples,
        field="speed_mps",
        unit="km/h",
        multiplier=3.6,
        start_at_zero=True,
        digits=2,
        reference_markers=reference_markers,
        current_markers=current_markers,
    )

    power_trace = _svg_time_series_chart(
        title="POWER(t)",
        reference_samples=reference_samples,
        current_samples=current_samples,
        field="power_w",
        unit="W",
        start_at_zero=True,
        digits=0,
        reference_markers=reference_markers,
        current_markers=current_markers,
    )

    steady_hr_chart = _feature_chart(
        comparison=comparison,
        title="Steady-state heart rate",
        names=(
            "HR_PRE_MEDIAN",
            "HR_P1_MEDIAN",
            "HR_P2_MEDIAN",
        ),
    )

    response_chart = _feature_chart(
        comparison=comparison,
        title="Heart-rate response and recovery",
        names=(
            "DELTA_HR30_P1",
            "DELTA_HR60_P1",
            "DELTA_HR30_P2",
            "DELTA_HR60_P2",
            "HRR30",
            "HRR60",
            "HRR90",
            "HRR120",
        ),
    )

    rhri_chart = _rhri_chart(
        comparison
    )

    feature_table = _feature_table(
        comparison
    )

    reference_date = _short_date(
        comparison.reference_started_at
    )

    current_date = _short_date(
        comparison.current_started_at
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>
<title>
PFT comparison — {reference_id} vs {current_id}
</title>

<style>
:root {{
    color-scheme: light dark;

    --bg: #f5f6f8;
    --card: #ffffff;
    --text: #17191c;
    --muted: #666b73;
    --border: #d9dde3;

    --reference: #59789f;
    --current: #ba7247;
}}

@media (prefers-color-scheme: dark) {{
    :root {{
        --bg: #15171a;
        --card: #202328;
        --text: #f1f3f5;
        --muted: #a9afb8;
        --border: #3b4149;

        --reference: #7fa3ce;
        --current: #dc9367;
    }}
}}

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family:
        Inter,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}}

main {{
    max-width: 1180px;
    margin: 0 auto;
    padding: 32px 20px 60px;
}}

h1 {{
    margin: 0 0 6px;
    font-size: 30px;
}}

.subtitle {{
    color: var(--muted);
    margin-bottom: 28px;
}}

.session-grid {{
    display: grid;
    grid-template-columns:
        repeat(
            2,
            minmax(0, 1fr)
        );
    gap: 16px;
    margin-bottom: 24px;
}}

.session-card,
.chart-panel,
.table-panel {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
}}

.session-card {{
    padding: 20px;
}}

.session-label {{
    color: var(--muted);
    font-size: 13px;
    font-weight: 700;
    letter-spacing: .08em;
    text-transform: uppercase;
}}

.session-date {{
    margin: 8px 0;
    font-size: 24px;
    font-weight: 700;
}}

.session-meta {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px 18px;
    color: var(--muted);
}}

.quality {{
    color: var(--text);
    font-weight: 700;
}}

.trace-section {{
    margin-top: 22px;
    display: grid;
    gap: 18px;
}}

.trace-section h2 {{
    margin-bottom: 0;
}}

.trace-chart {{
    display: block;
    width: 100%;
    min-width: 700px;
    max-height: 320px;
}}

.trace-reference,
.trace-current {{
    fill: none;
    stroke-width: 1.35;
    stroke-linejoin: round;
    stroke-linecap: round;
}}

.observed-marker-reference,
.observed-marker-current {{
    stroke-width: 1.2;
    stroke-dasharray: 3 4;
    opacity: .9;
}}

.observed-marker-reference {{
    stroke: var(--reference);
}}

.observed-marker-current {{
    stroke: var(--current);
}}

.observed-label-reference,
.observed-label-current {{
    font-size: 10px;
    font-weight: 700;
}}

.observed-label-reference {{
    fill: var(--reference);
}}

.observed-label-current {{
    fill: var(--current);
}}

.hover-hit {{
    fill: transparent;
    pointer-events: all;
    cursor: crosshair;
}}

.hover-cursor,
.hover-reference,
.hover-current,
.hover-box,
.hover-time,
.hover-value-reference,
.hover-value-equal,
.hover-value-current {{
    opacity: 0;
    pointer-events: none;
}}

.hover-slot:hover .hover-cursor,
.hover-slot:hover .hover-reference,
.hover-slot:hover .hover-current,
.hover-slot:hover .hover-box,
.hover-slot:hover .hover-time,
.hover-slot:hover .hover-value-reference,
.hover-slot:hover .hover-value-current,
.hover-slot.is-active .hover-cursor,
.hover-slot.is-active .hover-reference,
.hover-slot.is-active .hover-current,
.hover-slot.is-active .hover-box,
.hover-slot.is-active .hover-time,
.hover-slot.is-active .hover-value-reference,
.hover-slot:hover .hover-value-equal,
.hover-slot.is-active .hover-value-equal,
.hover-slot.is-active .hover-value-current
 {{
    opacity: 1;
}}

.hover-cursor {{
    stroke: var(--muted);
    stroke-width: 1;
    stroke-dasharray: 2 3;
}}

.hover-reference {{
    fill: var(--reference);
    stroke: var(--card);
    stroke-width: 1.2;
}}

.hover-current {{
    fill: var(--current);
    stroke: var(--card);
    stroke-width: 1.2;
}}

.hover-box {{
    fill: var(--card);
    fill-opacity: .96;
    stroke: var(--border);
    stroke-width: 1;
}}

.hover-time {{
    fill: var(--text);
    font-size: 11px;
    font-weight: 700;
}}

.hover-value-reference {{
    fill: var(--reference);
    font-size: 11px;
}}

.hover-value-current {{
    fill: var(--current);
    font-size: 11px;
}}

.hover-value-equal {{
    fill: var(--text);
    font-size: 11px;
}}

.trace-reference {{
    stroke: var(--reference);
}}

.trace-current {{
    stroke: var(--current);
}}

.grid-line {{
    stroke: var(--border);
    stroke-width: 1;
    opacity: .55;
}}

.stage-line {{
    stroke: var(--muted);
    stroke-width: 1;
    stroke-dasharray: 4 4;
    opacity: .65;
}}

.stage-label {{
    fill: var(--muted);
    font-size: 11px;
    font-weight: 700;
}}

.axis-label {{
    fill: var(--muted);
    font-size: 10px;
}}

.chart-grid {{
    display: grid;
    gap: 18px;
    margin-top: 22px;
}}

.chart-panel {{
    padding: 18px;
    min-width: 0;
}}

.chart-panel h3 {{
    margin: 0 0 6px;
    font-size: 18px;
}}

.legend {{
    display: flex;
    gap: 18px;
    margin-bottom: 8px;
    color: var(--muted);
    font-size: 13px;
}}

.legend span {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
}}

.legend i {{
    display: inline-block;
    width: 12px;
    height: 12px;
    border-radius: 3px;
}}

.legend-ref {{
    background: var(--reference);
}}

.legend-current {{
    background: var(--current);
}}

.chart-scroll {{
    overflow-x: auto;
}}

.chart {{
    display: block;
    width: 100%;
    min-width: 520px;
    max-height: 340px;
}}

.bar-ref {{
    fill: var(--reference);
}}

.bar-current {{
    fill: var(--current);
}}

.axis-line {{
    stroke: var(--border);
    stroke-width: 1.5;
}}

.value-label {{
    fill: var(--text);
    font-size: 11px;
}}

.category-label {{
    fill: var(--muted);
    font-size: 11px;
}}

.unit-label {{
    fill: var(--muted);
    font-size: 11px;
}}

.table-panel {{
    margin-top: 22px;
    padding: 18px;
}}

.table-panel h2 {{
    margin-top: 0;
}}

.table-scroll {{
    overflow-x: auto;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    white-space: nowrap;
}}

th,
td {{
    padding: 11px 12px;
    border-bottom: 1px solid var(--border);
    text-align: right;
}}

th {{
    color: var(--muted);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: .04em;
}}

th:first-child,
td:first-child {{
    text-align: left;
}}

tbody tr:last-child td {{
    border-bottom: 0;
}}

.note {{
    margin-top: 18px;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.5;
}}

@media (max-width: 700px) {{
    main {{
        padding: 20px 12px 40px;
    }}

    .session-grid {{
        grid-template-columns: 1fr;
    }}

    h1 {{
        font-size: 25px;
    }}
}}

@media print {{
    body {{
        background: white;
        color: black;
    }}

    main {{
        max-width: none;
    }}

    .session-card,
    .chart-panel,
    .table-panel {{
        break-inside: avoid;
    }}
}}
</style>
</head>

<body>
<main>

<h1>PFT comparison</h1>

<div class="subtitle">
    {escape(comparison.protocol_name)}
    {escape(comparison.protocol_version)}
    · current − reference
</div>

<section class="session-grid">

<div class="session-card">
    <div class="session-label">
        Reference · #{reference_id}
    </div>

    <div class="session-date">
        {escape(reference_date)}
    </div>

    <div class="session-meta">
        <span>
            Quality:
            <strong class="quality">
                {escape(
                    comparison
                    .reference_session_quality_grade
                )}
            </strong>
        </span>

        <span>
            Processor:
            {escape(
                comparison
                .reference_processor_version
            )}
        </span>
    </div>
</div>

<div class="session-card">
    <div class="session-label">
        Current · #{current_id}
    </div>

    <div class="session-date">
        {escape(current_date)}
    </div>

    <div class="session-meta">
        <span>
            Quality:
            <strong class="quality">
                {escape(
                    comparison
                    .current_session_quality_grade
                )}
            </strong>
        </span>

        <span>
            Processor:
            {escape(
                comparison
                .current_processor_version
            )}
        </span>
    </div>
</div>

</section>

<section class="trace-section">
    <h2>Session traces</h2>
    {hr_trace}
    {speed_trace}
    {power_trace}
</section>

<section class="chart-grid">
    {steady_hr_chart}
    {response_chart}
    {rhri_chart}
</section>

<section class="table-panel">
<h2>Detailed feature comparison</h2>

{feature_table}

<div class="note">
    Values are descriptive comparisons only.
    Positive and negative changes are not automatically
    interpreted as improved readiness, fatigue, or
    performance.
</div>
</section>

</main>

{_SYNC_HOVER_SCRIPT}

</body>
</html>
"""


def _stage_name_for_elapsed(
    elapsed_s: float,
) -> str:
    if elapsed_s < 120.0:
        return "PRE"

    if elapsed_s < 300.0:
        return "P0"

    if elapsed_s < 480.0:
        return "P1"

    if elapsed_s < 660.0:
        return "P2"

    return "REC"


def _time_label(
    elapsed_s: float,
) -> str:
    total = int(round(elapsed_s))

    minutes = total // 60
    seconds = total % 60

    return f"{minutes}:{seconds:02d}"


def _time_label_hhmmss(
    elapsed_s: float,
) -> str:
    total = max(
        0,
        int(round(elapsed_s)),
    )

    hours = total // 3600
    minutes = (
        total % 3600
    ) // 60
    seconds = total % 60

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{seconds:02d}"
    )


def _svg_time_series_chart(
    *,
    title: str,
    reference_samples: tuple[
        StoredPftSample, ...
    ],
    current_samples: tuple[
        StoredPftSample, ...
    ],
    field: str,
    unit: str,
    multiplier: float = 1.0,
    start_at_zero: bool = False,
    digits: int = 1,
    reference_markers: dict[
        str,
        float,
    ] | None = None,
    current_markers: dict[
        str,
        float,
    ] | None = None,
) -> str:

    width = 1100
    height = 300

    left = 58.0
    right = 20.0
    top = 35.0
    bottom = 48.0

    plot_width = (
        width - left - right
    )

    plot_height = (
        height - top - bottom
    )

    all_samples = (
        *reference_samples,
        *current_samples,
    )

    values = [
        float(getattr(sample, field))
        * multiplier
        for sample in all_samples
        if getattr(sample, field) is not None
    ]

    if not values:
        return ""

    max_elapsed = max(
        sample.elapsed_s
        for sample in all_samples
    )

    if max_elapsed <= 0.0:
        return ""

    minimum = min(values)
    maximum = max(values)

    if start_at_zero:
        minimum = min(
            0.0,
            minimum,
        )
    else:
        span = maximum - minimum

        padding = max(
            1.0,
            span * 0.08,
        )

        minimum -= padding
        maximum += padding

    if maximum <= minimum:
        maximum = minimum + 1.0

    def x_position(
        elapsed_s: float,
    ) -> float:
        return (
            left
            + elapsed_s
            / max_elapsed
            * plot_width
        )

    def y_position(
        value: float,
    ) -> float:
        return (
            top
            + (
                maximum - value
            )
            / (
                maximum - minimum
            )
            * plot_height
        )

    def build_paths(
        samples: tuple[
            StoredPftSample, ...
        ],
    ) -> list[str]:

        paths: list[str] = []
        current_path: list[str] = []

        for sample in samples:
            raw_value = getattr(
                sample,
                field,
            )

            if raw_value is None:
                if current_path:
                    paths.append(
                        " ".join(current_path)
                    )
                    current_path = []

                continue

            value = (
                float(raw_value)
                * multiplier
            )

            x = x_position(
                sample.elapsed_s
            )

            y = y_position(
                value
            )

            command = (
                "M"
                if not current_path
                else "L"
            )

            current_path.append(
                f"{command} "
                f"{x:.2f} "
                f"{y:.2f}"
            )

        if current_path:
            paths.append(
                " ".join(current_path)
            )

        return paths

    def build_hover_slots() -> list[str]:
        def values_by_time(
            samples: tuple[
                StoredPftSample, ...
            ],
        ) -> dict[
            float,
            tuple[float, float],
        ]:
            values: dict[
                float,
                tuple[float, float],
            ] = {}

            for sample in samples:
                raw_value = getattr(
                    sample,
                    field,
                )

                if raw_value is None:
                    continue

                key = round(
                    float(sample.elapsed_s),
                    3,
                )

                values[key] = (
                    float(sample.elapsed_s),
                    float(raw_value)
                    * multiplier,
                )

            return values

        reference_by_time = (
            values_by_time(
                reference_samples
            )
        )

        current_by_time = (
            values_by_time(
                current_samples
            )
        )

        keys = sorted(
            set(reference_by_time)
            | set(current_by_time)
        )

        if not keys:
            return []

        elapsed_values: list[float] = []

        for key in keys:
            if key in reference_by_time:
                elapsed_values.append(
                    reference_by_time[
                        key
                    ][0]
                )
            else:
                elapsed_values.append(
                    current_by_time[
                        key
                    ][0]
                )

        x_values = [
            x_position(elapsed)
            for elapsed in elapsed_values
        ]

        signal_name = (
            title.removesuffix("(t)")
        )

        output: list[str] = []

        box_width = 235.0

        for index, key in enumerate(keys):
            elapsed = elapsed_values[
                index
            ]

            x = x_values[index]

            if index == 0:
                hit_left = left
            else:
                hit_left = (
                    x_values[index - 1]
                    + x
                ) / 2.0

            if index == len(keys) - 1:
                hit_right = (
                    width - right
                )
            else:
                hit_right = (
                    x
                    + x_values[index + 1]
                ) / 2.0

            hit_width = max(
                1.0,
                hit_right - hit_left,
            )

            reference_value = None
            current_value = None

            if key in reference_by_time:
                reference_value = (
                    reference_by_time[
                        key
                    ][1]
                )

            if key in current_by_time:
                current_value = (
                    current_by_time[
                        key
                    ][1]
                )

            reference_display = (
                None
                if reference_value is None
                else f"{reference_value:.{digits}f}"
            )

            current_display = (
                None
                if current_value is None
                else f"{current_value:.{digits}f}"
            )

            same_display_value = (
                reference_display is not None
                and current_display is not None
                and reference_display
                == current_display
            )

            box_height = (
                47.0
                if same_display_value
                else 64.0
            )

            time_label = (
                _time_label_hhmmss(
                    elapsed
                )
            )

            stage_label = (
                _stage_name_for_elapsed(
                    elapsed
                )
            )

            if x < (
                left
                + plot_width / 2.0
            ):
                box_x = x + 12.0
            else:
                box_x = (
                    x
                    - box_width
                    - 12.0
                )

            box_x = max(
                left,
                min(
                    box_x,
                    width
                    - right
                    - box_width,
                ),
            )

            point_y_values: list[
                float
            ] = []

            if reference_value is not None:
                point_y_values.append(
                    y_position(
                        reference_value
                    )
                )

            if current_value is not None:
                point_y_values.append(
                    y_position(
                        current_value
                    )
                )

            if point_y_values:
                focus_y = (
                    sum(point_y_values)
                    / len(point_y_values)
                )
            else:
                focus_y = (
                    top
                    + plot_height / 2.0
                )

            vertical_gap = 12.0

            plot_mid_y = (
                top
                + plot_height / 2.0
            )

            if focus_y <= plot_mid_y:
                box_y = (
                    focus_y
                    + vertical_gap
                )
            else:
                box_y = (
                    focus_y
                    - box_height
                    - vertical_gap
                )

            box_y = max(
                top + 4.0,
                min(
                    box_y,
                    top
                    + plot_height
                    - box_height
                    - 4.0,
                ),
            )

            output.append(
                f'<g class="hover-slot" '
                f'data-hover-key="{key:.3f}">'
            )

            output.append(
                f'<rect '
                f'x="{hit_left:.2f}" '
                f'y="{top:.2f}" '
                f'width="{hit_width:.2f}" '
                f'height="{plot_height:.2f}" '
                f'class="hover-hit"/>'
            )

            output.append(
                f'<line '
                f'x1="{x:.2f}" '
                f'y1="{top:.2f}" '
                f'x2="{x:.2f}" '
                f'y2="{top + plot_height:.2f}" '
                f'class="hover-cursor"/>'
            )

            if reference_value is not None:
                reference_y = y_position(
                    reference_value
                )

                output.append(
                    f'<circle '
                    f'cx="{x:.2f}" '
                    f'cy="{reference_y:.2f}" '
                    f'r="4" '
                    f'class="hover-reference"/>'
                )

            if current_value is not None:
                current_y = y_position(
                    current_value
                )

                output.append(
                    f'<circle '
                    f'cx="{x:.2f}" '
                    f'cy="{current_y:.2f}" '
                    f'r="4" '
                    f'class="hover-current"/>'
                )

            output.append(
                f'<rect '
                f'x="{box_x:.2f}" '
                f'y="{box_y:.2f}" '
                f'width="{box_width:.2f}" '
                f'height="{box_height:.2f}" '
                f'rx="6" '
                f'class="hover-box"/>'
            )

            output.append(
                f'<text '
                f'x="{box_x + 10:.2f}" '
                f'y="{box_y + 16:.2f}" '
                f'class="hover-time">'
                f'{escape(signal_name)}'
                f'({escape(time_label)})'
                f' · {escape(stage_label)}'
                f'</text>'
            )

            if same_display_value:
                equal_text = (
                    f"{reference_display} "
                    f"{unit} · "
                    "Reference = Current"
                )

                output.append(
                    f'<text '
                    f'x="{box_x + 10:.2f}" '
                    f'y="{box_y + 38:.2f}" '
                    f'class="hover-value-equal">'
                    f'{escape(equal_text)}'
                    f'</text>'
                )

            else:
                reference_text = (
                    "—"
                    if reference_display is None
                    else (
                        f"{reference_display} "
                        f"{unit}"
                    )
                )

                current_text = (
                    "—"
                    if current_display is None
                    else (
                        f"{current_display} "
                        f"{unit}"
                    )
                )

                output.append(
                    f'<text '
                    f'x="{box_x + 10:.2f}" '
                    f'y="{box_y + 36:.2f}" '
                    f'class="hover-value-reference">'
                    f'Reference: '
                    f'{escape(reference_text)}'
                    f'</text>'
                )

                output.append(
                    f'<text '
                    f'x="{box_x + 10:.2f}" '
                    f'y="{box_y + 53:.2f}" '
                    f'class="hover-value-current">'
                    f'Current: '
                    f'{escape(current_text)}'
                    f'</text>'
                )

            output.append(
                '</g>'
            )

        return output

    def build_observed_markers(
        markers: dict[str, float] | None,
        *,
        line_class: str,
        label_class: str,
        text_anchor: str,
        text_dx: float,
    ) -> list[str]:
        if not markers:
            return []

        fragments: list[str] = []

        for label, elapsed in markers.items():
            if elapsed > max_elapsed:
                continue

            x = x_position(
                elapsed
            )

            fragments.append(
                f'<line '
                f'x1="{x:.2f}" '
                f'y1="{top}" '
                f'x2="{x:.2f}" '
                f'y2="{top + plot_height}" '
                f'class="{line_class}"/>'
            )

            fragments.append(
                f'<text '
                f'x="{x + text_dx:.2f}" '
                f'y="{top + 26:.2f}" '
                f'class="{label_class}" '
                f'text-anchor="{text_anchor}">'
                f'{escape(label)}'
                f'</text>'
            )

        return fragments

    fragments: list[str] = [
        '<div class="chart-panel">',
        f'<h3>{escape(title)}</h3>',
        (
            '<div class="legend">'
            '<span><i class="legend-ref"></i>'
            'Reference</span>'
            '<span><i class="legend-current"></i>'
            'Current</span>'
            '</div>'
        ),
        '<div class="chart-scroll">',
        (
            f'<svg class="trace-chart" '
            f'viewBox="0 0 {width} {height}" '
            f'role="img" '
            f'aria-label="{escape(title)}">'
        ),
    ]

    # PFT-RUN v0.1 nominal stage boundaries.
    stage_boundaries = (
        (0.0, "PRE"),
        (120.0, "P0"),
        (300.0, "P1"),
        (480.0, "P2"),
        (660.0, "REC"),
        (780.0, ""),
    )

    for elapsed, label in stage_boundaries:
        if elapsed > max_elapsed:
            continue

        x = x_position(
            elapsed
        )

        fragments.append(
            f'<line '
            f'x1="{x:.2f}" '
            f'y1="{top}" '
            f'x2="{x:.2f}" '
            f'y2="{top + plot_height}" '
            f'class="stage-line"/>'
        )

        if label:
            fragments.append(
                f'<text '
                f'x="{x + 5:.2f}" '
                f'y="{top + 13:.2f}" '
                f'class="stage-label">'
                f'{escape(label)}'
                f'</text>'
            )

    # Horizontal grid / y labels.
    for tick in range(5):
        fraction = tick / 4.0

        value = (
            maximum
            - fraction
            * (
                maximum - minimum
            )
        )

        y = (
            top
            + fraction
            * plot_height
        )

        fragments.append(
            f'<line '
            f'x1="{left}" '
            f'y1="{y:.2f}" '
            f'x2="{width - right}" '
            f'y2="{y:.2f}" '
            f'class="grid-line"/>'
        )

        fragments.append(
            f'<text '
            f'x="{left - 8}" '
            f'y="{y + 4:.2f}" '
            f'class="axis-label" '
            f'text-anchor="end">'
            f'{value:.1f}'
            f'</text>'
        )

    # Time labels.
    for elapsed in (
        0.0,
        120.0,
        300.0,
        480.0,
        660.0,
        780.0,
    ):
        if elapsed > max_elapsed:
            continue

        x = x_position(
            elapsed
        )

        fragments.append(
            f'<text '
            f'x="{x:.2f}" '
            f'y="{height - 15}" '
            f'class="axis-label" '
            f'text-anchor="middle">'
            f'{_time_label(elapsed)}'
            f'</text>'
        )

    fragments.extend(
        build_observed_markers(
            reference_markers,
            line_class="observed-marker-reference",
            label_class="observed-label-reference",
            text_anchor="end",
            text_dx=-4.0,
        )
    )

    fragments.extend(
        build_observed_markers(
            current_markers,
            line_class="observed-marker-current",
            label_class="observed-label-current",
            text_anchor="start",
            text_dx=4.0,
        )
    )

    for path in build_paths(
        reference_samples
    ):
        fragments.append(
            f'<path '
            f'd="{path}" '
            f'class="trace-reference"/>'
        )

    for path in build_paths(
        current_samples
    ):
        fragments.append(
            f'<path '
            f'd="{path}" '
            f'class="trace-current"/>'
        )

    fragments.extend(
        build_hover_slots()
    )

    fragments.append(
        f'<text '
        f'x="8" '
        f'y="18" '
        f'class="unit-label">'
        f'{escape(unit)}'
        f'</text>'
    )

    fragments.extend(
        [
            "</svg>",
            "</div>",
            "</div>",
        ]
    )

    return "".join(
        fragments
    )