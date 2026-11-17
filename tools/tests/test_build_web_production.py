"""A zero exit status, stale marker or partial output is not a valid Next build."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('web_build', Path(__file__).resolve().parents[1] / 'build_web_production.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.web = self.root / 'apps/web'
        cli = self.web / 'node_modules/next/dist/bin/next'
        cli.parent.mkdir(parents=True)
        cli.write_text('fake next cli')
        (self.root / 'athlete.sqlite').write_bytes(b'USER DATA')

    def ready(self):
        output = self.web / '.next'
        output.mkdir(exist_ok=True)
        (output / 'BUILD_ID').write_text('fixed-build-id')
        for name in build.MANIFESTS:
            p = output / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({'/nutrition/page': 'app/nutrition/page.js'} if name.startswith('server/') else {}))
        page = output / 'server/app/nutrition/page.js'
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text('compiled page')

    def run_build(self, runner):
        with contextlib.redirect_stdout(io.StringIO()):
            return build.build_web_production(self.root, runner=runner, node='node')

    def test_success_has_ci_only_in_the_child_and_preserves_user_files(self):
        before = dict(os.environ)
        def runner(command, **kwargs):
            self.assertEqual(command[-1], 'build')
            self.assertEqual(kwargs['cwd'], self.web)
            self.assertEqual(kwargs['env']['CI'], '1')
            self.assertFalse(kwargs['check'])
            self.ready()
            return SimpleNamespace(returncode=0)
        self.assertEqual(self.run_build(runner), 'fixed-build-id')
        self.assertEqual(dict(os.environ), before)
        self.assertEqual((self.root / 'athlete.sqlite').read_bytes(), b'USER DATA')

    def test_zero_exit_without_any_build_is_rejected(self):
        with self.assertRaisesRegex(build.BuildError, 'BUILD_ID'):
            self.run_build(lambda *a, **k: SimpleNamespace(returncode=0))

    def test_a_stale_ready_build_does_not_hide_an_upgrade_only_exit(self):
        self.ready()
        with self.assertRaisesRegex(build.BuildError, 'BUILD_ID'):
            self.run_build(lambda *a, **k: SimpleNamespace(returncode=0))

    def test_nonzero_exit_keeps_the_actual_failure_code(self):
        self.ready()
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_build(lambda *a, **k: SimpleNamespace(returncode=7))
        self.assertEqual(caught.exception.returncode, 7)
        self.assertFalse((self.web / '.next/BUILD_ID').exists())

    def test_a_rebuilt_static_build_id_can_legitimately_stay_the_same(self):
        self.ready()
        def runner(*a, **k):
            self.assertFalse((self.web / '.next/BUILD_ID').exists())
            self.ready()
            return SimpleNamespace(returncode=0)
        self.assertEqual(self.run_build(runner), 'fixed-build-id')

    def test_each_missing_manifest_is_rejected(self):
        for name in build.MANIFESTS:
            with self.subTest(name=name):
                self.ready()
                (self.web / '.next' / name).unlink()
                with self.assertRaises(build.BuildError):
                    build.verify_build(self.web)

    def test_malformed_and_non_object_manifests_are_rejected(self):
        for value in ['{', 'null', '[]', '"not a manifest"']:
            with self.subTest(value=value):
                self.ready()
                (self.web / '.next/build-manifest.json').write_text(value)
                with self.assertRaises(build.BuildError):
                    build.verify_build(self.web)

    def test_empty_marker_is_rejected(self):
        self.ready()
        (self.web / '.next/BUILD_ID').write_text(' \n')
        with self.assertRaises(build.BuildError):
            build.verify_build(self.web)

    def test_a_manifest_cannot_claim_an_absent_compiled_page(self):
        self.ready()
        (self.web / '.next/server/app/nutrition/page.js').unlink()
        with self.assertRaisesRegex(build.BuildError, 'nutrition'):
            build.verify_build(self.web)

    def test_empty_app_manifest_is_rejected(self):
        self.ready()
        (self.web / '.next/server/app-paths-manifest.json').write_text('{}')
        with self.assertRaises(build.BuildError):
            build.verify_build(self.web)

    def test_windows_manifest_separators_resolve_to_the_actual_compiled_page(self):
        self.ready()
        (self.web / '.next/server/app-paths-manifest.json').write_text(json.dumps({'/nutrition/page': 'app\\nutrition\\page.js'}))
        self.assertEqual(build.verify_build(self.web), 'fixed-build-id')

    def test_unsafe_app_manifest_paths_are_rejected(self):
        for value in ['../../athlete.sqlite', '/tmp/elsewhere', 'app\\outside.js', 42]:
            self.ready()
            (self.web / '.next/server/app-paths-manifest.json').write_text(json.dumps({'/wrong/page': value}))
            with self.assertRaises(build.BuildError):
                build.verify_build(self.web)

    def test_missing_cli_fails_before_removing_a_previous_ready_marker(self):
        self.ready()
        (self.web / 'node_modules/next/dist/bin/next').unlink()
        with self.assertRaises(build.BuildError):
            self.run_build(lambda *a, **k: self.fail('Must not start a missing CLI'))
        self.assertTrue((self.web / '.next/BUILD_ID').exists())


if __name__ == '__main__':
    unittest.main()
