"""Portable C20.0 regression gate for stored execution reconciliation."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


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
        ("Backend planning regression", root / "apps/api", [
            sys.executable, "-m", "pytest", "tests/planning", "-q", "--tb=short",
        ]),
        ("Frontend regression", web, [node, "--test", *[
            str(path.relative_to(web)) for path in sorted((web / "tests").glob("*.test.mjs"))
        ]]),
        ("Next route types", web, [node, "node_modules/next/dist/bin/next", "typegen"]),
        ("TypeScript", web, [node, "node_modules/typescript/bin/tsc", "--noEmit"]),
        ("ESLint", web, [node, "node_modules/eslint/bin/eslint.js",
            "src/lib/planning-cycles/execution-reconciliation.ts",
            "src/lib/planning-cycles/training-plan.ts",
            "src/components/planning-cycles/training-plan-feedback.tsx",
        ]),
    ]
    if args.build:
        checks.append(("Production build", web, [node, "node_modules/next/dist/bin/next", "build"]))
    for name, cwd, command in checks:
        print(f"C20.0: {name}", flush=True)
        try:
            subprocess.run(command, cwd=cwd, check=True)
        except subprocess.CalledProcessError as error:
            print(f"A C20.0 tesztkapu megallt: {name}.", file=sys.stderr)
            return error.returncode if error.returncode > 0 else 1
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print("C20.0 TESZTKAPU OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
