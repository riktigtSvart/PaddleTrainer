import argparse
from contextlib import closing
import json
from pathlib import Path
import sys

from app.pft_engine.io.hashing import (
    sha256_file,
)
from app.pft_engine.io.json_output import (
    serialize_pft_output_json,
)
from app.pft_engine.io.tcx import (
    parse_tcx,
)
from app.pft_engine.pft.output_mapper import (
    build_pft_output_contract,
)
from app.pft_engine.pft.processor import (
    process_pft,
)
from app.pft_engine.pft.protocol import (
    pft_run_v01,
)
from app.pft_engine.storage.repository import (
    PftRepository,
    PftReprocessingConflict,
)
from app.pft_engine.storage.sqlite import (
    open_database,
)
from dataclasses import asdict

from app.pft_engine.archive.comparison import (
    PftComparisonIncompatible,
    compare_pft_documents,
)

import webbrowser

from app.pft_engine.reporting.comparison_html import (
    render_pft_comparison_html,
)


def _analyze(
    path: Path,
):
    session = parse_tcx(
        path
    )

    result = process_pft(
        session=session,
        protocol=pft_run_v01(),
    )

    output = build_pft_output_contract(
        session=session,
        result=result,
    )

    return session, output


def _write_text(
    text: str,
    output_path: Path | None,
) -> None:
    if output_path is None:
        print(text)
        return

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        text + "\n",
        encoding="utf-8",
    )

    print(
        f"Written: {output_path}"
    )


def _feature_value(
    result: dict,
    name: str,
):
    for feature in result.get(
        "features",
        [],
    ):
        if feature.get("name") == name:
            return feature.get("value")

    return None


def _format_number(
    value,
) -> str:
    if value is None:
        return "-"

    return f"{float(value):.1f}"


def _format_delta(
    value: float | None,
    *,
    digits: int = 1,
) -> str:
    if value is None:
        return "-"

    return f"{value:+.{digits}f}"


def _format_pct(
    value: float | None,
) -> str:
    if value is None:
        return "-"

    return f"{value:+.1f}%"


def _format_eligibility_change(
    reference: bool,
    current: bool,
) -> str:
    if reference == current:
        return "yes" if current else "no"

    return (
        f"{'yes' if reference else 'no'}"
        "→"
        f"{'yes' if current else 'no'}"
    )


def _extract_observed_markers(
    result: dict,
) -> dict[str, float]:
    markers: dict[str, float] = {}

    for transition in result.get(
        "transitions",
        [],
    ):
        stage = str(
            transition.get(
                "to_stage",
                "",
            )
        ).upper()

        midpoint = transition.get(
            "midpoint_s"
        )

        if (
            stage in {"P1", "P2"}
            and midpoint is not None
        ):
            markers[stage] = float(
                midpoint
            )

    recovery = result.get(
        "recovery_anchor",
        {},
    )

    observed = recovery.get(
        "observed_s"
    )

    if observed is not None:
        markers["REC"] = float(
            observed
        )

    return markers


def _command_analyze(
    args,
) -> int:
    path = Path(args.input)

    _, output = _analyze(
        path
    )

    text = serialize_pft_output_json(
        output,
        indent=2 if args.pretty else None,
    )

    _write_text(
        text,
        (
            Path(args.output)
            if args.output
            else None
        ),
    )

    return 0


def _command_import(
    args,
) -> int:
    path = Path(args.input)

    session, output = _analyze(
        path
    )

    result_json = (
        serialize_pft_output_json(
            output
        )
    )

    fingerprint = sha256_file(
        path
    )

    with closing(
        open_database(args.db)
    ) as connection:

        repository = PftRepository(
            connection
        )

        result = repository.import_session(
            source_filename=path.name,
            source_sha256=fingerprint,
            output=output,
            result_json=result_json,
        )

        repository.replace_samples(
            session_id=result.session_id,
            samples=session.samples,
        )

    print(
        f"{result.status.value} "
        f"id={result.session_id} "
        f"sha256={fingerprint}"
    )

    return 0


def _command_list(
    args,
) -> int:

    with closing(
        open_database(args.db)
    ) as connection:

        repository = PftRepository(
            connection
        )

        sessions = repository.list_sessions(
            limit=args.limit
        )

    print(
        f"{'ID':>4} "
        f"{'DATE':<10} "
        f"{'QUALITY':<7} "
        f"{'PROTOCOL':<12} "
        f"{'P1 HR':>7} "
        f"{'P2 HR':>7} "
        f"{'HRR60':>7}"
    )

    for session in sessions:
        result = json.loads(
            session.result_json
        )

        p1 = _feature_value(
            result,
            "HR_P1_MEDIAN",
        )

        p2 = _feature_value(
            result,
            "HR_P2_MEDIAN",
        )

        hrr60 = _feature_value(
            result,
            "HRR60",
        )

        protocol = (
            f"{session.protocol_name}"
            f"-{session.protocol_version}"
        )

        print(
            f"{session.id:>4} "
            f"{session.started_at[:10]:<10} "
            f"{session.quality_grade:<7} "
            f"{protocol:<12} "
            f"{_format_number(p1):>7} "
            f"{_format_number(p2):>7} "
            f"{_format_number(hrr60):>7}"
        )

    return 0


def _command_show(
    args,
) -> int:

    with closing(
        open_database(args.db)
    ) as connection:

        repository = PftRepository(
            connection
        )

        session = repository.get_session(
            args.session_id
        )

    if session is None:
        print(
            f"PFT session not found: "
            f"{args.session_id}",
            file=sys.stderr,
        )

        return 2

    if args.pretty:
        parsed = json.loads(
            session.result_json
        )

        print(
            json.dumps(
                parsed,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
        )
    else:
        print(
            session.result_json
        )

    return 0


def _command_compare(
    args,
) -> int:

    with closing(
        open_database(args.db)
    ) as connection:

        repository = PftRepository(
            connection
        )

        reference_session = (
            repository.get_session(
                args.reference_id
            )
        )

        current_session = (
            repository.get_session(
                args.current_id
            )
        )

        reference_samples = (
            repository.get_samples(
                args.reference_id
            )
        )

        current_samples = (
            repository.get_samples(
                args.current_id
            )
        )

    if reference_session is None:
        print(
            "Reference PFT session "
            f"not found: {args.reference_id}",
            file=sys.stderr,
        )

        return 2

    if current_session is None:
        print(
            "Current PFT session "
            f"not found: {args.current_id}",
            file=sys.stderr,
        )

        return 2

    reference = json.loads(
        reference_session.result_json
    )

    current = json.loads(
        current_session.result_json
    )

    reference_markers = (
        _extract_observed_markers(
            reference
        )
    )

    current_markers = (
        _extract_observed_markers(
            current
        )
    )

    try:
        comparison = (
            compare_pft_documents(
                reference=reference,
                current=current,
            )
        )

    except PftComparisonIncompatible as exc:
        print(
            "PFT sessions are not "
            "scientifically comparable:",
            file=sys.stderr,
        )

        for issue in exc.issues:
            print(
                f"  - {issue}",
                file=sys.stderr,
            )

        return 3

    if args.open and not args.html:
        print(
            "--open requires --html.",
            file=sys.stderr,
        )

        return 2

    if args.html:
        html_path = Path(
            args.html
        )

        html = render_pft_comparison_html(
            comparison=comparison,
            reference_id=args.reference_id,
            current_id=args.current_id,
            reference_samples=reference_samples,
            current_samples=current_samples,
            reference_markers=reference_markers,
            current_markers=current_markers,
        )

        html_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        html_path.write_text(
            html,
            encoding="utf-8",
        )

        print(
            f"HTML report written: "
            f"{html_path}"
        )

        if args.open:
            webbrowser.open(
                html_path
                .resolve()
                .as_uri()
            )

    if args.json:
        print(
            json.dumps(
                asdict(comparison),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
        )

        return 0

    print(
        "PFT COMPARISON"
    )

    print(
        f"Reference: "
        f"id={args.reference_id} "
        f"{comparison.reference_started_at}"
    )

    print(
        f"Current:   "
        f"id={args.current_id} "
        f"{comparison.current_started_at}"
    )

    print(
        f"Protocol:  "
        f"{comparison.protocol_name}-"
        f"{comparison.protocol_version}"
    )

    print(
        "Quality:   "
        f"{comparison.reference_session_quality_grade}"
        " → "
        f"{comparison.current_session_quality_grade}"
    )

    print()

    print(
        f"{'FEATURE':<20} "
        f"{'OLD':>9} "
        f"{'NEW':>9} "
        f"{'DELTA':>9} "
        f"{'CHANGE':>9} "
        f"{'Q':>5} "
        f"{'BASE':>9}"
    )

    for feature in comparison.features:
        old = (
            "-"
            if feature.reference_value is None
            else f"{feature.reference_value:.2f}"
        )

        new = (
            "-"
            if feature.current_value is None
            else f"{feature.current_value:.2f}"
        )

        quality = (
            f"{feature.reference_quality_grade}"
            "→"
            f"{feature.current_quality_grade}"
        )

        baseline = (
            _format_eligibility_change(
                feature.reference_baseline_eligible,
                feature.current_baseline_eligible,
            )
        )

        print(
            f"{feature.name:<20} "
            f"{old:>9} "
            f"{new:>9} "
            f"{_format_delta(feature.delta):>9} "
            f"{_format_pct(feature.relative_change_pct):>9} "
            f"{quality:>5} "
            f"{baseline:>9}"
        )

    if comparison.rhri:
        print()
        print("RHRI")

        print(
            f"{'METHOD':<12} "
            f"{'STAGE':<6} "
            f"{'OLD':>9} "
            f"{'NEW':>9} "
            f"{'DELTA':>9} "
            f"{'CHANGE':>9}"
        )

        for value in comparison.rhri:
            print(
                f"{value.method:<12} "
                f"{value.stage.upper():<6} "
                f"{value.reference_value_bpm_per_s:>9.4f} "
                f"{value.current_value_bpm_per_s:>9.4f} "
                f"{_format_delta(value.delta_bpm_per_s, digits=4):>9} "
                f"{_format_pct(value.relative_change_pct):>9}"
            )

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paddletrainer-physiology",
        description=(
            "Standalone PaddleTrainer "
            "physiological analysis tools."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    analyze = subparsers.add_parser(
        "analyze-pft",
        help=(
            "Analyze a TCX PFT without "
            "storing it."
        ),
    )

    analyze.add_argument(
        "input",
    )

    analyze.add_argument(
        "--output",
    )

    analyze.add_argument(
        "--pretty",
        action="store_true",
    )

    analyze.set_defaults(
        handler=_command_analyze
    )

    import_pft = subparsers.add_parser(
        "import-pft",
        help=(
            "Analyze and store a TCX PFT."
        ),
    )

    import_pft.add_argument(
        "input",
    )

    import_pft.add_argument(
        "--db",
    )

    import_pft.set_defaults(
        handler=_command_import
    )

    list_pft = subparsers.add_parser(
        "list-pft",
        help="List stored PFT sessions.",
    )

    list_pft.add_argument(
        "--db",
    )

    list_pft.add_argument(
        "--limit",
        type=int,
        default=100,
    )

    list_pft.set_defaults(
        handler=_command_list
    )

    show_pft = subparsers.add_parser(
        "show-pft",
        help=(
            "Show the stored JSON result "
            "of one PFT."
        ),
    )

    show_pft.add_argument(
        "session_id",
        type=int,
    )

    show_pft.add_argument(
        "--db",
    )

    show_pft.add_argument(
        "--pretty",
        action="store_true",
    )

    show_pft.set_defaults(
        handler=_command_show
    )

    compare_pft = subparsers.add_parser(
        "compare-pft",
        help=(
            "Compare two stored PFT sessions."
        ),
    )

    compare_pft.add_argument(
        "reference_id",
        type=int,
        help=(
            "Earlier/reference PFT session ID."
        ),
    )

    compare_pft.add_argument(
        "current_id",
        type=int,
        help=(
            "Current/newer PFT session ID."
        ),
    )

    compare_pft.add_argument(
        "--db",
    )

    compare_pft.add_argument(
        "--json",
        action="store_true",
        help=(
            "Return machine-readable comparison JSON."
        ),
    )

    compare_pft.add_argument(
        "--html",
        metavar="PATH",
        help=(
            "Write a self-contained graphical "
            "HTML comparison report."
        ),
    )

    compare_pft.add_argument(
        "--open",
        action="store_true",
        help=(
            "Open the generated HTML report "
            "in the default browser. "
            "Requires --html."
        ),
    )

    compare_pft.set_defaults(
        handler=_command_compare
    )

    return parser


def main(
    argv: list[str] | None = None,
) -> int:
    parser = _build_parser()

    args = parser.parse_args(
        argv
    )

    try:
        return args.handler(args)
    except PftReprocessingConflict as exc:
        print(str(exc), file=sys.stderr)
        return 2
