"""C21.9.2 regression gate: running starts, historical evidence and Polar backfill."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-only', action='store_true', help='Skip an already completed backend regression.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    web = root / 'apps/web'
    node = shutil.which('node')
    if not node:
        print('Node nem talalhato a PATH-ban.', file=sys.stderr)
        return 1
    lint = ['src/lib/planning-cycles/prescription-context.ts', 'src/lib/planning-cycles/running-prescription.ts',
        'src/lib/planning-cycles/strength-assessment.ts', 'src/lib/data-connections/contracts.ts',
        'src/lib/data-connections/history-backfill.ts', 'src/components/ui/polar-history-control.tsx',
        'src/components/planning-cycles/plan-output.tsx', 'src/components/planning-data/sport-availability.tsx',
        'src/app/settings/page.tsx', 'tests/c21-9-1-calendar-endurance.test.mjs', 'tests/c21-9-2-running-history.test.mjs']
    checks = [
        ('Frontend regression', [node, '--test', *[str(p.relative_to(web)) for p in sorted((web / 'tests').glob('*.test.mjs'))]], web),
        ('Next route types', [node, 'node_modules/next/dist/bin/next', 'typegen'], web),
        ('TypeScript', [node, 'node_modules/typescript/bin/tsc', '--noEmit'], web),
        ('ESLint', [node, 'node_modules/eslint/bin/eslint.js', *lint], web),
        ('Production build', [node, 'node_modules/next/dist/bin/next', 'build'], web),
    ]
    if not args.frontend_only:
        checks.insert(0, ('Backend planning regression', [sys.executable, '-m', 'pytest', 'tests/planning', '-q'], root / 'apps/api'))
    for name, command, folder in checks:
        print('C21.9.2: ' + name, flush=True)
        try:
            subprocess.run(command, cwd=folder, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.9.2 tesztkapu megallt: ' + name + '.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.9.2 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
