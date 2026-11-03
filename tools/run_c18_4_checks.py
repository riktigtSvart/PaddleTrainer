"""C18.4/R1 checks runnable with the project Python on Windows and Linux."""

import shutil
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    if node is None:
        print("Node nem talalhato a PATH-ban.", file=sys.stderr)
        return 1
    checks = [
        (
            root / "apps/api",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/planning/test_p2_4c18_planning_inputs.py",
                "tests/planning/test_p2_4c18_2_goal_suggestions.py",
                "tests/planning/test_p2_4c18_3_strategy.py",
                "tests/planning/test_p2_4c18_4_training_plan.py",
                "-q",
            ],
        ),
        (
            root / "apps/web",
            [
                node,
                "--test",
                "tests/training-plan.test.mjs",
                "tests/training-plan-feedback.test.mjs",
                "tests/planning-inputs.test.mjs",
                "tests/planning-strategy.test.mjs",
            ],
        ),
        (root / "apps/web", [node, "node_modules/next/dist/bin/next", "typegen"]),
        (root / "apps/web", [node, "node_modules/typescript/bin/tsc", "--noEmit"]),
        (
            root / "apps/web",
            [
                node,
                "node_modules/eslint/bin/eslint.js",
                "src/components/planning-cycles/training-plan.tsx",
                "src/components/planning-cycles/training-plan-feedback.tsx",
                "src/lib/planning-cycles/training-plan.ts",
                "src/lib/planning-goals/proxy.ts",
            ],
        ),
    ]
    try:
        for cwd, command in checks:
            subprocess.run(command, cwd=cwd, check=True)
    except subprocess.CalledProcessError as exc:
        print("A C18.4R1 tesztkapu hibanal megallt.", file=sys.stderr)
        return exc.returncode
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("C18.4R1 TESZTKAPU OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
