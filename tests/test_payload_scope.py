"""Optional loader documentation must not enter the runtime payload."""
from pathlib import Path
import tempfile
import unittest
from tools.build_additive_payload import copy_into, runtime_file_required


class PayloadScopeTests(unittest.TestCase):
    def test_only_core_api_docs_and_changelog_are_optional(self):
        self.assertFalse(runtime_file_required('changelog.txt'))
        self.assertFalse(runtime_file_required('BepInEx/core/0Harmony.xml'))
        for name in ('BepInEx/core/0Harmony.dll', 'BepInEx/core/0Harmony20.dll',
                     'BepInEx/core/Mono.Cecil.dll', 'LICENSE', 'THIRD-PARTY-NOTICES.txt',
                     'BepInEx/core/NOTICE.txt', 'BepInEx/plugins/user.xml'):
            self.assertTrue(runtime_file_required(name), name)

    def test_runtime_filter_is_not_applied_to_general_data_copy(self):
        temp = tempfile.TemporaryDirectory(prefix='fizrp-payload-scope-test-')
        base = Path(temp.name).resolve()
        try:
            source = base / 'source'
            source.mkdir()
            (source / 'changelog.txt').write_bytes(b'documentation')
            (source / 'winhttp.dll').write_bytes(b'runtime')
            copy_into(str(source), str(base / 'runtime'), 1, include=runtime_file_required)
            self.assertFalse((base / 'runtime/changelog.txt').exists())
            self.assertEqual((base / 'runtime/winhttp.dll').read_bytes(), b'runtime')
            copy_into(str(source), str(base / 'data'), 2)
            self.assertTrue((base / 'data/changelog.txt').exists())
        finally:
            assert Path(temp.name).resolve() == base
            assert base.parent == Path(tempfile.gettempdir()).resolve()
            assert base.name.startswith('fizrp-payload-scope-test-')
            temp.cleanup()


if __name__ == '__main__':
    unittest.main()
