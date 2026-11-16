"""C21.10.13: independent strength volume, owned actual logs and source proofs."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--focused-backend', action='store_true', help='Run the strength/log/calendar regression subset before the full frontend gate.')
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
    lint = ['src/components/planning-cycles/plan-output.tsx', 'src/components/planning-cycles/workout-instructions.tsx', 'src/components/session-analysis/strength-log.tsx', 'src/components/session-analysis/workspace.tsx', 'src/lib/calendar/proxy.ts', 'src/lib/planning-cycles/mesocycle-coordination.ts', 'src/lib/planning-cycles/prescription-context.ts', 'src/lib/planning-cycles/sport-availability.ts', 'src/lib/planning-cycles/strength-assessment.ts', 'src/lib/planning-cycles/strength-starter.ts', 'src/lib/planning-cycles/strength-workout.ts', 'src/lib/planning-cycles/swimming-prescription.ts', 'src/lib/planning-cycles/training-distribution.ts', 'src/lib/planning-cycles/training-load.ts', 'src/lib/planning-cycles/workout-instructions.ts', 'src/lib/session-analysis/strength-log.ts', 'tests/c21-10-13-strength-workouts.test.mjs']
    checks = [
        ('Frontend regression', [node, '--test', *[str(p.relative_to(web)) for p in sorted((web / 'tests').glob('*.test.mjs'))]], web),
        ('Next route types', [node, 'node_modules/next/dist/bin/next', 'typegen'], web),
        ('TypeScript', [node, 'node_modules/typescript/bin/tsc', '--noEmit'], web),
        ('ESLint', [node, 'node_modules/eslint/bin/eslint.js', '--max-warnings=0', *lint], web),
        ('Production build', [node, 'node_modules/next/dist/bin/next', 'build'], web),
    ]
    if not args.frontend_only:
        backend = ['tests/planning/test_c21_10_13_strength_workouts.py', 'tests/planning/test_c21_10_12_instruction_encoding.py', 'tests/planning/test_c21_10_11_calibrated_calendar.py', 'tests/planning/test_c21_10_10_workout_instructions.py', 'tests/planning/test_c21_10_9_profile_sources.py', 'tests/planning/test_c21_10_8_strength_and_distribution.py', 'tests/planning/test_p2_4c20_5_assessed_strength.py', 'tests/planning/test_p2_4c20_7_calibration.py'] if args.focused_backend else ['tests/planning']
        checks.insert(0, ('Backend planning regression', [sys.executable, '-m', 'pytest', *backend, '-q', '--disable-warnings'], root / 'apps/api'))
    for name, command, folder in checks:
        print('C21.10.13: ' + name, flush=True)
        try:
            subprocess.run(command, cwd=folder, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.10.13 tesztkapu megallt: ' + name + '.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.10.13 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
