"""Compile and exercise the actual menu font policy without launching Unity."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MenuFontPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != 'nt' or not shutil.which('dotnet'):
            raise unittest.SkipTest('Needs Windows .NET Framework and the local .NET SDK')
        reference = (Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) /
                     'Reference Assemblies/Microsoft/Framework/.NETFramework/v4.8/mscorlib.dll')
        if not reference.is_file():
            raise unittest.SkipTest('Needs the installed .NET Framework 4.8 targeting pack')
        sdks = subprocess.run(['dotnet', '--list-sdks'], check=True, capture_output=True,
                              encoding='utf-8').stdout.splitlines()
        entries = [re.fullmatch(r'([^\s]+) \[(.+)\]', line.strip()) for line in sdks]
        entries = [entry for entry in entries if entry]
        if not entries:
            raise unittest.SkipTest('No local .NET SDK')
        sdk = entries[-1]
        compiler = Path(sdk[2]) / sdk[1] / 'Roslyn/bincore/csc.dll'
        if not compiler.is_file():
            raise unittest.SkipTest('Local C# compiler unavailable')
        cls.temp = tempfile.TemporaryDirectory(prefix='fizrp-menufont-test-')
        cls.base = Path(cls.temp.name).resolve()
        cls.addClassCleanup(cls.clean_temp)
        cls.exe = cls.base / 'MenuFontPolicyTests.exe'
        command = ['dotnet', str(compiler), '-noconfig', '-nologo', '-utf8output',
                   '-nostdlib+', '-target:exe', '-out:' + str(cls.exe),
                   '-reference:' + str(reference),
                   str(ROOT / 'plugin/TitleMenuFontPolicy.cs'),
                   str(ROOT / 'tests/menu_font_policy_harness.cs')]
        proc = subprocess.run(command, capture_output=True, encoding='utf-8')
        if proc.returncode:
            raise RuntimeError(proc.stdout + '\n' + proc.stderr)

    @classmethod
    def clean_temp(cls):
        target = Path(cls.temp.name).resolve()
        if (target != cls.base or target.parent != Path(tempfile.gettempdir()).resolve()
                or not target.name.startswith('fizrp-menufont-test-')):
            raise RuntimeError('Refusing to clean unexpected test path')
        cls.temp.cleanup()

    def run_case(self, name):
        proc = subprocess.run([str(self.exe), name], capture_output=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 0, proc.stdout + '\n' + proc.stderr)

    def test_main_menu_chinese_selected(self):
        self.run_case('menu')

    def test_game_hud_dialogue_and_missing_canvas_excluded(self):
        self.run_case('other-ui')

    def test_latin_text_not_changed(self):
        self.run_case('latin')

    def test_cold_start_8px_box_fits_10px_font(self):
        self.run_case('cold-start')

    def test_fractional_preferred_height_rounded_up(self):
        self.run_case('line-spacing')

    def test_existing_larger_box_not_shrunk(self):
        self.run_case('keep-height')

    def test_height_repair_is_idempotent(self):
        self.run_case('idempotent')

    def test_zero_measurement_still_reserves_10px(self):
        self.run_case('empty-measurement')


class MenuFontIntegrationTests(unittest.TestCase):
    def test_height_repair_runs_on_fast_and_changed_font_paths(self):
        source = (ROOT / 'plugin/LangMenuPlugin.cs').read_text(encoding='utf-8')
        apply = source.split('internal static void Apply(Text text)', 1)[1]
        apply = apply.split('internal static void ApplyTMP', 1)[0]
        self.assertEqual(apply.count('FitMainMenuHeight(text);'), 2)
        fast = apply.split('if (text.font == f && text.fontSize == want', 1)[1]
        self.assertIn('FitMainMenuHeight(text);', fast.split('return;', 1)[0])
        changed = apply.split('text.fontSize = want;', 1)[1]
        self.assertLess(changed.index('FitMainMenuHeight(text);'),
                        changed.index('SnapContentToPixelGrid(text, _id);'))

    def test_force_large_is_cjk_scoped_and_uses_policy_size(self):
        source = (ROOT / 'plugin/LangMenuPlugin.cs').read_text(encoding='utf-8')
        self.assertIn('SizeLarge = TitleMenuFontPolicy.Size;', source)
        self.assertIn('TitleMenuFontPolicy.Applies(text.canvas.name, HasCJK(text.text))', source)
        force = source.split('internal static bool ForceLarge(Text text)', 1)[1]
        force = force.split('\n\t\t}', 1)[0]
        self.assertIn('IsMainMenuText(text)', force)


if __name__ == '__main__':
    unittest.main()
