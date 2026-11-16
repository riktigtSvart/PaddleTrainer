"""C21.10.4: timetable validation and same-tab input recovery."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-backend', action='store_true', help='Run the full backend planning regression instead of the focused timetable tests.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    web = root / 'apps/web'
    node = shutil.which('node')
    if not node:
        print('Node nem talalhato a PATH-ban.', file=sys.stderr)
        return 1
    lint = [
        'src/lib/training-options/contracts.ts',
        'src/lib/training-options/synchronization.ts',
        'src/lib/training-options/slot-validation.ts',
        'src/lib/training-options/schedule-draft.ts',
        'src/components/training-options/use-schedule-draft.ts',
        'src/components/training-options/slot-fields.tsx',
        'src/components/training-options/schedule-editor.tsx',
        'src/components/training-options/workspace.tsx',
        'tests/c21-10-4-schedule-recovery.test.mjs',
    ]
    backend_target = 'tests/planning' if args.with_backend else 'tests/planning/test_c21_10_4_timetable_limits.py'
    checks = [
        ('Backend timetable regression' if not args.with_backend else 'Backend planning regression', [sys.executable, '-m', 'pytest', backend_target, '-q'], root / 'apps/api'),
        ('Frontend regression', [node, '--test', *[str(p.relative_to(web)) for p in sorted((web / 'tests').glob('*.test.mjs'))]], web),
        ('Next route types', [node, 'node_modules/next/dist/bin/next', 'typegen'], web),
        ('TypeScript', [node, 'node_modules/typescript/bin/tsc', '--noEmit'], web),
        ('ESLint', [node, 'node_modules/eslint/bin/eslint.js', *lint], web),
        ('Production build', [node, 'node_modules/next/dist/bin/next', 'build'], web),
    ]
    for name, command, folder in checks:
        print('C21.10.4: ' + name, flush=True)
        try:
            subprocess.run(command, cwd=folder, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.10.4 tesztkapu megallt: ' + name + '.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.10.4 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
