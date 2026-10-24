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
                   str(ROOT / 'plugin/LargeTitlePixelPolicy.cs'),
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

    def test_big_title_scope_matches_only_two_targets(self):
        self.run_case('big-title')

    def test_big_title_sizes_snap_to_integer_design_multiples(self):
        self.run_case('big-title-snap')

    def test_stage_select_second_line_gets_a_big_size_tag(self):
        self.run_case('stage-select-content')

    def test_movie_title_first_line_tag_is_rewritten_to_design_size(self):
        self.run_case('movie-title-content')

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

    def test_big_title_wiring_uses_ten_px_host_in_scan_and_setters(self):
        """两处大字都用 10px 宿主（8px 设计网格承载不了密笔画汉字），三个接线点同策略。"""
        source = (ROOT / 'plugin/LangMenuPlugin.cs').read_text(encoding='utf-8')
        # 8px 宿主承载不了密笔画汉字（8px 设计网格里没有字腔），大字不得再用它。
        self.assertNotIn('GetEightDesignFont', source)
        # 12px 宿主已整体移除：游戏自带的字体槽位都在用，新增对象又无法保证被实例化，
        # 因此两处大字统一走 10px 宿主（整数倍 10/20/30）。
        self.assertNotIn('FizRP12pxZhHans', source)
        self.assertNotIn('GetTwelveDesignFont', source)
        # Apply 与两个 setter 都必须走同一策略，不能只修扫描路径。
        apply = source.split('internal static void Apply(Text text)', 1)[1]
        apply = apply.split('internal static void ApplyTMP', 1)[0]
        self.assertIn('LargeTitlePixelPolicy.TargetSize(goName, text.text)', apply)
        self.assertIn('LargeTitlePixelPolicy.IsStageSelectName(goName)', apply)
        self.assertIn('LargeTitlePixelPolicy.IsMovieStageTitle(text.text)', apply)
        self.assertIn('LargeTitlePixelPolicy.StageSelectNumberSize', apply)
        self.assertIn('LargeTitlePixelPolicy.MovieTitleSize', apply)
        setter_size = source.split('internal static class TextFontSizePatch', 1)[1]
        self.assertIn('LargeTitlePixelPolicy.TargetSize(', setter_size)
        self.assertIn('LargeTitlePixelPolicy.MovieTitleSize', setter_size)
        setter_font = source.split('internal static class TextFontPatch', 1)[1]
        self.assertIn('LargeTitlePixelPolicy.MovieTitleSize', setter_font)
        # 关卡选择的行2 放大与过场标题首行改写都靠运行期注入富文本标签
        # （组件 m_RichText=1，译表本身不带标签，所以只能由插件加）。
        self.assertIn('LargeTitlePixelPolicy.BuildStageSelectContent(text.text)', apply)
        self.assertIn('LargeTitlePixelPolicy.BuildMovieTitleContent(text.text)', apply)
        # 日文原文不得被注入标签：语言探测可能滞后于界面语言，而 LocalizedText 只覆盖
        # 字体不覆盖文本 —— 注入会永久改写日文文案。注入前必须先判 HasCJK。
        self.assertIn('if (HasCJK(text.text))', apply)
        # 像素网格按最大那一行取（关卡选择行1 10px / 行2 20px → 2 单位）。
        self.assertIn('LargeTitlePixelPolicy.MaxLineSize(', source)
        self.assertIn('text.text = tagged;', apply)
        self.assertIn('text.text = retagged;', apply)
        # 只有这两处允许写 text.text（行2 放大标签、首行标签改写），其余文本不得被回写。
        self.assertEqual(apply.count('text.text ='), 2)
        # 其它文本不得被回写文案或改 rect（只换字体与字号）。
        self.assertNotIn('text.rectTransform', apply.split('FitMainMenuHeight(text);', 1)[0])

    def test_snap_log_format_placeholders_match_arguments(self):
        """[snap] 日志的格式串占位符数必须与实参个数一致。

        这条路径不在纯策略文件里，只有插件本体才会执行；占位符多于实参时
        string.Format 抛 FormatException，会中断当帧文本处理并刷错误日志。
        """
        source = (ROOT / 'plugin/LangMenuPlugin.cs').read_text(encoding='utf-8')
        start = source.index('"[snap]')
        end = source.index('));', start)
        call = source[start:end]
        literals = re.findall(r'"((?:[^"\\]|\\.)*)"', call)
        self.assertTrue(literals, 'no [snap] format literal found')
        fmt = ''.join(literals)
        placeholders = sorted({int(n) for n in re.findall(r'\{(\d+)', fmt)})
        self.assertTrue(placeholders, 'no placeholder in [snap] format string')
        self.assertEqual(placeholders, list(range(len(placeholders))),
                         'placeholders must be contiguous from 0')
        # 实参：在最后一个字符串字面量之后、调用右括号之前的顶层逗号分隔项。
        tail = call[call.rindex('"') + 1:]
        depth = 0
        args = []
        current = ''
        for char in tail:
            if char in '([':
                depth += 1
            elif char in ')]':
                depth -= 1
            if char == ',' and depth == 0:
                args.append(current)
                current = ''
            else:
                current += char
        args.append(current)
        args = [a for a in args if a.strip()]
        self.assertEqual(len(args), len(placeholders),
                         f'[snap] format has {len(placeholders)} placeholders '
                         f'but {len(args)} arguments: {fmt}')


if __name__ == '__main__':
    unittest.main()
