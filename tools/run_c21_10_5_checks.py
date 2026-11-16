"""C21.10.5: save feedback, calendar cycle markers and goal coverage."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-only', action='store_true', help='Skip backend regression only when it already passed for these sources.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    web = root / 'apps/web'
    node = shutil.which('node')
    if not node:
        print('Node nem talalhato a PATH-ban.', file=sys.stderr)
        return 1
    lint = [
        'src/lib/forms/validation.ts', 'src/lib/calendar/cycles.ts',
        'src/components/calendar/cycle-markers.tsx', 'src/components/calendar/time-grid.tsx',
        'src/components/calendar/period-grid.tsx', 'src/components/calendar/workspace.tsx',
        'src/components/calendar/overview-calendar.tsx',
        'src/components/planning-data/save-actions.tsx', 'src/components/planning-data/sport-availability.tsx',
        'src/components/training-options/schedule-editor.tsx', 'src/components/training-options/current-week.tsx',
        'src/lib/planning-cycles/sport-availability.ts', 'src/lib/planning-cycles/prescription-context.ts',
        'src/lib/planning-cycles/mesocycle-coordination.ts', 'src/lib/planning-cycles/strength-assessment.ts',
        'src/lib/planning-cycles/training-load.ts', 'src/lib/planning-cycles/training-plan.ts',
        'src/components/training-options/use-schedule-draft.ts',
        'src/components/training-options/slot-fields.tsx', 'src/lib/training-options/schedule-draft.ts',
        'src/lib/training-options/slot-validation.ts', 'src/lib/training-options/synchronization.ts',
        'src/lib/training-options/contracts.ts', 'src/components/training-options/workspace.tsx',
        'tests/c21-10-4-schedule-recovery.test.mjs', 'tests/c21-10-5-cycles-validation-goals.test.mjs',
    ]
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
        print('C21.10.5: ' + name, flush=True)
        try:
            subprocess.run(command, cwd=folder, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.10.5 tesztkapu megallt: ' + name + '.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.10.5 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
