"""C21.6 frontend regression gate: sport-specific history, editable sport goals, and durable replacement receipts."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-only', action='store_true', help='Skip an already completed backend planning regression.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    web = root / 'apps/web'
    node = shutil.which('node')
    if not node:
        print('Node nem talalhato a PATH-ban.', file=sys.stderr)
        return 1
    checks = [
        ('Frontend regression', [node, '--test', *[str(p.relative_to(web)) for p in sorted((web/'tests').glob('*.test.mjs'))]]),
        ('Next route types', [node, 'node_modules/next/dist/bin/next', 'typegen']),
        ('TypeScript', [node, 'node_modules/typescript/bin/tsc', '--noEmit']),
        ('ESLint', [node, 'node_modules/eslint/bin/eslint.js',
            'src/components/calendar', 'src/components/ui/app-shell.tsx',
            'src/components/planning-data', 'src/components/athlete-setup/workspace.tsx',
            'src/components/athlete-setup/profile-form.tsx', 'src/components/athlete-setup/sport-context.tsx', 'src/components/planning-goals/workspace.tsx', 'src/lib/planning-data', 'src/lib/athlete-setup', 'src/lib/ui/navigation.ts', 'src/lib/planning-cycles/contracts.ts', 'src/lib/planning-cycles/client.ts',
            'src/components/planning-goals/macro-form.tsx', 'src/components/planning-goals/protocol-form.tsx',
            'src/components/planning-cycles/workspace.tsx', 'src/components/initial-assessment/workspace.tsx',
            'src/components/guided-strength/workspace.tsx', 'src/components/training-options/location-editor.tsx',
            'src/components/training-options/schedule-editor.tsx',
            'src/lib/calendar/editor-history.ts', 'src/lib/calendar/interactions.ts',
            'src/lib/calendar/moves.ts', 'src/app/settings/page.tsx',
            'src/app/nutrition/page.tsx', 'tests/calendar-layout.test.mjs',
            'tests/compact-workspace.test.mjs', 'tests/planning-data-profile.test.mjs', 'tests/profile-normalization.test.mjs',
            'tests/training-options-layout.test.mjs', 'tests/sport-goals.test.mjs']),
        ('Production build', [node, 'node_modules/next/dist/bin/next', 'build']),
    ]
    checks = [(name, command, web) for name, command in checks]
    if not args.frontend_only:
        checks.insert(0, ('Backend planning regression', [sys.executable, '-m', 'pytest', 'tests/planning', '-q'], root / 'apps/api'))
    for name, command, folder in checks:
        print('C21.6: '+name, flush=True)
        try:
            subprocess.run(command, cwd=folder, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.6 tesztkapu megallt: '+name+'.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.6 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
