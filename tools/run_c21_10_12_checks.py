"""C21.10.12: UTF-8 instructions, legacy Windows reads and explicit work sets."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--focused-backend', action='store_true', help='Run the encoding/calendar regression subset before the full frontend gate.')
    parser.add_argument('--frontend-only', action='store_true', help='Skip backend only if it passed with these same sources.')
    args = parser.parse_args()
    if args.frontend_only and args.focused_backend:
        parser.error('--frontend-only and --focused-backend cannot be combined')
    root = Path(__file__).resolve().parents[1]
    web = root / 'apps/web'
    node = shutil.which('node')
    if not node:
        print('Node nem talalhato a PATH-ban.', file=sys.stderr)
        return 1
    lint = ['src/components/planning-cycles/plan-output.tsx', 'src/components/planning-cycles/workout-instructions.tsx', 'src/lib/calendar/contracts.ts', 'src/lib/planning-cycles/workout-instructions.ts', 'tests/c21-10-12-instruction-encoding.test.mjs']
    checks = [
        ('Frontend regression', [node, '--test', *[str(p.relative_to(web)) for p in sorted((web / 'tests').glob('*.test.mjs'))]], web),
        ('Next route types', [node, 'node_modules/next/dist/bin/next', 'typegen'], web),
        ('TypeScript', [node, 'node_modules/typescript/bin/tsc', '--noEmit'], web),
        ('ESLint', [node, 'node_modules/eslint/bin/eslint.js', '--max-warnings=0', *lint], web),
        ('Production build', [node, 'node_modules/next/dist/bin/next', 'build'], web),
    ]
    if not args.frontend_only:
        backend = ['tests/planning/test_c21_10_12_instruction_encoding.py', 'tests/planning/test_c21_10_11_calibrated_calendar.py', 'tests/planning/test_c21_10_10_workout_instructions.py', 'tests/planning/test_c21_10_7_calendar_cycles.py', 'tests/planning/test_c21_10_2_calendar_choices.py'] if args.focused_backend else ['tests/planning']
        checks.insert(0, ('Backend planning regression', [sys.executable, '-m', 'pytest', *backend, '-q', '--disable-warnings'], root / 'apps/api'))
    for name, command, folder in checks:
        print('C21.10.12: ' + name, flush=True)
        try:
            subprocess.run(command, cwd=folder, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.10.12 tesztkapu megallt: ' + name + '.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.10.12 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
