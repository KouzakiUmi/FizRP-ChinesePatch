using System;

namespace FizRPLangMenu
{
	/// <summary>
	/// 仅两处大字的像素对齐策略：
	///   a) 关卡选择界面左上角世界名（go=StageName，TextData:StageSelectText_WorldName，原 14px 两行）；
	///   b) 首次到达新关卡的中央过场标题（UI Table: MovieCanvasCamera_Stage*，
	///      原 24px，首行富文本 &lt;size=16&gt;）。
	///
	/// 实机反馈（v1.2.10）确认：改成 8px 设计宿主 @16px 后「糖/浆/饼」等密笔画汉字
	/// **字腔被填成实心**。原因有两层，且都只能从字形本身解决：
	///   1) 8px 设计网格里这些字就没有留出字腔（放大到 16px 只是把实心块放大）——
	///      这是硬限制，任何倍率都救不回来；
	///   2) 游戏的 PixelOutline 描边固定 1 canvas 单位（实测白笔画 8px / 黑间隙 4px），
	///      不随字号缩放，字号越大相对越细，但密笔画的 1px 间隙仍会被吃掉。
	///
	/// 因此两处都用 **10px 设计宿主**（k8x12EXS），字号取该设计的整数倍：
	///   关卡选择：行1「第N关」10px（1:1，小字）、行2「地名」20px（2×）。
	///     文本框实测 240×32 canvas 单位，下一行宝珠在 45.8 处；两行字身占 16..43.5，
	///     框内且不碰宝珠行。
	///   过场标题：首行「第N关」20px（2×）、地名 30px（3×）。
	///     文本框 256×224 空间充裕；两行共用一个字体，所以首行只能取 10px 宿主的整数倍，
	///     译表里的 &lt;size=16&gt;（16/10 = 1.6× 非整数倍）必须由插件在运行期改写——
	///     实机反馈「第x关 依然模糊」正是这个非整数倍造成的。
	///
	/// 范围严格限定：其它大字（对白内 &lt;size=24&gt;、教学板 75px 等）不适用本策略。
	/// </summary>
	internal static class LargeTitlePixelPolicy
	{
		/// <summary>关卡选择世界名的 GameObject 名（全部场景里只有 level4 一处）。</summary>
		internal const string StageSelectName = "StageName";

		/// <summary>关卡选择行1「第N关」的字号：10px 宿主 1:1（保持小字，不放大）。</summary>
		internal const int StageSelectNumberSize = 10;

		/// <summary>关卡选择行2「地名」的字号：10px 宿主 2×。</summary>
		internal const int StageSelectPlaceSize = 20;

		/// <summary>过场中央标题地名行的字号：10px 宿主 3×（30px）。</summary>
		internal const int MovieTitleSize = 30;

		/// <summary>
		/// 过场标题首行「第N关」的字号：10px 宿主 2×（20px）。
		///
		/// 译表里的首行标签是 &lt;size=16&gt;（日文原文如此），而 16/10 = 1.6×
		/// 是非整数倍 → 字腔与描边都会糊（实机反馈「第x关 依然模糊」）。
		/// 10px 宿主的整数倍只有 10（太小）与 20（够大），故取 20。
		/// </summary>
		internal const int MovieTagSize = 20;

		/// <summary>译表里首行标签的原始字号（仅用于识别与改写）。</summary>
		internal const int MovieOriginalTagSize = 16;

		/// <summary>两处大字所用的宿主设计尺寸。</summary>
		internal const int DesignSize = 10;

		internal static bool IsStageSelectName(string goName)
		{
			return goName == StageSelectName;
		}

		/// <summary>
		/// 中央过场标题：`&lt;size=N&gt;第N关&lt;/size&gt;\n地名`。
		/// N 只能是译表里的 16，或运行期改写成的 20——否则改写后的文本会在下一轮
		/// 扫描里失去大字策略。日文原文是 `&lt;size=16&gt;ステージN&lt;/size&gt;`，
		/// 标签后是假名，天然不匹配。
		/// </summary>
		internal static bool IsMovieStageTitle(string text)
		{
			if (string.IsNullOrEmpty(text))
			{
				return false;
			}
			int close = text.IndexOf('>');
			if (close < 0 || !text.StartsWith("<size=", StringComparison.Ordinal))
			{
				return false;
			}
			string tag = text.Substring(0, close + 1);
			bool known = tag == "<size=" + MovieOriginalTagSize + ">"
				|| tag == "<size=" + MovieTagSize + ">";
			return known
				&& text.IndexOf("第", StringComparison.Ordinal) == close + 1
				&& text.IndexOf("关</size>", StringComparison.Ordinal) >= 0;
		}

		internal static bool Applies(string goName, string text)
		{
			return IsStageSelectName(goName) || IsMovieStageTitle(text);
		}

		/// <summary>
		/// 该文本的基础字号（Text.fontSize）。关卡选择与过场标题各有独立取值，
		/// 其它文本返回 -1 表示不适用本策略。
		/// </summary>
		internal static int TargetSize(string goName, string text)
		{
			if (IsStageSelectName(goName))
			{
				return StageSelectNumberSize;
			}
			if (IsMovieStageTitle(text))
			{
				return MovieTitleSize;
			}
			return -1;
		}

		/// <summary>
		/// 该文本中最大的行字号（一个 Text 里可能有多行不同字号）；不适用返回 -1。
		///
		/// 关卡选择：行1 10px、行2 20px → 20（像素网格按它取：20px 行 1 设计像素
		/// = 2 canvas 单位，起点落在 2 的整数倍上才不糊；而 2 又是 1 的整数倍，
		/// 行1（10px）随之一起对齐）。
		/// 过场标题：地名 30px、首行 20px → 30。
		/// </summary>
		internal static int MaxLineSize(string goName, string text)
		{
			if (IsStageSelectName(goName))
			{
				return StageSelectPlaceSize;
			}
			if (IsMovieStageTitle(text))
			{
				return MovieTitleSize;
			}
			return -1;
		}

		/// <summary>
		/// 关卡选择的行2 需要比行1 大：给第二行加 &lt;size=20&gt; 标签。
		///
		/// 组件本身支持富文本（实测 m_RichText=1），而译表里这两行没有尺寸标签
		/// （日文原文同样是两行同字号），所以标签只能由插件在运行期注入——译文数据
		/// 保持逐字不变，译表一致性校验也不受影响。
		/// 幂等：已带标签时原样返回。
		/// </summary>
		internal static string BuildStageSelectContent(string text)
		{
			if (string.IsNullOrEmpty(text))
			{
				return text;
			}
			if (text.IndexOf("<size=", StringComparison.Ordinal) >= 0)
			{
				return text;
			}
			int nl = text.IndexOf('\n');
			if (nl < 0)
			{
				return text;
			}
			string tail = text.Substring(nl + 1);
			if (tail.Length == 0)
			{
				return text;
			}
			return text.Substring(0, nl + 1)
				+ "<size=" + StageSelectPlaceSize + ">" + tail + "</size>";
		}

		/// <summary>
		/// 过场标题首行的标签改写成目标字号，使「第N关」在宿主设计尺寸下是整数倍。
		///
		/// 译表里的标签必须与日文原文逐字节相同（标签序列一致性校验），所以不能改表；
		/// 组件实测支持富文本，因此由插件在运行期改写。幂等：已是目标字号就原样返回。
		/// </summary>
		internal static string BuildMovieTitleContent(string text)
		{
			if (string.IsNullOrEmpty(text))
			{
				return text;
			}
			int end = text.IndexOf(">", StringComparison.Ordinal);
			if (!text.StartsWith("<size=", StringComparison.Ordinal) || end < 0)
			{
				return text;
			}
			string head = text.Substring(0, end + 1);
			string target = "<size=" + MovieTagSize + ">";
			if (head == target)
			{
				return text;
			}
			return target + text.Substring(end + 1);
		}
	}
}
