"""C21.12: meal times, actual intake and reported assessment data."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-only', action='store_true', help='Use only after these same backend sources passed.')
    parser.add_argument('--build-only', action='store_true', help='Verify the build guard and create a verified production build without repeating the passed tests.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    web = root / 'apps/web'
    node = shutil.which('node')
    if not node:
        print('Node nem talalhato a PATH-ban.', file=sys.stderr)
        return 1
    tests = [str(p.relative_to(web)) for p in sorted((web / 'tests').glob('*.test.mjs'))]
    lint = ['src/lib/nutrition/journal.ts', 'src/components/nutrition/journal-workspace.tsx', 'tests/c21-12-journal.test.mjs', 'src/lib/nutrition/contracts.ts', 'src/components/nutrition/meal-workspace.tsx',
        'src/components/nutrition/body-workspace.tsx', 'src/lib/planning-goals/proxy.ts', 'src/lib/ui/navigation.ts',
        'src/components/ui/app-shell.tsx', 'src/app/nutrition/page.tsx', 'src/app/shopping/page.tsx',
        'src/app/layout.tsx', 'tests/c21-11-nutrition.test.mjs']
    checks = []
    if not args.frontend_only and not args.build_only:
        checks.append(('Nutrition and shared body-goal backend regression', [sys.executable, '-m', 'pytest',
            'tests/planning/test_c21_12_nutrition_journal.py', 'tests/planning/test_c21_11_nutrition.py', 'tests/planning/test_c21_7_demands_and_body.py',
            '-q', '--disable-warnings'], root / 'apps/api'))
    if not args.build_only:
        checks.extend([
        ('Full frontend regression', [node, '--test', *tests], web),
        ('Next route types', [node, 'node_modules/next/dist/bin/next', 'typegen'], web),
        ('TypeScript', [node, 'node_modules/typescript/bin/tsc', '--noEmit'], web),
        ('ESLint', [node, 'node_modules/eslint/bin/eslint.js', '--max-warnings=0', *lint], web),
        ])
    checks.extend([
        ('Build guard regression', [sys.executable, str(root / 'tools/tests/test_build_web_production.py')], root),
        ('Verified production build', [sys.executable, str(root / 'tools/build_web_production.py')], root),
    ])
    for name, command, directory in checks:
        print('C21.12: ' + name, flush=True)
        try:
            subprocess.run(command, cwd=directory, check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            print('A C21.12 ellenorzese megallt: ' + name + '.', file=sys.stderr)
            return max(1, getattr(error, 'returncode', 1))
    print('C21.12 BUILD OK' if args.build_only else 'C21.12 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
