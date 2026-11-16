"""C21.10.14: focused alternatives checks, types, lint and production build."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full-frontend',action='store_true',help='Run every frontend regression instead of the focused subset.')
    parser.add_argument('--with-backend',action='store_true',help='Also run the two new isolated HTTP regression cases.')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    web=root/'apps/web'
    node=shutil.which('node')
    if not node:
        print('Node nem talalhato a PATH-ban.',file=sys.stderr)
        return 1
    focused=['tests/c21-10-14-strength-alternatives.test.mjs','tests/c21-10-13-strength-workouts.test.mjs',
             'tests/c21-10-2-calendar-choices.test.mjs','tests/c21-10-11-calibrated-calendar.test.mjs',
             'tests/c21-10-12-instruction-encoding.test.mjs']
    tests=[str(p.relative_to(web)) for p in sorted((web/'tests').glob('*.test.mjs'))] if args.full_frontend else focused
    checks=[('Frontend alternatives regression',[node,'--test',*tests],web),
            ('Next route types',[node,'node_modules/next/dist/bin/next','typegen'],web),
            ('TypeScript',[node,'node_modules/typescript/bin/tsc','--noEmit'],web),
            ('ESLint',[node,'node_modules/eslint/bin/eslint.js','--max-warnings=0',
                'src/lib/planning-cycles/strength-workout.ts','src/components/calendar/workout-alternatives.tsx',
                'tests/c21-10-14-strength-alternatives.test.mjs'],web),
            ('Production build',[node,'node_modules/next/dist/bin/next','build'],web)]
    if args.with_backend:
        checks.insert(0,('Owned HTTP alternatives regression',[sys.executable,'-m','pytest',
            'tests/planning/test_c21_10_14_strength_alternatives.py','-q','--disable-warnings'],root/'apps/api'))
    for name,command,folder in checks:
        print('C21.10.14: '+name,flush=True)
        try:
            subprocess.run(command,cwd=folder,check=True)
        except subprocess.CalledProcessError as error:
            print('A C21.10.14 tesztkapu megallt: '+name+'.',file=sys.stderr)
            return max(1,error.returncode)
        except OSError as error:
            print(str(error),file=sys.stderr)
            return 1
    print('C21.10.14 TESZTKAPU OK',flush=True)
    return 0


if __name__=='__main__':
    sys.exit(main())
