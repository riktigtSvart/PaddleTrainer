"""C21.10.7: calendar cycle goals, observed coverage and accepted wave colours."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-only', action='store_true', help='Skip backend only if it passed with these same sources.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    web = root / 'apps/web'
    node = shutil.which('node')
    if not node:
        print('Node nem talalhato a PATH-ban.', file=sys.stderr)
        return 1
    lint = [
        'src/lib/calendar/cycles.ts', 'src/lib/calendar/cycle-context.ts',
        'src/lib/calendar/cycle-coverage.ts', 'src/lib/calendar/visibility.ts', 'src/lib/calendar/proxy.ts',
        'src/components/calendar/cycle-detail.tsx', 'src/components/calendar/cycle-markers.tsx',
        'src/components/calendar/use-cycle-context.ts', 'src/components/calendar/use-visibility.ts',
        'src/components/calendar/time-grid.tsx', 'src/components/calendar/period-grid.tsx',
        'src/components/calendar/overview-calendar.tsx', 'src/components/calendar/workspace.tsx',
        'tests/c21-10-7-calendar-cycles.test.mjs',
    ]
    checks = [
        ('Frontend regression', [node, '--test', *[str(p.relative_to(web)) for p in sorted((web / 'tests').glob('*.test.mjs'))]], web),
        ('Next route types', [node, 'node_modules/next/dist/bin/next', 'typegen'], web),
        ('TypeScript', [node, 'node_modules/typescript/bin/tsc', '--noEmit'], web),
        ('ESLint', [node, 'node_modules/eslint/bin/eslint.js', '--max-warnings=0', *lint], web),
        ('Production build', [node, 'node_modules/next/dist/bin/next', 'build'], web),
    ]
    if not args.frontend_only:
        checks.insert(0, ('Backend planning regression', [sys.executable, '-m', 'pytest', 'tests/planning', '-q', '--disable-warnings'], root / 'apps/api'))
    for name, command, folder in checks:
        print('C21.10.7: ' + name, flush=True)
        try:
            subprocess.run(command, cwd=folder, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.10.7 tesztkapu megallt: ' + name + '.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.10.7 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
