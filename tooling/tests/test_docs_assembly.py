"""Selected-release boundaries for published links and Studio screenshots."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('docs_assembly', ROOT / 'tooling/docs/assemble_public_docs.py')
assert SPEC is not None and SPEC.loader is not None
assembly = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = assembly
SPEC.loader.exec_module(assembly)


class AssemblyBoundaryTests(unittest.TestCase):
    def test_component_links_follow_independent_source_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory)
            page = content / 'guide.md'
            page.write_text('\n'.join([
                '[SDK](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/base)',
                '[Studio](https://github.com/mdrideout/junjo/blob/master/apps/studio/README.md#setup)',
                '[Root](https://github.com/mdrideout/junjo/tree/master/tooling)',
                '[Already pinned](https://github.com/mdrideout/junjo/tree/old-revision/sdks/python)',
                '[Different repository](https://github.com/example/junjo/tree/master/sdks/python)',
            ]))
            assembly.pin_component_source_links(content, python_revision='python-revision', studio_revision='studio-revision')
            output = page.read_text()
            self.assertIn('/tree/python-revision/sdks/python/examples/base', output)
            self.assertIn('/blob/studio-revision/apps/studio/README.md#setup', output)
            self.assertIn('/tree/master/tooling', output)
            self.assertIn('/tree/old-revision/sdks/python', output)
            self.assertIn('example/junjo/tree/master/sdks/python', output)

    def test_old_release_without_screenshots_publishes_empty_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / 'output'
            assembly.copy_studio_assets(root / 'old-release', destination)
            self.assertTrue(destination.is_dir())
            self.assertEqual(assembly.directory_files(destination), {})

    def test_selected_studio_assets_participate_in_parity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'release/apps/studio/docs/assets'
            source.mkdir(parents=True)
            (source / 'dataset.png').write_bytes(b'captured-screenshot')
            staged = root / 'staged'
            published = root / 'published'
            assembly.copy_studio_assets(root / 'release', staged)
            assembly.replace_output(staged, published)
            self.assertEqual(assembly.compare_directory(staged, published, 'Studio assets'), [])
            (published / 'dataset.png').write_bytes(b'stale-screenshot')
            self.assertEqual(assembly.compare_directory(staged, published, 'Studio assets'), ['Studio assets: stale dataset.png'])
            empty = root / 'empty'
            assembly.copy_studio_assets(root / 'old-release', empty)
            assembly.replace_output(empty, published)
            self.assertEqual(assembly.directory_files(published), {})


if __name__ == '__main__':
    unittest.main()
