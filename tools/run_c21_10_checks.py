"""C21.10 regression gate: geographic areas, swimming and current weekly training."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-only', action='store_true', help='Skip an already completed backend regression.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    web = root / 'apps/web'
    node = shutil.which('node')
    if not node:
        print('Node nem talalhato a PATH-ban.', file=sys.stderr)
        return 1
    lint = ['src/components/athlete-setup/profile-form.tsx',
     'src/components/planning-cycles/plan-output.tsx',
     'src/components/planning-cycles/training-plan-feedback.tsx',
     'src/components/planning-data/sport-availability.tsx',
     'src/components/training-options/daylight-settings.tsx',
     'src/components/training-options/location-editor.tsx',
     'src/components/training-options/location-geography.tsx',
     'src/components/training-options/location-map.tsx',
     'src/components/training-options/prescription-settings.tsx',
     'src/components/training-options/workspace.tsx',
     'src/lib/planning-cycles/assessment-options.ts',
     'src/lib/planning-cycles/mesocycle-coordination.ts',
     'src/lib/planning-cycles/prescription-context.ts',
     'src/lib/planning-cycles/sport-availability.ts',
     'src/lib/planning-cycles/strength-assessment.ts',
     'src/lib/planning-cycles/swimming-prescription.ts',
     'src/lib/planning-cycles/training-load.ts',
     'src/lib/planning-data/automation.ts',
     'src/lib/training-options/area-daylight.ts',
     'src/lib/training-options/contracts.ts',
     'src/lib/training-options/daylight-rules.ts',
     'src/lib/training-options/daylight.ts',
     'src/lib/training-options/location-map.ts',
     'src/lib/training-options/prescription-settings.ts',
     'tests/c21-10-planning.test.mjs']
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
        print('C21.10: ' + name, flush=True)
        try:
            subprocess.run(command, cwd=folder, check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.10 tesztkapu megallt: ' + name + '.', file=sys.stderr)
            return max(1, error.returncode)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 1
    print('C21.10 TESZTKAPU OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
