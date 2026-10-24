using System;
using FizRPLangMenu;

internal static class MenuFontPolicyHarness
{
	private static void Check(bool value)
	{
		if (!value) throw new Exception("Menu font policy regression");
	}

	private static int Main(string[] args)
	{
		switch (args[0])
		{
			case "font-sizes":
				Check(FontSizePolicy.Quantize(8) == 8);
				Check(FontSizePolicy.Quantize(10) == 10);
				Check(FontSizePolicy.Quantize(12) == 10);
				foreach (int size in new[] { 13, 16, 24, 32, 48, 64, 96 })
				{
					Check(FontSizePolicy.Quantize(size) == size);
					Check(FontSizePolicy.Quantize(FontSizePolicy.Quantize(size)) == size);
				}
				break;
			case "big-title":
				// 两处大字的识别：关卡选择世界名（go=StageName）/ 中央过场标题（<size=16>第N关</size>）
				Check(LargeTitlePixelPolicy.IsStageSelectName("StageName"));
				Check(!LargeTitlePixelPolicy.IsStageSelectName("StageText"));
				Check(!LargeTitlePixelPolicy.IsStageSelectName("Text"));
				Check(LargeTitlePixelPolicy.IsMovieStageTitle("<size=16>第2关</size>\n糖浆平原"));
				Check(LargeTitlePixelPolicy.IsMovieStageTitle("<size=16>第8关</size>\n未命名区域"));
				Check(!LargeTitlePixelPolicy.IsMovieStageTitle("<size=16>ステージ2</size>\nクッキー砂漠"));
				Check(!LargeTitlePixelPolicy.IsMovieStageTitle("<size=24>大字显示</size>"));
				Check(!LargeTitlePixelPolicy.IsMovieStageTitle("普通文本"));
				Check(!LargeTitlePixelPolicy.IsMovieStageTitle(null));
				Check(LargeTitlePixelPolicy.Applies("StageName", "第1关\n糖浆平原"));
				Check(LargeTitlePixelPolicy.Applies("Text", "<size=16>第2关</size>\n糖浆平原"));
				Check(!LargeTitlePixelPolicy.Applies("Text", "普通文本"));
				break;
			case "big-title-snap":
				// 字号吸附到 8px 设计尺寸的整数倍：14→16（2×8）、24→24（3×8）、16→16（2×8）
				Check(LargeTitlePixelPolicy.SnapSize(14) == 16);
				Check(LargeTitlePixelPolicy.SnapSize(24) == 24);
				Check(LargeTitlePixelPolicy.SnapSize(16) == 16);
				Check(LargeTitlePixelPolicy.SnapSize(8) == 8);
				Check(LargeTitlePixelPolicy.SnapSize(12) == 16);
				Check(LargeTitlePixelPolicy.SnapSize(4) == 8);
				foreach (int size in new[] { 8, 14, 16, 24, 32 })
				{
					int snapped = LargeTitlePixelPolicy.SnapSize(size);
					Check(snapped % LargeTitlePixelPolicy.DesignSize == 0);
					Check(LargeTitlePixelPolicy.SnapSize(snapped) == snapped);
				}
				break;
			case "menu":
				Check(TitleMenuFontPolicy.Applies("TitleCanvas", true));
				break;
			case "other-ui":
				Check(!TitleMenuFontPolicy.Applies("GameCanvas", true));
				Check(!TitleMenuFontPolicy.Applies("DialogueCanvas", true));
				Check(!TitleMenuFontPolicy.Applies(null, true));
				break;
			case "latin":
				Check(!TitleMenuFontPolicy.Applies("TitleCanvas", false));
				break;
			case "cold-start":
				Check(TitleMenuFontPolicy.Size == 10);
				Check(TitleMenuFontPolicy.MinimumHeight(8, 10) == 10);
				break;
			case "line-spacing":
				Check(TitleMenuFontPolicy.MinimumHeight(8, 12.5f) == 13);
				break;
			case "keep-height":
				Check(TitleMenuFontPolicy.MinimumHeight(32, 10) == 32);
				Check(TitleMenuFontPolicy.MinimumHeight(32.5f, 10) == 32.5f);
				break;
			case "idempotent":
				float once = TitleMenuFontPolicy.MinimumHeight(8, 10);
				Check(TitleMenuFontPolicy.MinimumHeight(once, 10) == once);
				break;
			case "empty-measurement":
				Check(TitleMenuFontPolicy.MinimumHeight(8, 0) == 10);
				break;
			default:
				throw new ArgumentException("Unknown test case");
		}
		return 0;
	}
}
