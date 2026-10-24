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
				// 关卡选择：行1 小字 10px（1:1），行2 地名 20px（2×）；
				// 过场标题：首行 20px（2×）、地名 30px（3×）。两处都用 10px 宿主。
				Check(LargeTitlePixelPolicy.TargetSize("StageName", "第1关\n糖浆平原") == 10);
				Check(LargeTitlePixelPolicy.TargetSize("Text", "<size=16>第2关</size>\n饼干沙漠") == 30);
				Check(LargeTitlePixelPolicy.TargetSize("Text", "普通文本") == -1);
				Check(LargeTitlePixelPolicy.TargetSize("StageText", "第1关\n糖浆平原") == -1);
				Check(LargeTitlePixelPolicy.StageSelectNumberSize == 10);
				Check(LargeTitlePixelPolicy.StageSelectPlaceSize == 20);
				Check(LargeTitlePixelPolicy.MovieTitleSize == 30);
				Check(LargeTitlePixelPolicy.MovieTagSize == 20);
				Check(LargeTitlePixelPolicy.DesignSize == 10);
				// 字号必须是宿主设计尺寸的整数倍，否则字腔会被描边吃掉。
				Check(LargeTitlePixelPolicy.StageSelectNumberSize % LargeTitlePixelPolicy.DesignSize == 0);
				Check(LargeTitlePixelPolicy.StageSelectPlaceSize % LargeTitlePixelPolicy.DesignSize == 0);
				Check(LargeTitlePixelPolicy.MovieTagSize % LargeTitlePixelPolicy.DesignSize == 0);
				Check(LargeTitlePixelPolicy.MovieTitleSize % LargeTitlePixelPolicy.DesignSize == 0);
				break;
			case "stage-select-content":
				// 行2 注入 <size=20> 标签；幂等；单行/已带标签不动。
				Check(LargeTitlePixelPolicy.BuildStageSelectContent("第1关\n糖浆平原")
					== "第1关\n<size=20>糖浆平原</size>");
				Check(LargeTitlePixelPolicy.BuildStageSelectContent("第3关\n抹茶树海")
					== "第3关\n<size=20>抹茶树海</size>");
				string tagged = LargeTitlePixelPolicy.BuildStageSelectContent("第1关\n糖浆平原");
				Check(LargeTitlePixelPolicy.BuildStageSelectContent(tagged) == tagged);
				Check(LargeTitlePixelPolicy.BuildStageSelectContent("只有一行") == "只有一行");
				Check(LargeTitlePixelPolicy.BuildStageSelectContent("") == "");
				Check(LargeTitlePixelPolicy.BuildStageSelectContent(null) == null);
				Check(LargeTitlePixelPolicy.BuildStageSelectContent("第1关\n") == "第1关\n");
				// 译表原文不带标签，注入只发生在运行期。
				Check(LargeTitlePixelPolicy.BuildStageSelectContent("第1关\n糖浆平原").IndexOf("<size=20>") > 0);
				break;
			case "movie-title-content":
				// 首行标签 16 → 20（10px 宿主的 2×；16/10=1.6× 非整数倍会糊）；幂等；非目标不动。
				Check(LargeTitlePixelPolicy.BuildMovieTitleContent("<size=16>第2关</size>\n饼干沙漠")
					== "<size=20>第2关</size>\n饼干沙漠");
				Check(LargeTitlePixelPolicy.BuildMovieTitleContent("<size=16>第8关</size>\n未命名区域")
					== "<size=20>第8关</size>\n未命名区域");
				string rewritten = LargeTitlePixelPolicy.BuildMovieTitleContent("<size=16>第2关</size>\n饼干沙漠");
				Check(LargeTitlePixelPolicy.BuildMovieTitleContent(rewritten) == rewritten);
				Check(LargeTitlePixelPolicy.BuildMovieTitleContent("普通文本") == "普通文本");
				Check(LargeTitlePixelPolicy.BuildMovieTitleContent("") == "");
				Check(LargeTitlePixelPolicy.BuildMovieTitleContent(null) == null);
				// 改写后仍要被识别为过场标题（否则下一轮扫描会丢掉大字策略）。
				Check(LargeTitlePixelPolicy.IsMovieStageTitle("<size=16>第2关</size>\n饼干沙漠"));
				Check(LargeTitlePixelPolicy.IsMovieStageTitle("<size=20>第2关</size>\n饼干沙漠"));
				Check(!LargeTitlePixelPolicy.IsMovieStageTitle("<size=24>第2关</size>\n饼干沙漠"));
				Check(!LargeTitlePixelPolicy.IsMovieStageTitle("<size=16>ステージ2</size>\nクッキー砂漠"));
				Check(LargeTitlePixelPolicy.MovieTagSize == 20);
				Check(LargeTitlePixelPolicy.MovieOriginalTagSize == 16);
				// 首行与地名的字号都必须是宿主设计尺寸的整数倍。
				Check(LargeTitlePixelPolicy.MovieTagSize % LargeTitlePixelPolicy.DesignSize == 0);
				Check(LargeTitlePixelPolicy.MovieTitleSize % LargeTitlePixelPolicy.DesignSize == 0);
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
