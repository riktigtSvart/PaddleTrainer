"""Build the frontend non-interactively and verify actual next-start artifacts."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys


class BuildError(RuntimeError):
    pass


MANIFESTS = ('build-manifest.json', 'prerender-manifest.json', 'routes-manifest.json',
    'required-server-files.json', 'server/app-paths-manifest.json')


def verify_build(web):
    output = Path(web) / '.next'
    try:
        build_id = (output / 'BUILD_ID').read_text(encoding='utf-8').strip()
    except (OSError, UnicodeError) as error:
        raise BuildError('Nincs friss .next/BUILD_ID. A Next kilepett, de nem keszult indithato production build.') from error
    if not build_id or len(build_id) > 4096:
        raise BuildError('A .next/BUILD_ID ures vagy ervenytelen.')
    values = {}
    for name in MANIFESTS:
        try:
            value = json.loads((output / name).read_text(encoding='utf-8'))
        except (OSError, UnicodeError, ValueError) as error:
            raise BuildError('A production build hianyos vagy serult: ' + name) from error
        if not isinstance(value, dict):
            raise BuildError('Ervenytelen build-manifeszt: ' + name)
        values[name] = value
    paths = values['server/app-paths-manifest.json']
    if not paths:
        raise BuildError('A production build nem tartalmaz alkalmazasoldalakat.')
    for route, name in paths.items():
        if not isinstance(name, str):
            raise BuildError('Ervenytelen alkalmazasmodul: ' + str(route))
        path = PurePosixPath(name.replace('\\', '/'))
        if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'app':
            raise BuildError('Ervenytelen alkalmazasmodul-utvonal: ' + str(route))
        if not (output / 'server' / Path(*path.parts)).is_file():
            raise BuildError('Hianyzo alkalmazasmodul: ' + str(route))
    return build_id


def build_web_production(project_root, *, runner=subprocess.run, node=None):
    web = Path(project_root).resolve() / 'apps/web'
    command = web / 'node_modules/next/dist/bin/next'
    node = node or shutil.which('node')
    if not node or not command.is_file():
        raise BuildError('A Node vagy a telepitett Next nem talalhato. Elobb az apps/web mappaban futtasd az npm ci parancsot.')
    # Remove only the generated readiness marker. An old build must never turn
    # a successful no-op or a cancelled upgrade into a false success.
    marker = web / '.next/BUILD_ID'
    marker.unlink(missing_ok=True)
    env = os.environ.copy()
    env['CI'] = '1'  # Next's human upgrade menu must not intercept a test gate.
    result = runner([node, str(command), 'build'], cwd=web, env=env, check=False)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, result.args if hasattr(result, 'args') else [node, str(command), 'build'])
    build_id = verify_build(web)
    print('Production build ellenorizve: friss BUILD_ID, 5 JSON-manifeszt es az alkalmazasmodulok.', flush=True)
    return build_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        build_web_production(args.project_root)
    except (OSError, BuildError, subprocess.CalledProcessError) as error:
        print('A frontend build nem sikerult: ' + str(error), file=sys.stderr)
        return max(1, getattr(error, 'returncode', 1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
