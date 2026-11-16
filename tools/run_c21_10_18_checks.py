"""C21.10.18: bounded calendar source reads, cancellation and transient GET recovery."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full-backend', action='store_true', help='Run the full backend planning suite instead of the calendar read, cycle and direct-picker regressions.')
    parser.add_argument('--full-frontend', action='store_true', help='Run every frontend regression instead of the focused alternatives subset.')
    parser.add_argument('--frontend-only', action='store_true', help='Skip backend only if it passed with these same sources.')
    args = parser.parse_args()
    if args.frontend_only and args.full_backend:
        parser.error('--frontend-only and --full-backend cannot be combined')
    root = Path(__file__).resolve().parents[1]
    web = root / 'apps/web'
    node = shutil.which('node')
    if not node:
        print('Node nem talalhato a PATH-ban.', file=sys.stderr)
        return 1
    focused = ['tests/c21-10-18-calendar-reads.test.mjs', 'tests/calendar-workspace.test.mjs', 'tests/calendar-constraints.test.mjs', 'tests/c21-10-7-calendar-cycles.test.mjs', 'tests/c21-10-17-direct-picker.test.mjs', 'tests/c21-10-16-alternative-deadlines.test.mjs', 'tests/c21-10-15-today-variants.test.mjs', 'tests/c21-10-14-strength-alternatives.test.mjs',
               'tests/c21-10-13-strength-workouts.test.mjs', 'tests/c21-10-2-calendar-choices.test.mjs',
               'tests/c21-10-11-calibrated-calendar.test.mjs', 'tests/c21-10-12-instruction-encoding.test.mjs']
    tests = [str(p.relative_to(web)) for p in sorted((web / 'tests').glob('*.test.mjs'))] if args.full_frontend else focused
    lint = ['src/lib/calendar/client.ts', 'src/lib/calendar/read-request.ts', 'src/lib/calendar/proxy.ts',
            'src/lib/calendar/cycle-context.ts', 'src/lib/calendar/constraint-client.ts',
            'tests/c21-10-18-calendar-reads.test.mjs']
    checks = [
        ('Calendar and alternatives frontend regression', [node, '--test', *tests], web),
        ('Next route types', [node, 'node_modules/next/dist/bin/next', 'typegen'], web),
        ('TypeScript', [node, 'node_modules/typescript/bin/tsc', '--noEmit'], web),
        ('ESLint', [node, 'node_modules/eslint/bin/eslint.js', '--max-warnings=0', *lint], web),
        ('Production build', [node, 'node_modules/next/dist/bin/next', 'build'], web),
    ]
    if not args.frontend_only:
        backend = ['tests/planning'] if args.full_backend else ['tests/planning/test_c21_10_18_calendar_reads.py', 'tests/planning/test_c21_10_17_direct_picker.py', 'tests/planning/test_c21_10_16_alternative_deadlines.py', 'tests/planning/test_c21_10_7_calendar_cycles.py']
        checks.insert(0, ('Read-only calendar and day-picker backend regression',
                         [sys.executable, '-m', 'pytest', *backend, '-q', '--disable-warnings'], root / 'apps/api'))
    for name, command, folder in checks:
        print('C21.10.18: ' + name, flush=True)
        try:
            subprocess.run(command, cwd=folder, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.10.18 tesztkapu megallt: ' + name + '.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.10.18 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
