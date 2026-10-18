using System;

namespace FizRPLangMenu
{
	/// <summary>仅主菜单中文使用的大字号与容纳高度；不依赖字体加载先后顺序。</summary>
	internal static class TitleMenuFontPolicy
	{
		internal const int Size = 10;

		internal static bool Applies(string canvasName, bool hasCjk)
		{
			return hasCjk && canvasName == "TitleCanvas";
		}

		internal static float MinimumHeight(float currentHeight, float preferredHeight)
		{
			return (float)Math.Max(currentHeight, Math.Ceiling(Math.Max(Size, preferredHeight)));
		}
	}
}
