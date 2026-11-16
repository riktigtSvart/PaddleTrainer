"""C21.10.2: calendar-day alternatives, accepted workout purpose and indicators."""
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    web = root / 'apps/web'
    node = shutil.which('node')
    if not node:
        print('Node nem talalhato a PATH-ban.', file=sys.stderr)
        return 1
    lint = [
        'src/lib/calendar/contracts.ts', 'src/lib/calendar/training-alternatives.ts',
        'src/lib/calendar/event-preview.ts', 'src/lib/planning-cycles/training-plan.ts',
        'src/components/calendar/event-detail.tsx', 'src/components/calendar/workout-alternatives.tsx',
        'src/components/calendar/alternative-badge.tsx', 'src/components/calendar/time-grid.tsx',
        'src/components/calendar/period-grid.tsx', 'src/components/calendar/workspace.tsx',
        'src/components/planning-cycles/plan-output.tsx', 'tests/c21-10-2-calendar-choices.test.mjs',
    ]
    checks = [
        ('Backend planning regression', [sys.executable, '-m', 'pytest', 'tests/planning', '-q'], root / 'apps/api'),
        ('Frontend regression', [node, '--test', *[str(p.relative_to(web)) for p in sorted((web / 'tests').glob('*.test.mjs'))]], web),
        ('Next route types', [node, 'node_modules/next/dist/bin/next', 'typegen'], web),
        ('TypeScript', [node, 'node_modules/typescript/bin/tsc', '--noEmit'], web),
        ('ESLint', [node, 'node_modules/eslint/bin/eslint.js', *lint], web),
        ('Production build', [node, 'node_modules/next/dist/bin/next', 'build'], web),
    ]
    for name, command, folder in checks:
        print('C21.10.2: ' + name, flush=True)
        try:
            subprocess.run(command, cwd=folder, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.10.2 tesztkapu megallt: ' + name + '.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.10.2 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
