from __future__ import annotations

import hashlib
import importlib
import inspect
from pathlib import Path
import sys


MODULE_NAMES = (
    "app.services.athlete_state_scientific_view",
    "app.services.athlete_state",
    "app.services.scientific_assessment",
    "app.services.capacity_state",
    "app.api.routes.coach",
)

TEST_RELATIVES = (
    Path("apps/api/tests/test_athlete_state_scientific_view.py"),
    Path("apps/api/tests/test_athlete_state.py"),
    Path("apps/api/tests/test_scientific_assessment.py"),
    Path("apps/api/tests/test_capacity_state.py"),
    Path("apps/api/tests/test_coach_routes.py"),
)

OUTPUT = Path("athlete_state_scientific_view_contract_report.txt")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _describe_module(module_name: str) -> str:
    module = importlib.import_module(module_name)
    source_path = inspect.getsourcefile(module)
    lines = [f"MODULE: {module_name}", f"SOURCE_PATH: {source_path}"]

    if source_path:
        text = Path(source_path).read_text(encoding="utf-8")
        lines.append(f"SOURCE_SHA256: {_sha256(text)}")
    else:
        text = ""
        lines.append("SOURCE_SHA256: <unavailable>")

    lines.append("PUBLIC_CALLABLES:")
    for name, value in sorted(vars(module).items()):
        if name.startswith("_") or not callable(value):
            continue
        if getattr(value, "__module__", None) != module_name:
            continue
        try:
            signature = str(inspect.signature(value))
        except (TypeError, ValueError):
            signature = "<signature unavailable>"
        kind = (
            "async-function"
            if inspect.iscoroutinefunction(value)
            else "function"
            if inspect.isfunction(value)
            else "class"
        )
        lines.append(f"  {kind} {name}{signature}")

    lines.append("\n--- EXACT SOURCE BEGIN ---")
    lines.append(text)
    lines.append("--- EXACT SOURCE END ---\n")
    return "\n".join(lines)


def _describe_test(repo: Path, relative: Path) -> str:
    path = repo / relative
    lines = [f"TEST_PATH: {path}"]
    if not path.exists():
        lines.append("TEST_SOURCE: <not found>")
        return "\n".join(lines)

    text = path.read_text(encoding="utf-8")
    lines.append(f"TEST_SHA256: {_sha256(text)}")
    lines.append("\n--- EXACT TEST SOURCE BEGIN ---")
    lines.append(text)
    lines.append("--- EXACT TEST SOURCE END ---\n")
    return "\n".join(lines)


def main() -> int:
    repo = Path.cwd()
    api_path = repo / "apps" / "api"
    if not api_path.exists():
        print(
            "Run this script from the PaddleTrainerProject repository root.",
            file=sys.stderr,
        )
        return 2

    sys.path.insert(0, str(api_path))
    sections = [
        "PaddleTrainer V22.2 complete AthleteState live-binding contract probe",
        (
            "READ_ONLY: imports modules and reads source files; calls no "
            "application function and writes no DB rows."
        ),
        "",
    ]

    for module_name in MODULE_NAMES:
        try:
            sections.append(_describe_module(module_name))
        except Exception as exc:
            sections.append(
                f"MODULE: {module_name}\n"
                f"ERROR: {type(exc).__name__}: {exc}\n"
            )

    for relative in TEST_RELATIVES:
        sections.append(_describe_test(repo, relative))

    OUTPUT.write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote {OUTPUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
