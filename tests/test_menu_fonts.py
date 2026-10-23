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
                   str(ROOT / 'plugin/FontSizePolicy.cs'),
                   str(ROOT / 'tests/menu_font_policy_harness.cs')]
        proc = subprocess.run(command, capture_output=True, encoding='utf-8')
        if proc.returncode:
            raise RuntimeError(proc.stdout + '\n' + proc.stderr)
        # Exercise the pure pause-hint policy with the widths and inherited offsets
        # observed in live A/B/C captures. This is not a Unity rendering test.
        cls.grid_exe = cls.base / 'PauseHintPolicyTests.exe'
        grid_command = command[:command.index('-out:' + str(cls.exe))]
        grid_command += ['-out:' + str(cls.grid_exe), '-reference:' + str(reference),
                         str(ROOT / 'plugin/PauseHintPixelPolicy.cs'),
                         str(ROOT / 'tests/pixel_grid_harness.cs')]
        proc = subprocess.run(grid_command, capture_output=True, encoding='utf-8')
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

    def test_large_stage_titles_keep_authored_size_across_scans(self):
        self.run_case('font-sizes')

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

    def run_grid_case(self, name):
        proc = subprocess.run([str(self.grid_exe), name], capture_output=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 0, proc.stdout + '\n' + proc.stderr)

    def test_only_three_named_pause_hints_are_targets(self):
        self.run_grid_case('scope')

    def test_inactive_or_unmounted_prefab_is_not_shifted(self):
        self.run_grid_case('prefab')

    def test_clone_inherited_offset_is_not_added_again(self):
        self.run_grid_case('clone')

    def test_repeated_frames_and_recreated_instances_do_not_drift(self):
        self.run_grid_case('idempotent')

    def test_reselected_language_recalculates_absolute_phase(self):
        self.run_grid_case('text-change')

    def test_measured_three_page_widths_use_expected_offsets(self):
        self.run_grid_case('measured-widths')

    def test_invalid_layout_values_are_rejected(self):
        self.run_grid_case('invalid')

    def test_japanese_and_latin_hints_are_not_shifted(self):
        self.run_grid_case('language')


class MenuFontIntegrationTests(unittest.TestCase):
    def test_scan_and_setters_share_size_policy(self):
        source = (ROOT / 'plugin/LangMenuPlugin.cs').read_text(encoding='utf-8')
        quantize = source.split('internal static int QuantizeSize(int fontSize)', 1)[1]
        self.assertIn('return FontSizePolicy.Quantize(fontSize);', quantize.split('}', 1)[0])
        apply = source.split('internal static void Apply(Text text)', 1)[1]
        self.assertIn('QuantizeSize(baseSize)', apply.split('internal static void ApplyTMP', 1)[0])
        setter = source.split('internal static class TextFontSizePatch', 1)[1]
        self.assertIn('GetBaseSize(__instance, value)', setter)
        self.assertIn('FontApplier.QuantizeSize(baseSize)', setter)


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

    def test_pause_hints_bypass_legacy_additive_snap(self):
        source = (ROOT / 'plugin/LangMenuPlugin.cs').read_text(encoding='utf-8')
        snap = source.split('internal static void SnapContentToPixelGrid(Text text, int id)', 1)[1]
        snap = snap.split('private static float NearestGridShift', 1)[0]
        branch = snap.split('if (text == null)', 1)[0]
        self.assertIn('PauseHintPixelPolicy.IsTarget(text.gameObject.name)', branch)
        self.assertIn('SnapPauseHint(text, id);', branch)
        self.assertIn('return;', branch)
        self.assertLess(snap.index('SnapPauseHint(text, id);'), snap.index('_snapChecked.TryGetValue'))

    def test_pause_hint_repairs_absolute_x_only_after_scope_guard(self):
        source = (ROOT / 'plugin/LangMenuPlugin.cs').read_text(encoding='utf-8')
        helper = source.split('private static void SnapPauseHint(Text text, int id)', 1)[1]
        helper = helper.split('internal static void SnapContentToPixelGrid', 1)[0]
        self.assertLess(helper.index('PauseHintPixelPolicy.Applies'), helper.index('text.preferredWidth'))
        self.assertIn('rect.anchoredPosition = new Vector2(state.TargetX, position.y);', helper)
        self.assertNotIn('position.x +', helper)
        self.assertNotIn('rect.position =', helper)
        self.assertNotIn('text.font =', helper)
        self.assertNotIn('text.fontSize =', helper)
        for field in ('Content', 'Font', 'Size', 'CanvasId', 'Ppu', 'XMin', 'Width'):
            self.assertIn('state.' + field + ' !=', helper)
        self.assertIn('PauseHintPixelPolicy.IsFinite(position.x)', helper)
        self.assertIn('PauseHintPixelPolicy.IsFinite(position.y)', helper)

    def test_force_large_is_cjk_scoped_and_uses_policy_size(self):
        source = (ROOT / 'plugin/LangMenuPlugin.cs').read_text(encoding='utf-8')
        self.assertIn('SizeLarge = TitleMenuFontPolicy.Size;', source)
        self.assertIn('TitleMenuFontPolicy.Applies(text.canvas.name, HasCJK(text.text))', source)
        force = source.split('internal static bool ForceLarge(Text text)', 1)[1]
        force = force.split('\n\t\t}', 1)[0]
        self.assertIn('IsMainMenuText(text)', force)


if __name__ == '__main__':
    unittest.main()
