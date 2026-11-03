"""C18.5 checks with the project's Python; no PowerShell execution policy change."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Also build the production frontend.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    web = root / "apps/web"
    node = shutil.which("node")
    if not node:
        print("Node nem talalhato a PATH-ban.", file=sys.stderr)
        return 1
    checks = [
        (root / "apps/api", [sys.executable, "-m", "pytest",
            "tests/planning/test_p2_4c5r2_athlete_setup.py",
            "tests/planning/test_p2_4c18_planning_inputs.py",
            "tests/planning/test_p2_4c18_4_training_plan.py",
            "tests/planning/test_p2_4c18_5_preparation.py",
            "tests/planning/test_p2_4c81_calendar_constraints.py",
            "tests/planning/test_p2_4c81r1_calendar_duration.py",
            "tests/planning/test_p2_4c81r2_segmented_duration.py", "-q"]),
        (web, [node, "--test", *[str(p.relative_to(web)) for p in sorted((web / "tests").glob("*.test.mjs"))]]),
        (web, [node, "node_modules/next/dist/bin/next", "typegen"]),
        (web, [node, "node_modules/typescript/bin/tsc", "--noEmit"]),
        (web, [node, "node_modules/eslint/bin/eslint.js",
            "src/components/athlete-setup", "src/components/planning-cycles/training-plan.tsx",
            "src/components/planning-cycles/training-plan-feedback.tsx",
            "src/components/calendar/duration-details.tsx",
            "src/lib/athlete-setup", "src/lib/calendar/duration-estimate.ts",
            "src/lib/calendar/constraints.ts", "src/lib/planning-cycles/training-plan.ts"]),
    ]
    if args.build:
        checks.append((web, [node, "node_modules/next/dist/bin/next", "build"]))
    try:
        for cwd, command in checks:
            subprocess.run(command, cwd=cwd, check=True)
    except subprocess.CalledProcessError as error:
        print("A C18.5 tesztkapu hibanal megallt.", file=sys.stderr)
        return error.returncode
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 1
    print("C18.5 TESZTKAPU OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
