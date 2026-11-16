"""C21.5 frontend regression gate: single visible save controls and separated personal/training fields."""
import shutil
import subprocess
import sys
from pathlib import Path


def main():
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
            'src/components/athlete-setup/profile-form.tsx', 'src/lib/planning-data', 'src/lib/athlete-setup', 'src/lib/ui/navigation.ts',
            'src/components/planning-goals/macro-form.tsx', 'src/components/planning-goals/protocol-form.tsx',
            'src/components/planning-cycles/workspace.tsx', 'src/components/initial-assessment/workspace.tsx',
            'src/components/guided-strength/workspace.tsx', 'src/components/training-options/location-editor.tsx',
            'src/components/training-options/schedule-editor.tsx',
            'src/lib/calendar/editor-history.ts', 'src/lib/calendar/interactions.ts',
            'src/lib/calendar/moves.ts', 'src/app/settings/page.tsx',
            'src/app/nutrition/page.tsx', 'tests/calendar-layout.test.mjs',
            'tests/compact-workspace.test.mjs', 'tests/planning-data-profile.test.mjs', 'tests/profile-normalization.test.mjs',
            'tests/training-options-layout.test.mjs']),
        ('Production build', [node, 'node_modules/next/dist/bin/next', 'build']),
    ]
    for name, command in checks:
        print('C21.5: '+name, flush=True)
        try:
            subprocess.run(command, cwd=web, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.5 tesztkapu megallt: '+name+'.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.5 FRONTEND TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
