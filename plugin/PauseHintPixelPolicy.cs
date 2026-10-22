using System;

namespace FizRPLangMenu
{
	/// <summary>
	/// Only the three pause-footer hints have this policy. Their serialized anchored X is 0
	/// (including the NDS variants), and the game only toggles them, not their X position.
	/// Return an absolute offset from that baseline, never a delta added to an inherited offset.
	/// </summary>
	internal static class PauseHintPixelPolicy
	{
		internal static bool IsTarget(string name)
		{
			return name == "ButtomText_Chara" || name == "ButtomText_Menu"
				|| name == "ButtomText_Treasure";
		}

		internal static bool Applies(string name, bool active, bool hasCanvas, bool hasCjk, bool hasKana)
		{
			return IsTarget(name) && active && hasCanvas && hasCjk && !hasKana;
		}

		internal static bool IsFinite(float value)
		{
			return !float.IsNaN(value) && !float.IsInfinity(value);
		}

		internal static bool TryTargetX(float xMin, float width, float preferredWidth, out float targetX)
		{
			targetX = 0f;
			if (!IsFinite(xMin) || !IsFinite(width) || !IsFinite(preferredWidth)
				|| width <= 0f || preferredWidth <= 0f)
			{
				return false;
			}
			float origin = xMin + (width - preferredWidth) * 0.5f;
			if (!IsFinite(origin)) return false;
			float fraction = origin - (float)Math.Floor(origin);
			if (fraction > 0.02f && fraction < 0.98f)
				targetX = fraction <= 0.5f ? -fraction : 1f - fraction;
			return true;
		}
	}
}
