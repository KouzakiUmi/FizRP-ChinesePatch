using System;

namespace FizRPLangMenu
{
	/// <summary>
	/// 仅两处大字的像素对齐策略：
	///   a) 关卡选择界面左上角世界名（go=StageName，TextData:StageSelectText_WorldName，原 14px）；
	///   b) 首次到达新关卡的中央过场标题（UI Table: MovieCanvasCamera_Stage*，
	///      原 24px + 首行富文本 &lt;size=16&gt;）。
	///
	/// 发虚根因：两处宿主字体是 fusion-10px 设计（k8x12EXS），14 / 24 / 16 px 都不是
	/// 10px 的整数倍（1.4× / 2.4× / 1.6×），字形贴图光栅化时设计像素边界落在分数像素上，
	/// 边缘自带灰阶 —— 这是光栅内部的模糊，位置对齐救不了，只有整数倍放大才能消除。
	///
	/// 改用 8px 设计宿主（k8x12EXL ← fusion-8px）后 24 = 3×8、16 = 2×8、14 → 16 = 2×8
	/// 均为整数倍，字形按整块设计像素放大；24/16 版式一毫不变，仅世界名 14→16 微调一格。
	///
	/// 范围严格限定：其它大字（对白内 &lt;size=24&gt;、教学板 75px 等）不适用本策略。
	/// </summary>
	internal static class LargeTitlePixelPolicy
	{
		/// <summary>fusion-8px 的设计尺寸；倍率 = fontSize / 8 必须为整数。</summary>
		internal const int DesignSize = 8;

		/// <summary>关卡选择世界名的 GameObject 名（全场景唯一命中）。</summary>
		internal const string StageSelectName = "StageName";

		internal static bool IsStageSelectName(string goName)
		{
			return goName == StageSelectName;
		}

		/// <summary>
		/// 中央过场标题：`&lt;size=16&gt;第N关&lt;/size&gt;\n地名`。日文原文是
		/// `&lt;size=16&gt;ステージN&lt;/size&gt;`，不含「第…关」，故此判定天然只命中中文文案。
		/// </summary>
		internal static bool IsMovieStageTitle(string text)
		{
			if (string.IsNullOrEmpty(text))
			{
				return false;
			}
			return text.StartsWith("<size=16>第", StringComparison.Ordinal)
				&& text.IndexOf("关</size>", StringComparison.Ordinal) >= 0;
		}

		internal static bool Applies(string goName, string text)
		{
			return IsStageSelectName(goName) || IsMovieStageTitle(text);
		}

		/// <summary>
		/// 字号吸附到设计尺寸的整数倍（就近取整，下限 1 个倍率）：
		/// 14 → 16（2×8）、24 → 24（3×8）、16 → 16（2×8）。幂等。
		/// </summary>
		internal static int SnapSize(int size)
		{
			if (size <= DesignSize)
			{
				return DesignSize;
			}
			int rounded = ((size + DesignSize / 2) / DesignSize) * DesignSize;
			return rounded < DesignSize ? DesignSize : rounded;
		}
	}
}
