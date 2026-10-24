using System;

namespace FizRPLangMenu
{
	/// <summary>
	/// 仅两处大字的像素对齐策略：
	///   a) 关卡选择界面左上角世界名（go=StageName，TextData:StageSelectText_WorldName，原 14px）；
	///   b) 首次到达新关卡的中央过场标题（UI Table: MovieCanvasCamera_Stage*，
	///      原 24px，首行富文本 &lt;size=16&gt;）。
	///
	/// 实机反馈（v1.2.10）确认：改成 8px 设计宿主 @16px 后「糖/浆/饼」等密笔画汉字
	/// **字腔被填成实心**。原因有两层，且都只能从字形本身解决：
	///   1) 8px 设计网格里这些字就没有留出字腔（放大到 16px 只是把实心块放大）——
	///      这是硬限制，任何倍率都救不回来，必须换更大的设计尺寸；
	///   2) 游戏的 PixelOutline 描边固定 1 canvas 单位（实测白笔画 8px / 黑间隙 4px），
	///      不随字号缩放，字号越大相对越细，但密笔画的 1px 间隙仍会被吃掉。
	///
	/// 因此两处一律改用 **12px 设计宿主**（补丁新增的 Font 对象）：
	///   关卡选择 12px（1:1）——其文本框实测 240×32 canvas 单位，实测两行 10px 的
	///   字身占 15.8..34.5，而下一行宝珠在 45.8，12px 的两行仍有余量；
	///   过场标题 24px（2× 整数倍）——文本框 256×224 空间充裕，2× 放大后字腔完整、
	///   笔画粗壮；首行由译表 &lt;size=16&gt; 固定为 16px，不受此处的 fontSize 影响。
	///
	/// 范围严格限定：其它大字（对白内 &lt;size=24&gt;、教学板 75px 等）不适用本策略。
	/// </summary>
	internal static class LargeTitlePixelPolicy
	{
		/// <summary>fusion-12px 的设计尺寸（补丁新增的宿主对象）；倍率须为整数。</summary>
		internal const int DesignSize = 12;

		/// <summary>关卡选择世界名的 GameObject 名（全场景唯一命中）。</summary>
		internal const string StageSelectName = "StageName";

		/// <summary>关卡选择世界名字号：1:1，12px 设计逐格对应。</summary>
		internal const int StageSelectSize = 12;

		/// <summary>过场中央标题字号：2× 整数倍，24px。</summary>
		internal const int MovieTitleSize = 24;

		/// <summary>12px 宿主不可用时的退路字号（10px 宿主的整数倍）。</summary>
		internal const int FallbackStageSelectSize = 10;

		/// <summary>12px 宿主不可用时的退路字号（10px 宿主的整数倍）。</summary>
		internal const int FallbackMovieTitleSize = 20;

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
		/// 该文本应使用的字号。关卡选择与过场标题各有独立取值（版式余量不同），
		/// 其它文本返回 -1 表示不适用本策略。
		/// </summary>
		internal static int TargetSize(string goName, string text)
		{
			if (IsStageSelectName(goName))
			{
				return StageSelectSize;
			}
			if (IsMovieStageTitle(text))
			{
				return MovieTitleSize;
			}
			return -1;
		}

		/// <summary>
		/// 12px 宿主缺失时的退路字号（10px 宿主的整数倍）：关卡选择 10px（1:1）、
		/// 过场标题 20px（2×）。两者仍是整数倍，只是字腔比 12px 密。
		/// </summary>
		internal static int FallbackSize(int targetSize)
		{
			if (targetSize == StageSelectSize)
			{
				return FallbackStageSelectSize;
			}
			if (targetSize == MovieTitleSize)
			{
				return FallbackMovieTitleSize;
			}
			return targetSize;
		}
	}
}
