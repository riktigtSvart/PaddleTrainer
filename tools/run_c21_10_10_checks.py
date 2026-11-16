"""C21.10.10: calendar alignment and concrete workout instructions."""
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
    lint = ['src/app/workouts/[id]/page.tsx', 'src/components/calendar/event-detail.tsx', 'src/components/calendar/overview-calendar.tsx', 'src/components/calendar/period-grid.tsx', 'src/components/calendar/use-visibility.ts', 'src/components/calendar/workspace.tsx', 'src/components/planning-cycles/plan-output.tsx', 'src/components/planning-cycles/saved-workout-instructions.tsx', 'src/components/planning-cycles/workout-instructions.tsx', 'src/lib/calendar/contracts.ts', 'src/lib/calendar/cycles.ts', 'src/lib/calendar/overview.ts', 'src/lib/calendar/visibility.ts', 'src/lib/planning-cycles/mesocycle-coordination.ts', 'src/lib/planning-cycles/sport-availability.ts', 'src/lib/planning-cycles/strength-assessment.ts', 'src/lib/planning-cycles/strength-starter.ts', 'src/lib/planning-cycles/swimming-prescription.ts', 'src/lib/planning-cycles/training-distribution.ts', 'src/lib/planning-cycles/training-load.ts', 'src/lib/planning-cycles/training-plan.ts', 'src/lib/planning-cycles/workout-instructions.ts', 'tests/c21-10-10-workout-instructions.test.mjs']
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
        print('C21.10.10: ' + name, flush=True)
        try:
            subprocess.run(command, cwd=folder, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.10.10 tesztkapu megallt: ' + name + '.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.10.10 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
