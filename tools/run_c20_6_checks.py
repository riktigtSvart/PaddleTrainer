"""Portable C20.6 regression gate for the first real guided strength reference occasion."""

import argparse
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="paddletrainer-c20-6-checks-") as temporary:
        return run(Path(temporary))


def run(report_directory):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Also build the production frontend.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    web = root / "apps/web"
    node = shutil.which("node")
    if not node:
        print("Node nem talalhato a PATH-ban.", file=sys.stderr)
        return 1
    print("C20.6: Backend planning test collection", flush=True)
    try:
        collected = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/planning", "--collect-only", "-q"],
            cwd=root / "apps/api", check=True, capture_output=True, text=True,
        )
    except (subprocess.CalledProcessError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    counts = Counter(line.split("::")[0] for line in collected.stdout.splitlines()
                     if line.startswith("tests/planning/") and "::" in line)
    if not counts:
        print("Nem gyujtheto ossze a teljes backend tesztkeszlet.", file=sys.stderr)
        return 1
    # Separate processes bound retained test state; every collected file runs once.
    groups, sizes = [[], [], []], [0, 0, 0]
    for filename, count in sorted(counts.items(), key=lambda entry: (-entry[1], entry[0])):
        index = min(range(3), key=lambda i: sizes[i])
        groups[index].append(filename)
        sizes[index] += count
    reports = {}
    checks = []
    for index, files in enumerate(groups):
        if not files:
            continue
        name = f"Backend planning regression ({index + 1}/3)"
        report = report_directory / f"backend-{index}.xml"
        reports[name] = (report, sizes[index])
        checks.append((name, root / "apps/api", [sys.executable, "-m", "pytest", *sorted(files),
                      "-q", "--tb=short", "--junitxml", str(report)]))
    checks.extend([
        ("Frontend regression", web, [node, "--test", *[
            str(path.relative_to(web)) for path in sorted((web / "tests").glob("*.test.mjs"))
        ]]),
        ("Next route types", web, [node, "node_modules/next/dist/bin/next", "typegen"]),
        ("TypeScript", web, [node, "node_modules/typescript/bin/tsc", "--noEmit"]),
        ("ESLint", web, [node, "node_modules/eslint/bin/eslint.js",
            "src/lib/guided-strength", "src/components/guided-strength", "src/app/strength-assessment/page.tsx", "tests/guided-strength.test.mjs",
            "src/lib/planning-cycles/strength-assessment.ts",
            "src/components/planning-cycles/strength-assessment.tsx",
            "tests/assessed-strength.test.mjs",
            "src/lib/initial-assessment", "src/components/initial-assessment",
            "src/app/initial-assessment/page.tsx", "src/components/training-planning/journey.tsx",
            "src/components/ui/app-shell.tsx", "src/lib/planning-goals/proxy.ts",
            "tests/initial-assessment.test.mjs",
            "src/lib/training-options/strength-catalog.ts",
            "src/lib/training-options/contracts.ts",
            "src/components/training-options/location-editor.tsx",
            "src/components/training-options/strength-equipment.tsx",
            "src/components/training-options/equipment-illustration.tsx",
            "src/components/training-options/workspace.tsx",
            "tests/strength-catalog.test.mjs", "tests/strength-machines.test.mjs", "tests/strength-bars.test.mjs",
            "src/lib/planning-cycles/prescription-context.ts",
            "src/lib/planning-cycles/mesocycle-coordination.ts",
            "src/components/planning-cycles/mesocycle-summary.tsx",
            "src/components/planning-cycles/training-plan.tsx",
            "src/lib/planning-cycles/training-plan.ts",
            "src/lib/planning-cycles/plan-view.ts",
            "src/components/planning-cycles/plan-output.tsx",
            "src/components/planning-cycles/training-plan-feedback.tsx",
            "tests/prescriptions.test.mjs", "tests/preparation.test.mjs",
            "tests/mesocycle-coordination.test.mjs",
        ]),
    ])
    if args.build:
        checks.append(("Production build", web, [node, "node_modules/next/dist/bin/next", "build"]))
    for name, cwd, command in checks:
        print(f"C20.6: {name}", flush=True)
        try:
            subprocess.run(command, cwd=cwd, check=True)
            if name in reports:
                backend_report, expected_count = reports[name]
                if not backend_report.is_file():
                    print("A backend tesztfutas nem adott befejezett eredmenyt.", file=sys.stderr)
                    return 1
                suites = ET.parse(backend_report).getroot()
                if sum(int(suite.get("tests", "0")) for suite in suites) != expected_count or any(
                    int(suite.get(key, "0")) for suite in suites for key in ("failures", "errors")
                ):
                    print("A backend osszesitett teszteredmenye hibas.", file=sys.stderr)
                    return 1
        except subprocess.CalledProcessError as error:
            print(f"A C20.6 tesztkapu megallt: {name}.", file=sys.stderr)
            return error.returncode if error.returncode > 0 else 1
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print("C20.6 TESZTKAPU OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
