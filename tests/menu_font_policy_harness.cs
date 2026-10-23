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
