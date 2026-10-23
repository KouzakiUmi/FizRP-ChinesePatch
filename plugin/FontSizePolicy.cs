namespace FizRPLangMenu
{
	/// <summary>Only ordinary 8/10/12px UI belongs to the small pixel-font tiers.</summary>
	internal static class FontSizePolicy
	{
		internal static int Quantize(int originalSize)
		{
			// Large stage-introduction text is presentation, not small UI. Keep its
			// authored size instead of letting the periodic font scan collapse it.
			if (originalSize > 12) return originalSize;
			return originalSize <= 8 ? 8 : 10;
		}
	}
}
