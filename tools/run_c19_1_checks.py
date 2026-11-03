"""C19.1 frontend regression gate, using the project's installed Node dependencies."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Also build the production frontend.")
    args = parser.parse_args()
    web = Path(__file__).resolve().parents[1] / "apps/web"
    node = shutil.which("node")
    if not node:
        print("Node nem talalhato a PATH-ban.", file=sys.stderr)
        return 1
    checks = [
        ("Frontend regression", [node, "--test", *[
            str(path.relative_to(web)) for path in sorted((web / "tests").glob("*.test.mjs"))
        ]]),
        ("Next route types", [node, "node_modules/next/dist/bin/next", "typegen"]),
        ("TypeScript", [node, "node_modules/typescript/bin/tsc", "--noEmit"]),
        ("ESLint", [node, "node_modules/eslint/bin/eslint.js",
            "src/components/training-options", "src/components/athlete-setup/profile-form.tsx",
            "src/components/athlete-setup/workspace.tsx", "src/components/training-planning/journey.tsx",
            "src/components/planning-cycles/plan-output.tsx",
        ]),
    ]
    if args.build:
        checks.append(("Production build", [node, "node_modules/next/dist/bin/next", "build"]))
    for name, command in checks:
        print(f"C19.1: {name}", flush=True)
        try:
            subprocess.run(command, cwd=web, check=True)
        except subprocess.CalledProcessError as error:
            print(f"A C19.1 tesztkapu megallt: {name}.", file=sys.stderr)
            return error.returncode if error.returncode > 0 else 1
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print("C19.1 TESZTKAPU OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
