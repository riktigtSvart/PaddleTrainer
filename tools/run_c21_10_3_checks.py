"""C21.10.3: calendar preferences and synchronized timetable editors."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-backend', action='store_true', help='Also run the unchanged full backend planning regression.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    web = root / 'apps/web'
    node = shutil.which('node')
    if not node:
        print('Node nem talalhato a PATH-ban.', file=sys.stderr)
        return 1
    lint = [
        'src/lib/calendar/visibility.ts', 'src/components/calendar/use-visibility.ts',
        'src/components/calendar/workspace.tsx',
        'src/lib/training-options/synchronization.ts',
        'src/components/training-options/workspace.tsx',
        'src/components/training-options/schedule-editor.tsx',
        'tests/c21-10-3-options-visibility.test.mjs',
    ]
    checks = [
        ('Frontend regression', [node, '--test', *[str(p.relative_to(web)) for p in sorted((web / 'tests').glob('*.test.mjs'))]], web),
        ('Next route types', [node, 'node_modules/next/dist/bin/next', 'typegen'], web),
        ('TypeScript', [node, 'node_modules/typescript/bin/tsc', '--noEmit'], web),
        ('ESLint', [node, 'node_modules/eslint/bin/eslint.js', *lint], web),
        ('Production build', [node, 'node_modules/next/dist/bin/next', 'build'], web),
    ]
    if args.with_backend:
        checks.insert(0, ('Backend planning regression', [sys.executable, '-m', 'pytest', 'tests/planning', '-q'], root / 'apps/api'))
    for name, command, folder in checks:
        print('C21.10.3: ' + name, flush=True)
        try:
            subprocess.run(command, cwd=folder, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.10.3 tesztkapu megallt: ' + name + '.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.10.3 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
