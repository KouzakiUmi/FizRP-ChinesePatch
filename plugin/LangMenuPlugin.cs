using System;
using System.Collections.Generic;
using System.Reflection;
using System.Reflection.Emit;
using BepInEx;
using HarmonyLib;
using TMPro;
using UnityEngine;
using UnityEngine.TextCore.LowLevel;
using UnityEngine.UI;

namespace FizRPLangMenu
{
	/// <summary>
	/// FizRP 语言菜单追加式中文（X2）插件：
	/// 1) LanguageSetting.Start 后激活第三项「選択肢 (2)」并置文本「中文」；
	/// 2) LanguageSetting.Update 的 clamp 常量 1→2（Transpiler），使 index 2 可被光标选中，
	///    由原版 case 2 → Language.Spanish 逻辑接受（中文装在 es 槽位）。
	/// 磁盘上的游戏 DLL 与场景文件不做任何修改。
	/// </summary>
	[BepInPlugin(PluginGuid, PluginName, PluginVersion)]
	public sealed class LangMenuPlugin : BaseUnityPlugin
	{
		public const string PluginGuid = "cc.fizrp.langmenu";
		public const string PluginName = "FizRPLangMenu";
		public const string PluginVersion = "1.0.0";

		internal static BepInEx.Logging.ManualLogSource Log;

		private Harmony _harmony;

		private void Awake()
		{
			Log = Logger;
			try
			{
				_harmony = new Harmony(PluginGuid);
				_harmony.PatchAll(typeof(LangMenuPlugin).Assembly);
				Log.LogInfo("[" + PluginGuid + "] patches applied: LanguageSetting.Start postfix + LanguageSetting.Update clamp transpiler.");
				GameObject host = new GameObject("FizRPLangMenu.FontApplier");
				UnityEngine.Object.DontDestroyOnLoad(host);
				host.AddComponent<FontApplierBehaviour>();
				Log.LogInfo("[" + PluginGuid + "] font applier created (Text.font -> Chinese font while language is Spanish).");
				Log.LogInfo("[" + PluginGuid + "] main-menu Chinese: 10px font with fitted text height.");
			}
			catch (Exception e)
			{
				Log.LogError("[" + PluginGuid + "] PatchAll failed (game continues unpatched): " + e);
			}
		}

		private void OnDestroy()
		{
			try
			{
				if (_harmony != null)
				{
					_harmony.UnpatchSelf();
				}
			}
			catch (Exception e)
			{
				if (Log != null)
				{
					Log.LogWarning("[" + PluginGuid + "] UnpatchAll failed (ignored): " + e);
				}
			}
		}
	}

	/// <summary>补丁共用工具：字段解析、场景对象查找、日志。全部只读反射，不改游戏数据文件。</summary>
	internal static class PatchUtil
	{
		internal const string IndexFieldName = "nowSelectingIndex";
		internal const string LangFieldName = "nowSelectedLanguage";
		internal const string CursorFieldName = "rect_カーソル";
		internal const string OptionObjectName = "選択肢 (2)";
		internal const string OptionObjectNameNoSpace = "選択肢(2)";
		internal const string OptionText = "中文";
		internal const int ThirdIndex = 2;

		private static FieldInfo _indexField;
		private static FieldInfo _langField;
		private static FieldInfo _cursorField;

		internal static FieldInfo GetIndexField()
		{
			if (_indexField == null)
			{
				_indexField = AccessTools.Field(typeof(LanguageSetting), IndexFieldName);
			}
			return _indexField;
		}

		internal static FieldInfo GetLangField()
		{
			if (_langField == null)
			{
				_langField = AccessTools.Field(typeof(LanguageSetting), LangFieldName);
			}
			return _langField;
		}

		/// <summary>光标 RectTransform 字段：先按名「rect_カーソル」，失败则回退到唯一 RectTransform 类型字段。</summary>
		internal static FieldInfo GetCursorField()
		{
			if (_cursorField != null)
			{
				return _cursorField;
			}
			_cursorField = AccessTools.Field(typeof(LanguageSetting), CursorFieldName);
			if (_cursorField == null)
			{
				foreach (FieldInfo f in typeof(LanguageSetting).GetFields(BindingFlags.NonPublic | BindingFlags.Instance))
				{
					if (f.FieldType == typeof(RectTransform))
					{
						_cursorField = f;
						break;
					}
				}
			}
			return _cursorField;
		}

		internal static bool NameMatches(string name)
		{
			if (string.IsNullOrEmpty(name))
			{
				return false;
			}
			return name == OptionObjectName || name.Replace(" ", string.Empty) == OptionObjectNameNoSpace;
		}

		/// <summary>
		/// 查找第三项标签对象「選択肢 (2)」（含未激活对象）：
		/// 先查 LanguageSetting 自身层级树，再查同场景全部 Transform。
		/// </summary>
		internal static GameObject FindOptionLabel(Component instance)
		{
			Transform root = instance.transform.root;
			foreach (Transform t in root.GetComponentsInChildren<Transform>(true))
			{
				if (NameMatches(t.name))
				{
					return t.gameObject;
				}
			}

			int sceneHandle = instance.gameObject.scene.handle;
			foreach (Transform t in Resources.FindObjectsOfTypeAll<Transform>())
			{
				if (!NameMatches(t.name))
				{
					continue;
				}
				GameObject go = t.gameObject;
				if (go.scene.IsValid() && go.scene.handle == sceneHandle)
				{
					return go;
				}
			}
			return null;
		}

		/// <summary>把标签文本设为「中文」：TMP_Text 优先，其次 UnityEngine.UI.Text。返回是否找到文本组件。</summary>
		internal static bool SetLabelChinese(GameObject labelObject)
		{
			TMP_Text tmp = labelObject.GetComponentInChildren<TMP_Text>(true);
			if (tmp != null)
			{
				tmp.text = OptionText;
				return true;
			}
			Text uiText = labelObject.GetComponentInChildren<Text>(true);
			if (uiText != null)
			{
				uiText.text = OptionText;
				return true;
			}
			return false;
		}

		/// <summary>光标位置公式与原版一致：(-16, 32 - index * 24)，index 2 → y = -16。</summary>
		internal static void SetCursorToThird(LanguageSetting instance)
		{
			FieldInfo cursorField = GetCursorField();
			if (cursorField == null)
			{
				Warn("field 'rect_カーソル' not resolved; skip cursor reposition");
				return;
			}
			RectTransform rect = (RectTransform)cursorField.GetValue(instance);
			if (rect != null)
			{
				rect.anchoredPosition = new Vector2(-16f, 32f - ThirdIndex * 24f);
			}
		}

		internal static void Info(string message)
		{
			if (LangMenuPlugin.Log != null)
			{
				LangMenuPlugin.Log.LogInfo("[" + LangMenuPlugin.PluginGuid + "] " + message);
			}
		}

		internal static void Warn(string message)
		{
			if (LangMenuPlugin.Log != null)
			{
				LangMenuPlugin.Log.LogWarning("[" + LangMenuPlugin.PluginGuid + "] " + message);
			}
		}
	}

	/// <summary>
	/// LanguageSetting.Start 之后：
	/// a) 激活「選択肢 (2)」并置文本「中文」（找不到则 LogWarning，不影响游戏）；
	/// b) 若当前存档语言为 Spanish（中文槽位），把光标索引修正为 2（原版 Start 会映射到 1）。
	/// </summary>
	[HarmonyPatch(typeof(LanguageSetting), "Start")]
	internal static class LanguageSettingStartPatch
	{
		private static void Postfix(LanguageSetting __instance)
		{
			try
			{
				GameObject label = PatchUtil.FindOptionLabel(__instance);
				if (label == null)
				{
					PatchUtil.Warn("option label GameObject '選択肢 (2)' not found in scene; skip third-option activation (game unaffected)");
				}
				else
				{
					label.SetActive(true);
					if (PatchUtil.SetLabelChinese(label))
					{
						PatchUtil.Info("third option activated: '選択肢 (2)' -> text '中文'");
					}
					else
					{
						PatchUtil.Warn("no text component (TMP_Text/UnityEngine.UI.Text) under '選択肢 (2)'; activated but text not changed");
					}
				}

				FieldInfo langField = PatchUtil.GetLangField();
				FieldInfo indexField = PatchUtil.GetIndexField();
				if (langField == null || indexField == null)
				{
					PatchUtil.Warn("private fields nowSelectedLanguage/nowSelectingIndex not resolved; skip cursor index fix");
					return;
				}

				Language current = (Language)langField.GetValue(__instance);
				if (current == Language.Spanish)
				{
					indexField.SetValue(__instance, PatchUtil.ThirdIndex);
					PatchUtil.SetCursorToThird(__instance);
					PatchUtil.Info("saved language is Spanish (Chinese slot); cursor index corrected to 2");
				}
			}
			catch (Exception e)
			{
				PatchUtil.Warn("Start postfix exception (ignored, game unaffected): " + e);
			}
		}
	}

	/// <summary>
	/// LanguageSetting.Update 的 clamp 提升：把上限比较与赋值两处常量 1 改为 2。
	/// 目标 IL（Assembly-CSharp LanguageSetting::Update，RVA 0x4ccdc）：
	///   IL_0108 ldfld nowSelectingIndex / IL_010d ldc.i4.1 / IL_010e ble.s   （比较处）
	///   IL_0110 ldarg.0 / IL_0111 ldc.i4.1 / IL_0112 stfld nowSelectingIndex（赋值处）
	/// 采用严格模式匹配 + 命中计数自校验：非恰好 2 处则放弃补丁并保留原版 clamp，绝不猜测修改。
	/// </summary>
	[HarmonyPatch(typeof(LanguageSetting), "Update")]
	internal static class LanguageSettingUpdatePatch
	{
		private static IEnumerable<CodeInstruction> Transpiler(IEnumerable<CodeInstruction> instructions)
		{
			var codes = new List<CodeInstruction>(instructions);
			try
			{
				FieldInfo indexField = PatchUtil.GetIndexField();
				if (indexField == null)
				{
					PatchUtil.Warn("transpiler: field nowSelectingIndex not resolved; keep original clamp");
					return codes;
				}

				// 第一遍：仅收集候选位置，不修改任何指令。
				var targets = new List<int>();
				for (int i = 0; i < codes.Count; i++)
				{
					// 模式 A（上限比较常量）：ldfld nowSelectingIndex; ldc.i4.1; 条件分支
					if (i + 2 < codes.Count
						&& IsLoadField(codes[i], indexField)
						&& IsLoadInt(codes[i + 1], 1)
						&& codes[i + 2].opcode.FlowControl == FlowControl.Cond_Branch)
					{
						targets.Add(i + 1);
					}
					// 模式 B（上限赋值常量）：ldc.i4.1; stfld nowSelectingIndex
					else if (i + 1 < codes.Count
						&& IsLoadInt(codes[i], 1)
						&& IsStoreField(codes[i + 1], indexField))
					{
						targets.Add(i);
					}
				}

				if (targets.Count != 2)
				{
					PatchUtil.Warn("transpiler: matched " + targets.Count + " clamp constant(s), expected exactly 2; keep original clamp (third option stays unreachable)");
					return codes;
				}

				// 第二遍：确认计数无误后再改常量 1 → 2。
				foreach (int i in targets)
				{
					SetLoadInt(codes[i], 2);
				}
				PatchUtil.Info("transpiler: Update clamp constants 1 -> 2 replaced at 2 sites");
			}
			catch (Exception e)
			{
				PatchUtil.Warn("transpiler exception (keep original clamp): " + e);
			}
			return codes;
		}

		private static bool IsLoadField(CodeInstruction ci, FieldInfo field)
		{
			return ci.opcode == OpCodes.Ldfld && Equals(ci.operand, field);
		}

		private static bool IsStoreField(CodeInstruction ci, FieldInfo field)
		{
			return ci.opcode == OpCodes.Stfld && Equals(ci.operand, field);
		}

		private static bool IsLoadInt(CodeInstruction ci, int value)
		{
			if (ci.opcode == OpCodes.Ldc_I4_S)
			{
				return (sbyte)ci.operand == value;
			}
			if (ci.opcode == OpCodes.Ldc_I4)
			{
				return (int)ci.operand == value;
			}
			return GetShortFormValue(ci.opcode, out int shortValue) && shortValue == value;
		}

		private static void SetLoadInt(CodeInstruction ci, int value)
		{
			if (value == 0)
			{
				ci.opcode = OpCodes.Ldc_I4_0;
				ci.operand = null;
			}
			else if (value == 1)
			{
				ci.opcode = OpCodes.Ldc_I4_1;
				ci.operand = null;
			}
			else if (value == 2)
			{
				ci.opcode = OpCodes.Ldc_I4_2;
				ci.operand = null;
			}
			else if (value >= sbyte.MinValue && value <= sbyte.MaxValue)
			{
				ci.opcode = OpCodes.Ldc_I4_S;
				ci.operand = (sbyte)value;
			}
			else
			{
				ci.opcode = OpCodes.Ldc_I4;
				ci.operand = value;
			}
		}

		private static bool GetShortFormValue(OpCode opcode, out int value)
		{
			if (opcode == OpCodes.Ldc_I4_0)
			{
				value = 0;
				return true;
			}
			if (opcode == OpCodes.Ldc_I4_1)
			{
				value = 1;
				return true;
			}
			if (opcode == OpCodes.Ldc_I4_2)
			{
				value = 2;
				return true;
			}
			value = 0;
			return false;
		}
	}

	/// <summary>
	/// 运行时字体替换（追加式中文 X2 的字形修复）。
	///
	/// 2026-10-23 全量口径为 1824 Text / 159 LocalizedText；很多文本没有逐语言字体设置。
	/// 中文（Spanish 槽）下接管含 CJK 的文本，普通小字使用 Fusion Pixel 8/10px 宿主，
	/// 两处大字（关卡选择世界名、中央过场标题）改用 10px 宿主的 10px/20px 整数倍渲染
	/// （见 LargeTitlePixelPolicy）。主菜单高度与暂停页脚位置分别使用有界策略。
	/// 这里只处理字形/排版，不翻译任意硬编码文案。
	///
	/// 非中文时不主动套用此策略，但数据侧已替换共享 Font blob，日英字形仍可能受影响。
	/// 磁盘上的 DLL 与场景文件均不修改。
	/// </summary>
	internal static class FontApplier
	{
		internal const int SpanishLanguageValue = 4;

		/// <summary>
		/// 双字体宿主（一开始的方案）：`k8x12EXL` 装 8px 设计简中、`k8x12EXS` 装 10px
		/// 设计简中。普通小字量化到 8 / 10 两档以匹配设计尺寸；超过 12px 的大标题保留
		/// 基准字号，不保证非整数放大后的点阵锐利。中文字形为全角方形（advance 1.0em）。
		///
		/// 为什么不用 12：方形中文字宽 = 字号，把大档提到 12 会让中文比现在的 10 宽 20%，
		/// 在底栏说明这类刚好顶满容器的文本上会换行压叠（实测过并已回退）。维持在
		/// 10 既保持锐利，也不改变原有的排版宽度层级。
		/// </summary>
		internal const string Font8Name = "k8x12EXL";
		internal const string Font10Name = "k8x12EXS";
		internal const int SizeSmall = 8;
		internal const int SizeLarge = TitleMenuFontPolicy.Size;

		private static readonly Font[] FontCache = new Font[2];
		private static readonly float[] FontSearchTime = new float[2];
		private static readonly HashSet<int> DiagSeen = new HashSet<int>();
		private static int DiagCount;
		private static Text[] _textCache;
		private static float _cacheAge;
		private static readonly HashSet<int> _missingLogged = new HashSet<int>();
		private static readonly HashSet<int> _notApplied = new HashSet<int>();
		/// <summary>
		/// Text 实例 → 我们上一次亲眼确认过的字体。只在通过 HasKana/HasCJK 判定、
		/// 确实由我们接管的文本上写入，用于区分「游戏把我们设的值改回去了」与
		/// 「这个文本我们根本没碰过」——后者曾被当成前者，产生大量假阳性。
		/// </summary>
		private static readonly Dictionary<int, Font> _lastSeen = new Dictionary<int, Font>();
		/// <summary>
		/// Text 实例 → 首次接管时记录的原字号（基准字号）。
		/// 游戏在不同进入时机会给同一文本设 12/10/8 等不同字号；若每次按当前值量化，
		/// 语言选择画面的提示会在 10px / 8px 之间跳。记录基准后始终按基准量化，档位稳定。
		/// </summary>
		private static readonly Dictionary<int, int> _baseFontSize = new Dictionary<int, int>();
		/// <summary>Legacy snap cache for UI outside the three pause-footer hints.</summary>
		private static readonly Dictionary<int, Vector2> _snapChecked = new Dictionary<int, Vector2>();
		private static readonly Dictionary<int, PauseHintState> _pauseHints = new Dictionary<int, PauseHintState>();
		private static readonly HashSet<int> _pauseHintLogged = new HashSet<int>();
		private sealed class PauseHintState
		{
			internal string Content;
			internal Font Font;
			internal int Size;
			internal int CanvasId;
			internal float Ppu;
			internal float XMin;
			internal float Width;
			internal float TargetX;
		}
		private static int _snapLogged;
		private static readonly HashSet<int> _reverted = new HashSet<int>();
		private static readonly HashSet<int> _assignFail = new HashSet<int>();
		private static readonly HashSet<int> _applyFailed = new HashSet<int>();
		private static TMP_Text[] _tmpCache;
		private static float _cacheAgeTmp;
		private static object _manager;
		private static MethodInfo _getLanguage;
		private static bool _langProbeFailed;

		/// <summary>普通小字量化到 8/10；超过原版常规 12px 的大标题保留原字号。</summary>
		internal static int QuantizeSize(int fontSize)
		{
			return FontSizePolicy.Quantize(fontSize);
		}

		/// <summary>只识别主菜单 Canvas 内的中文；不改变游戏内 HUD、对白或拉丁文本。</summary>
		internal static bool IsMainMenuText(Text text)
		{
			return text != null && text.canvas != null
				&& TitleMenuFontPolicy.Applies(text.canvas.name, HasCJK(text.text));
		}

		/// <summary>
		/// 主菜单原有 8px 高文本框不能容纳 10px 字体（Truncate 会整行裁掉）。
		/// 只扩大不足的高度，保留宽度、锚点和位置；稳定态也检查，防止布局把高度改回去。
		/// </summary>
		internal static void FitMainMenuHeight(Text text)
		{
			if (!IsMainMenuText(text))
			{
				return;
			}
			RectTransform rect = text.rectTransform;
			float height = rect.rect.height;
			float required = TitleMenuFontPolicy.MinimumHeight(height, text.preferredHeight);
			if (required > height + 0.01f)
			{
				Vector2 delta = rect.sizeDelta;
				rect.sizeDelta = new Vector2(delta.x, delta.y + required - height);
			}
		}

		/// <summary>
		/// 主菜单中文统一使用现有 10px 宿主，不再取决于 8px 宿主是否已经加载。
		/// 保留原来的 InfoText 和版权行强制大档规则。
		/// </summary>
		internal static bool ForceLarge(Text text)
		{
			if (text == null)
			{
				return false;
			}
			if (IsMainMenuText(text))
			{
				return true;
			}
			if (text.gameObject != null && text.gameObject.name == "InfoText")
			{
				return true;
			}
			string s = text.text;
			return !string.IsNullOrEmpty(s) && s.TrimStart().StartsWith("©2024");
		}

		/// <summary>取文本的基准字号：首次接管时记录，之后不再随游戏赋值改变档位。</summary>
		internal static int GetBaseSize(Text text, int current)
		{
			int id = text.GetInstanceID();
			int size;
			// 取历史见过的最大字号作为基准：游戏有时先用小字号（8）建对象，
			// 随后才按界面状态设成 12/10；只看第一次会把基准错误地锁在 8。
			if (!_baseFontSize.TryGetValue(id, out size) || current > size)
			{
				size = current;
				_baseFontSize[id] = size;
			}
			return size;
		}

		/// <summary>
		/// 按名字找字体宿主对象。
		///
		/// 只在**成功**时缓存：两个宿主位于不同的 serialized file，由 Addressables 异步加载，
		/// 游戏刚启动时可能只加载了一部分（例如标题场景只有 sharedassets0 = 10px 宿主）。
		/// 若把「未找到」也缓存下来，之后这些场景就再也取不到该档字体，只能回退游戏原版
		/// 日文字体（中文会缺字/发虚）。因此失败时允许重试，但限流为每秒一次，
		/// 避免每帧遍历全部对象。
		/// </summary>
		private static Font FindFont(int slot, string name)
		{
			if (FontCache[slot] != null)
			{
				return FontCache[slot];
			}
			float now = Time.unscaledTime;
			if (now - FontSearchTime[slot] < 1f)
			{
				return null;
			}
			FontSearchTime[slot] = now;
			try
			{
				Font[] all = Resources.FindObjectsOfTypeAll<Font>();
				for (int i = 0; i < all.Length; i++)
				{
					Font f = all[i];
					if (f != null && f.name == name)
					{
						FontCache[slot] = f;
						PatchUtil.Info("chinese font host found: " + name);
						return f;
					}
				}
			}
			catch (Exception e)
			{
				PatchUtil.Warn("font host search failed: " + e.Message);
			}
			return null;
		}

		/// <summary>取指定字号档位对应的中文字体（8 -> k8x12EXL，10 -> k8x12EXS）。</summary>
		internal static Font GetFontFor(int size)
		{
			return (size <= SizeSmall) ? FindFont(0, Font8Name) : FindFont(1, Font10Name);
		}

		/// <summary>
		/// 10px 设计宿主（k8x12EXS ← fusion-10px）。两处大字都用它：关卡选择 10px（1:1）、
		/// 过场标题 20px（2× 整数倍）。8px 宿主承载不了「糖/浆/饼」这类密笔画汉字
		/// （8px 设计网格里没有字腔），不能用于大字。未加载时返回 null，调用方回退普通路径。
		/// </summary>
		internal static Font GetTenDesignFont()
		{
			// slot 1 缓存的正是 10px 宿主（k8x12EXS），与 GetFontFor(>8) 共用同一份缓存。
			return FindFont(1, Font10Name);
		}

		/// <summary>当前语言是否为 Spanish（中文槽位）。反射调用以兼容 GetLanguage 的实际签名。</summary>
		internal static bool IsChineseLanguage()
		{
			if (_langProbeFailed)
			{
				return false;
			}
			try
			{
				if (_manager == null)
				{
					Type t = AccessTools.TypeByName("FizRpResidentFlagManager");
					if (t == null)
					{
						_langProbeFailed = true;
						PatchUtil.Warn("FizRpResidentFlagManager type not found; font replacement disabled");
						return false;
					}
					PropertyInfo p = t.GetProperty("Instance", BindingFlags.Public | BindingFlags.Static);
					if (p == null)
					{
						_langProbeFailed = true;
						PatchUtil.Warn("FizRpResidentFlagManager.Instance not found; font replacement disabled");
						return false;
					}
					_manager = p.GetValue(null, null);
				}
				if (_manager == null)
				{
					return false;
				}
				if (_getLanguage == null)
				{
					_getLanguage = _manager.GetType().GetMethod("GetLanguage", BindingFlags.Public | BindingFlags.Instance);
					if (_getLanguage == null)
					{
						_langProbeFailed = true;
						PatchUtil.Warn("GetLanguage not found; font replacement disabled");
						return false;
					}
				}
				ParameterInfo[] ps = _getLanguage.GetParameters();
				object result = (ps.Length == 0)
					? _getLanguage.Invoke(_manager, null)
					: _getLanguage.Invoke(_manager, new object[] { false });
				return Convert.ToInt32(result) == SpanishLanguageValue;
			}
			catch (Exception e)
			{
				_langProbeFailed = true;
				PatchUtil.Warn("language probe failed: " + e.Message);
				return false;
			}
		}

		private static readonly HashSet<int> _setterLogged = new HashSet<int>();

		/// <summary>
		/// 记录 Harmony 对 Text 字体/字号 setter 的拦截调用（每个 Text 只记一次）。
		/// 用于确认拦截是否真的生效：若 13 个用原版字体的中文 Text 从未出现在这里，
		/// 说明游戏并非通过属性赋值来设置字体（拦截不到），只能靠每帧扫描兜底。
		/// </summary>
		internal static void NoteSetterCall(string which, Text text, int value)
		{
			if (_setterLogged.Count >= 40 || text == null)
			{
				return;
			}
			int id = text.GetInstanceID();
			if (!_setterLogged.Add(id))
			{
				return;
			}
			string c = text.text ?? string.Empty;
			PatchUtil.Info(string.Format(
				"[setter] {0} '{1}' value={2}",
				which, c.Length > 18 ? c.Substring(0, 18) : c, value));
		}

		/// <summary>
		/// 是否含日文假名（平假名 / 片假名）。
		///
		/// 用途：插件按语言决定是否介入，但语言查询读的是**存档**里的值，未必等于当前界面语言
		/// （玩家在标题界面切语言后存档可能还没更新）。日文文本必然含假名、中文文本不含，
		/// 故以「含假名 → 不处理」兜底，避免切到日语后插件仍改动日文文本的字号。
		/// </summary>
		internal static bool HasKana(string s)
		{
			if (string.IsNullOrEmpty(s))
			{
				return false;
			}
			for (int i = 0; i < s.Length; i++)
			{
				char c = s[i];
				// 片假名中点「・」(U+30FB) 不是假名：中文译文同样用它作并列分隔符。
				// 它落在 U+30A0..U+30FF 里，早期版本把它当假名 → 含它的译文被整段跳过，
				// 永远不换字体，仍用原版日文/拉丁字体渲染中文（缺字回退 → 抗锯齿发虚）。
				// 实测：全库 1411 行译文里，落在 U+3040..U+30FF 的字符只有「・」，共 18 行，
				// 含「跳跃・游泳」「攻击・冲刺」以及整块暂停面板 '------动作------…'。
				// 若日后译文用到该段内其它非假名符号（U+30A0 ゠、U+30FC ー 等），在此一并排除。
				if (c == '\u30FB')
				{
					continue;
				}
				if ((c >= '぀' && c <= 'ゟ') || (c >= '゠' && c <= 'ヿ'))
				{
					return true;
				}
			}
			return false;
		}

		/// <summary>
		/// 文本是否含中日韩字符（汉字 / 扩展 A / CJK 标点 / 全角形式）。
		/// 纯拉丁文本（百分比、版本号、LIFE / COIN / REST、Shift 等）必须保持原版字体，
		/// 否则会破坏这些原本按拉丁像素字体设计的显示。
		/// </summary>
		internal static bool HasCJK(string s)
		{
			if (string.IsNullOrEmpty(s))
			{
				return false;
			}
			for (int i = 0; i < s.Length; i++)
			{
				char c = s[i];
				if ((c >= '\u4E00' && c <= '\u9FFF')
					|| (c >= '\u3400' && c <= '\u4DBF')
					|| (c >= '\u3000' && c <= '\u303F')
					|| (c >= '\uFF00' && c <= '\uFFEF'))
				{
					return true;
				}
			}
			return false;
		}

		/// <summary>
		/// Pause footers only: wait for an active Canvas instance and set an absolute X offset.
		/// Do not shift prefab assets, do not add to a copied offset, and never move Y or Z.
		/// </summary>
		private static void SnapPauseHint(Text text, int id)
		{
			Canvas canvas = text.canvas;
			if (!PauseHintPixelPolicy.Applies(text.gameObject.name, text.isActiveAndEnabled,
				canvas != null, HasCJK(text.text), HasKana(text.text)))
			{
				return;
			}
			Font font = text.font;
			if (font == null || font.name != Font10Name || text.fontSize != SizeLarge
				|| text.resizeTextForBestFit)
			{
				return;
			}
			RectTransform rect = text.rectTransform;
			if (rect.localRotation != Quaternion.identity
				|| Mathf.Abs(rect.localScale.x - 1f) > 0.001f
				|| Mathf.Abs(rect.localScale.y - 1f) > 0.001f
				|| Mathf.Abs(rect.pivot.x - 0.5f) > 0.001f
				|| Mathf.Abs(rect.anchorMin.x) > 0.001f
				|| Mathf.Abs(rect.anchorMax.x - 1f) > 0.001f
				|| (text.alignment != TextAnchor.UpperCenter
					&& text.alignment != TextAnchor.MiddleCenter
					&& text.alignment != TextAnchor.LowerCenter))
			{
				return;
			}
			Vector2 position = rect.anchoredPosition;
			float ppu = text.pixelsPerUnit;
			if (!PauseHintPixelPolicy.IsFinite(position.x) || !PauseHintPixelPolicy.IsFinite(position.y)
				|| !PauseHintPixelPolicy.IsFinite(ppu) || ppu <= 0f)
			{
				return;
			}
			Rect box = rect.rect;
			PauseHintState state;
			if (!_pauseHints.TryGetValue(id, out state) || state.Content != text.text
				|| state.Font != font || state.Size != text.fontSize || state.CanvasId != canvas.GetInstanceID()
				|| state.Ppu != ppu || state.XMin != box.xMin || state.Width != box.width)
			{
				float target;
				if (!PauseHintPixelPolicy.TryTargetX(box.xMin, box.width, text.preferredWidth, out target))
					return;
				state = new PauseHintState {
					Content = text.text, Font = font, Size = text.fontSize, CanvasId = canvas.GetInstanceID(),
					Ppu = ppu, XMin = box.xMin, Width = box.width, TargetX = target
				};
				_pauseHints[id] = state;
			}
			if (Mathf.Abs(position.x - state.TargetX) <= 0.001f) return;
			rect.anchoredPosition = new Vector2(state.TargetX, position.y);
			if (_pauseHintLogged.Count < 80 && _pauseHintLogged.Add(id))
				PatchUtil.Info(string.Format("[pause-hint] {0} id={1} x={2:F3}->{3:F3} y={4:F3} absolute-baseline=0",
					text.gameObject.name, id, position.x, state.TargetX, position.y));
		}

		/// <summary>
		/// 把文字内容起点补偿到「整数设计像素」上 —— 修的是同屏内一部分文本锐利、
		/// 另一部分发虚的最终原因。
		///
		/// 实测定论（2026-10-16）：底部说明行的文字像素**只有 128 与 255 两个灰度值**，
		/// 128 恰好是 50% 混合；笔画在屏幕上是整齐的 4 像素块（= 1 个设计像素，
		/// Canvas.scaleFactor = 4）。「整格 50%」只有一个成因：字形轮廓相对设计网格
		/// 偏了半个设计像素。
		///
		/// 偏移量可以对上：该行中心对齐，内容起点 = rect.xMin + (rect.width - preferredWidth)/2；
		/// 日志里 rect 宽 = 256 canvas 单位，而用现役 fusion-10px 离线算出的行宽 = 255.000，
		/// 于是起点 = (256 - 255)/2 = **0.5 canvas 单位 = 半个设计像素**（字号 == 设计尺寸时
		/// 1 canvas 单位 = 1 个设计像素）。同一行实测屏幕跨度 ≈1020px = 255 × 4，与 255 吻合。
		///
		/// 对照：悬挂的「动作」面板 rect 与行宽之差是偶数，起点落在整格上，所以一直锐利。
		///
		/// 做法：沿 x 与 y 两轴各平移 ≤0.5 个网格，就近取整，使内容起点落整。
		/// 网格 = 1 个设计像素占多少 canvas 单位（见 DesignPixelGrid）：普通 8/10px 小字
		/// 为 1，两处大字（10px 宿主 @20px）为 2，故大字单轴位移上限 1 canvas 单位
		/// （scaleFactor 4 下即 4 屏幕像素）。
		/// 该修正自稳定：一旦落整，residual 变 0，后续帧不再动；若游戏挪动了 rect，
		/// 靠 _snapChecked 里记录的 (xMin, width) 发现并重新核算。
		/// 不动 fontSize / 不改文案，视觉位移上限 2 屏幕像素（小字）/ 4 屏幕像素（大字）。
		/// </summary>
		internal static void SnapContentToPixelGrid(Text text, int id)
		{
			if (text != null && PauseHintPixelPolicy.IsTarget(text.gameObject.name))
			{
				SnapPauseHint(text, id);
				return;
			}
			if (text == null)
			{
				return;
			}
			RectTransform rt = text.rectTransform;
			if (rt == null)
			{
				return;
			}
			// 有旋转/缩放时本地单位与 canvas 单位不再一致，设计像素-整数的对应关系不成立，跳过。
			if (rt.localRotation != Quaternion.identity || Mathf.Abs(rt.localScale.x - 1f) > 0.001f)
			{
				return;
			}
			Rect r = rt.rect;
			Vector2 key = new Vector2(r.xMin, r.width);
			Vector2 prev;
			if (_snapChecked.TryGetValue(id, out prev)
				&& Mathf.Abs(prev.x - key.x) < 0.0005f && Mathf.Abs(prev.y - key.y) < 0.0005f)
			{
				return; // 几何未变 → 上次的核算结论仍有效
			}
			_snapChecked[id] = key;

			float lineW = text.preferredWidth;
			float lineH = text.preferredHeight;
			TextAnchor a = text.alignment;
			float originX;
			if (a == TextAnchor.UpperLeft || a == TextAnchor.MiddleLeft || a == TextAnchor.LowerLeft)
			{
				originX = r.xMin;
			}
			else if (a == TextAnchor.UpperRight || a == TextAnchor.MiddleRight || a == TextAnchor.LowerRight)
			{
				originX = r.xMax - lineW;
			}
			else
			{
				originX = r.xMin + (r.width - lineW) * 0.5f;
			}

			// 纵向同理。早期版本只算了 x，而且**x 已在整格时直接 return** —— 于是
			// 「x 对齐、y 偏半格」的文本永远修不到，表现就是同一屏里有的文字锐利、
			// 有的整行发虚（底栏说明文字就是这个症状：pos=(0.50,0.81)，sf=3 时
			// x 偏 0.5 格但 y 偏 0.43 格，实测文字像素是一整串中间灰而非单一纯色）。
			float originY;
			if (a == TextAnchor.UpperLeft || a == TextAnchor.UpperCenter || a == TextAnchor.UpperRight)
			{
				originY = r.yMax - lineH;
			}
			else if (a == TextAnchor.MiddleLeft || a == TextAnchor.MiddleCenter || a == TextAnchor.MiddleRight)
			{
				originY = r.yMin + (r.height - lineH) * 0.5f;
			}
			else
			{
				originY = r.yMin;
			}

			// 网格换算（2026-10-24 复核）：Unity 动态字体按 fontSize 光栅化，1 个设计像素
			// = fontSize / 设计尺寸 个 canvas 单位（10px 宿主 @20px 时 1 设计像素 = 2 单位）。
			// 要让笔画边缘落在整格上，内容起点须对齐到**设计像素**的整数倍：
			// 普通 8/10px 小字 fontSize == 设计尺寸，1 设计像素 = 1 canvas 单位，
			// 故按整 canvas 单位对齐即可（半 canvas 单位偏移实测整格 50% 灰）；
			// 大字（10px 宿主 @20px）1 设计像素 = 2 canvas 单位，需对齐到 2 单位。
			// 设计尺寸的整数倍另决定**光栅内部**有无灰阶（非整数倍放大会把字腔糊死，
			// 见 LargeTitlePixelPolicy），与这里的对齐网格是两件事。
			float grid = DesignPixelGrid(text);
			float shiftX = NearestGridShift(originX, grid);
			float shiftY = NearestGridShift(originY, grid);
			if (shiftX == 0f && shiftY == 0f)
			{
				return; // 两轴都已在整格（或浮点噪声范围内）
			}
			Vector2 pos = rt.anchoredPosition;
			rt.anchoredPosition = new Vector2(pos.x + shiftX, pos.y + shiftY);
			if (_snapLogged < 40)
			{
				_snapLogged++;
				string c = text.text ?? string.Empty;
				PatchUtil.Info(string.Format(
					"[snap] '{0}' originX={1:F3} fx={2:F3} shiftX={3:F3} "
					+ "originY={4:F3} fy={5:F3} shiftY={6:F3} rect={7:F1}x{8:F1} "
					+ "line={9:F1}x{10:F1} align={11} grid={12:F1}",
					c.Length > 16 ? c.Substring(0, 16) : c, originX,
					originX - Mathf.Floor(originX), shiftX, originY,
					originY - Mathf.Floor(originY), shiftY, r.width, r.height,
					lineW, lineH, a, grid));
			}
		}

		/// <summary>把内容起点沿某一轴就近挪到整格上；已在整格（含浮点噪声）时返回 0。</summary>
		/// <param name="origin">该轴上的内容起点（canvas 单位）。</param>
		/// <param name="grid">对齐网格（canvas 单位）。1 = 整 canvas 单位。</param>
		private static float NearestGridShift(float origin, float grid)
		{
			if (grid < 1f)
			{
				grid = 1f;
			}
			float steps = origin / grid;
			float frac = steps - Mathf.Floor(steps);
			if (frac <= 0.02f || frac >= 0.98f)
			{
				return 0f;
			}
			return ((frac <= 0.5f) ? -frac : (1f - frac)) * grid;
		}

		/// <summary>
		/// 当前文本的对齐网格（canvas 单位）：1 个设计像素占多少 canvas 单位。
		/// 依据是**实际挂载的宿主字体**与当前 fontSize：8px 宿主 @8px → 1；
		/// 10px 宿主 @10px → 1；10px 宿主 @20px（两处大字）→ 2。
		/// 非整数倍时退回 1（保守：宁可少对齐，也不要按错误的网格平移）。
		/// </summary>
		private static float DesignPixelGrid(Text text)
		{
			if (text == null)
			{
				return 1f;
			}
			Font font = text.font;
			int design = 0;
			if (font != null)
			{
				if (font.name == Font8Name)
				{
					design = 8;
				}
				else if (font.name == Font10Name)
				{
					design = 10;
				}
			}
			if (design <= 0 || text.fontSize <= 0)
			{
				return 1f;
			}
			int size = text.fontSize;
			if (size % design != 0)
			{
				return 1f;
			}
			return size / (float)design;
		}


		/// <summary>把单个 Text 换成对应字号档位的中文字体（仅含 CJK 的文本；纯拉丁保持原版）。</summary>
		internal static void Apply(Text text)
		{
			if (text == null)
			{
				return;
			}
			bool forceInfo = ForceLarge(text);
			int baseSize = GetBaseSize(text, text.fontSize);
			int want = forceInfo ? SizeLarge : QuantizeSize(baseSize);
			Font f = GetFontFor(want);
			// 两处大字（关卡选择世界名 / 中央过场标题）：统一改用 10px 设计宿主，字号取
			// 各自版式余量允许的整数倍（关卡选择 10px=1:1，过场标题 20px=2×），消除
			// 非整数倍放大造成的字腔糊死（见 LargeTitlePixelPolicy）。
			// 宿主未加载时回退上面的普通路径，不丢文本。
			if (!forceInfo)
			{
				int bigSize = LargeTitlePixelPolicy.TargetSize(text.gameObject.name, text.text);
				Font bigFont = bigSize > 0 ? GetTenDesignFont() : null;
				if (bigFont != null)
				{
					want = bigSize;
					f = bigFont;
				}
			}
			if (f == null && want == SizeSmall)
			{
				// 两个字体宿主位于不同的 serialized file，而场景只加载其中一部分
				// （例：标题场景加载 sharedassets0 = 10px 宿主，不含 sharedassets3 = 8px 宿主）。
				// 此时不可回退到游戏原版字体（那会用日文字形渲染中文），而应改用当前场景里可用的档位。
				want = SizeLarge;
				f = GetFontFor(SizeLarge);
			}
			if (f == null)
			{
				return;
			}
			// 「该不该由我们接管」必须先判定，再动检测器状态。
			//
			// 早期版本把 _appliedOnce.Add 放在这之前（就在下面那个位置），于是拉丁文本、
			// 含假名的日文文本、以及被 HasKana 误判的文本，虽然一行字体都没改过，
			// 下一帧就会命中「标记过 + 字体不是我们的」→ 刷出大量 [reverted] 假阳性。
			// 这批假阳性掩盖了真正的问题（有一批译文根本没被处理过）。
			// 含汉字的文本由我们接管；即使夹有假名（如版权行「にじいろドラゴン（虹色龙）」、
			// 结局作者名），我们的 fusion 字体同时含假名与汉字，能完整显示。
			// 纯假名（无汉字）的日文文本仍不介入，避免把未翻译的日文界面换成中文字体。
			if (!HasCJK(text.text) && !forceInfo)
			{
				// 纯拉丁 / 纯假名文本：保持原版字体与字号，绝不改动
				return;
			}

			// 被改回检测：只在「确实由我们接管过的文本」上做，且 was 报的是
			// 上一次我们亲眼确认过的字体，不用期望值 f.name 冒充。
			int _id = text.GetInstanceID();
			Font prevSeen;
			if (_lastSeen.TryGetValue(_id, out prevSeen) && prevSeen != null && text.font != prevSeen)
			{
				if (_reverted.Add(_id))
				{
					string c = text.text ?? string.Empty;
					PatchUtil.Warn(string.Format(
						"[reverted] '{0}' was {1}, now {2} (size={3})",
						c.Length > 18 ? c.Substring(0, 18) : c,
						prevSeen.name, (text.font != null) ? text.font.name : "(null)", text.fontSize));
				}
			}

			// 快速路径：字体已是我们的中文字体且字号已对齐 → 说明此前处理过，直接跳过。
			// （每帧扫描下这是稳定态的唯一开销：一次引用比较 + 两次整数比较。）
			if (text.font == f && text.fontSize == want && !text.resizeTextForBestFit)
			{
				_lastSeen[_id] = f;
				FitMainMenuHeight(text);
				// 暂停提示检查挂载状态并按绝对偏移纠正；其它 UI 保持原有策略。
				SnapContentToPixelGrid(text, _id);
				return;
			}
			try
			{
				// 诊断：每个 Text 首次处理时记录真实渲染参数（最多 60 条），
				// 用于定位「字形模糊」是字号、缩放还是 Canvas 比例导致的。
				if (DiagCount < 200 && DiagSeen.Add(text.GetInstanceID()))
				{
					DiagCount++;
					try
					{
						Canvas cv = text.canvas;
						string c = (text.text ?? string.Empty);
						if (c.Length > 22)
						{
							c = c.Substring(0, 22);
						}
						if (c.Length > 22)
						{
							c = c.Substring(0, 22);
						}
						Vector3 wp = text.rectTransform.position;
						PatchUtil.Info(string.Format(
							"[diag2] '{0}' size={1} font={2} pos=({3:F2},{4:F2}) pref=({5:F1},{6:F1}) rect=({7:F1},{8:F1}) canvas={9} rm={10} sf={11:F2} pp={12} active={13}",
							c, text.fontSize, text.font.name,
							wp.x, wp.y,
							text.preferredWidth, text.preferredHeight,
							text.rectTransform.rect.width, text.rectTransform.rect.height,
							(cv != null) ? cv.name : "(null)",
							(cv != null) ? ((int)cv.renderMode).ToString() : "-",
							(cv != null) ? cv.scaleFactor : -1f,
							(cv != null) && cv.pixelPerfect,
							text.gameObject.activeInHierarchy));
					}
					catch (Exception)
					{
					}
				}
				Font before = text.font;
				if (before != f)
				{
					text.font = f;
					// 赋值后立即验证：若 Unity 拒绝这次赋值（字体不可用等），当场记录。
					if (text.font != f && _assignFail.Add(text.GetInstanceID()))
					{
						string cc = text.text ?? string.Empty;
						PatchUtil.Warn(string.Format(
							"[assignfail] '{0}' wanted {1}, got {2}",
							cc.Length > 18 ? cc.Substring(0, 18) : cc,
							f.name, (text.font != null) ? text.font.name : "(null)"));
					}
				}
				// 记录我们亲眼确认过的字体（成功赋值后），供下一帧的「被改回」检测比对。
				if (text.font == f)
				{
					_lastSeen[text.GetInstanceID()] = f;
				}
				// 设置未生效检测：少数 Text 会被游戏代码改回去（例如文本与字体同时重设），
				// 结果仍用原版日文字体渲染中文 → 缺字显示为「口」。
				if (_notApplied.Add(text.GetInstanceID()) && text.font != f)
				{
					PatchUtil.Warn(string.Format(
						"[notapplied] '{0}' font={1} wanted={2} size={3}",
						(text.text ?? string.Empty).Length > 20
							? text.text.Substring(0, 20) : (text.text ?? string.Empty),
						(text.font != null) ? text.font.name : "(null)", f.name, text.fontSize));
				}
				// 关闭 Best Fit：开启时 Unity 会自行挑选（通常是非整数的）字号，
				// 破坏点阵字体的 1:1 像素对齐，渲染出来就是模糊的。
				if (text.resizeTextForBestFit)
				{
					text.resizeTextForBestFit = false;
				}
				// 像素完美：UI 元素若落在非整数像素位置，点阵字形会被双线性采样成模糊。
				// 这也解释了「同一段提示文本，第 2 页锐利而第 1/3 页模糊」——三页的位置小数部分不同。
				Canvas pixelCanvas = text.GetComponentInParent<Canvas>();
				if (pixelCanvas != null && !pixelCanvas.pixelPerfect)
				{
					pixelCanvas.pixelPerfect = true;
				}
				// 普通小字对齐到 8/10；两处大字按 LargeTitlePixelPolicy 取 10px/20px
				// 整数倍，不压缩成小字。
				if (text.fontSize != want)
				{
					text.fontSize = want;
				}
				FitMainMenuHeight(text);
				// 像素网格对齐：把文字内容起点补偿到整数设计像素上。
				// 这是「同一屏内有锐利也有发虚」的最终解释（见 SnapContentToPixelGrid 注释）。
				SnapContentToPixelGrid(text, _id);
				// 缺字形检测：若字体缺少文本中的字符，Unity 会绘制空白方块（口），
				// 说明该文本实际没走我们的中文字体（或字体覆盖不全）。
				if (DiagCount < 400 && _missingLogged.Add(text.GetInstanceID()))
				{
					string t = text.text ?? string.Empty;
					string missing = string.Empty;
					for (int i = 0; i < t.Length && i < 60; i++)
					{
						char ch = t[i];
						if (ch == (char)10 || ch == (char)13 || ch == ' ')
						{
							continue;
						}
						if (!f.HasCharacter(ch))
						{
							missing += ch;
						}
					}
					if (missing.Length > 0)
					{
						DiagCount++;
						PatchUtil.Warn(string.Format(
							"[missing] font={0} size={1} lacks '{2}' in text '{3}'",
							f.name, want, missing,
							t.Length > 24 ? t.Substring(0, 24) : t));
					}
					else
					{
						_missingLogged.Remove(text.GetInstanceID());
					}
				}
				// 溢出自动降档（实验性关闭：怀疑它切换到另一档字体正是底部提示模糊的来源）
				if (false && want > SizeSmall)
				{
					float boxWidth = text.rectTransform.rect.width;
					if (boxWidth > 0f && text.preferredWidth > boxWidth + 0.5f)
					{
						Font small = GetFontFor(SizeSmall);
						if (small != null)
						{
							text.font = small;
							text.fontSize = SizeSmall;
						}
					}
				}
			}
			catch (Exception e)
			{
				// 单个对象失败不影响其它文本；但必须留痕，否则"字体没换"会毫无线索。
				if (_applyFailed.Add(text.GetInstanceID()))
				{
					string cc = text.text ?? string.Empty;
					PatchUtil.Warn(string.Format(
						"[applyfail] '{0}' font={1} size={2} -> {3}",
						cc.Length > 18 ? cc.Substring(0, 18) : cc,
						(text.font != null) ? text.font.name : "(null)",
						text.fontSize, e.Message));
				}
			}
		}

		/// <summary>
		/// TMP（TextMeshProUGUI）中文字体资源，运行时从我们的 Font 创建。
		/// 关键：渲染模式必须是 RASTER_HINTED（无抗锯齿光栅化）——
		/// TMP 默认的 SDF 距离场模式会把点阵字形渲染成模糊的边缘。
		/// </summary>
		private static TMP_FontAsset _tmpAsset;
		private static bool _tmpSearched;

		internal static TMP_FontAsset GetChineseTMPFont()
		{
			if (_tmpSearched)
			{
				return _tmpAsset;
			}
			_tmpSearched = true;
			Font f = GetFontFor(SizeLarge);
			if (f == null)
			{
				PatchUtil.Warn("TMP: base font host unavailable; TMP text keeps the game font");
				return null;
			}
			try
			{
				// 只使用默认重载，且不要在此之前尝试任何"更理想"的重载。
				//
				// 实测结论（务必保留此注释）：
				//  * 带 GlyphRenderMode 参数的重载在本游戏运行时必定抛 ArgumentNullException
				//    （游戏的 TMP 是预烘焙资产，运行时生成字形所需的内部依赖未随构建打包）。
				//  * 更严重的是：这些**失败的调用会污染 TMP 内部 FontEngine 的静态状态**，
				//    导致随后默认重载"成功"返回的资源字形错乱，对话文本显示为乱码。
				//  * 因此这里只调用默认重载（SDF 渲染，略糊但字形正确），不再尝试其它重载。
				_tmpAsset = TMP_FontAsset.CreateFontAsset(f);
				if (_tmpAsset != null)
				{
					_tmpAsset.name = "FizRPChineseTMP";
					PatchUtil.Info("TMP font asset created (default overload)");
				}
				else
				{
					PatchUtil.Warn("TMP default overload returned null; TMP text keeps the game font");
				}
			}
			catch (Exception e)
			{
				PatchUtil.Warn("TMP font asset creation failed: " + e.Message);
			}
			return _tmpAsset;
		}

		/// <summary>把单个 TMP 文本换成中文 TMP 字体并对齐字号。</summary>
		internal static void ApplyTMP(TMP_Text tmp)
		{
			if (tmp == null)
			{
				return;
			}
			if (!HasCJK(tmp.text))
			{
				// 纯拉丁 / 纯假名：不介入；含汉字的混合专名（假名+汉字）继续接管
				return;
			}
			try
			{
				TMP_FontAsset asset = GetChineseTMPFont();
				if (asset == null)
				{
					return;
				}
				if (tmp.font != asset)
				{
					tmp.font = asset;
				}
				int want = QuantizeSize((int)tmp.fontSize);
				if (tmp.fontSize != want)
				{
					tmp.fontSize = want;
				}
			}
			catch (Exception)
			{
			}
		}

		/// <summary>全场景扫描（含未激活对象，因为切换语言时面板可能未激活）。</summary>
		internal static void ApplyAll()
		{
			if (!IsChineseLanguage())
			{
				return;
			}
			if (FindFont(0, Font8Name) == null && FindFont(1, Font10Name) == null)
			{
				return;
			}
			try
			{
				// 缓存 Text 列表：FindObjectsOfTypeAll 每帧调用会明显掉帧，故每秒刷新一次，
				// 每帧只遍历缓存（约百余个引用，稳定态下每个都走 O(1) 快速路径）。
				_cacheAge += Time.unscaledDeltaTime;
				if (_textCache == null || _cacheAge >= 1f)
				{
					_textCache = Resources.FindObjectsOfTypeAll<Text>();
					_cacheAge = 0f;
				}
				Text[] all = _textCache;
				for (int i = 0; i < all.Length; i++)
				{
					Text t = all[i];
					if (t == null || t.gameObject == null)
					{
						continue;
					}
					// 注意：不要用 scene.IsValid() 过滤！
					// 它会误伤正在显示的 UI（DontDestroyOnLoad 场景下的对象），
					// 使这些 Text 完全不被处理、继续用原版日文字体渲染中文 → 缺字显示为「口」。
					Apply(t);
				}

				// TMP 组件同样处理（游戏里版权行等用的是 TextMeshProUGUI）
				_cacheAgeTmp += Time.unscaledDeltaTime;
				if (_tmpCache == null || _cacheAgeTmp >= 1f)
				{
					_tmpCache = Resources.FindObjectsOfTypeAll<TMP_Text>();
					_cacheAgeTmp = 0f;
				}
				TMP_Text[] tmps = _tmpCache;
				for (int i = 0; i < tmps.Length; i++)
				{
					TMP_Text t = tmps[i];
					if (t == null || t.gameObject == null)
					{
						continue;
					}
					// 同上：不过滤 scene.IsValid()
					ApplyTMP(t);
				}
			}
			catch (Exception e)
			{
				PatchUtil.Warn("font sweep failed: " + e.Message);
			}
		}
	}

	/// <summary>
	/// 每帧扫描并纠正。
	///
	/// 为什么必须每帧：Text 的字号在场景加载时由**序列化数据**直接填充，不经过
	/// Text.set_fontSize（Harmony 拦截不到），因此游戏画面出现的瞬间字号是错的（模糊），
	/// 必须尽快纠正。0.5 秒的间隔会让玩家明显看到「先大号模糊、再跳成小号清晰」。
	///
	/// 开销控制：Apply 内部先做 O(1) 的字号比对，只有不符时才走文本扫描与字体重设，
	/// 稳定状态下每帧几乎零成本。
	/// </summary>
	internal sealed class FontApplierBehaviour : MonoBehaviour
	{
		private void Awake()
		{
			try
			{
				// 渲染前最后一刻再纠正一次。
				// 若游戏代码在 LateUpdate 里把我们设的字体改回去，仅靠 LateUpdate 会来不及，
				// 而 onBeforeRender 在所有脚本之后、真正渲染之前触发，能覆盖这种情况。
				Application.onBeforeRender += FontApplier.ApplyAll;
				PatchUtil.Info("hooked Application.onBeforeRender for last-moment font correction");
			}
			catch (Exception e)
			{
				PatchUtil.Warn("onBeforeRender hook failed: " + e.Message);
			}
		}

		private void LateUpdate()
		{
			try
			{
				FontApplier.ApplyAll();
			}
			catch (Exception)
			{
				// 绝不让异常冒出到 Unity 主循环
			}
		}
	}

	/// <summary>
	/// LocalizedText 是唯一会按语言重设字体的组件（每 10 帧检查语言并覆盖 text.font）。
	/// 在其之后再压一次，避免它把字体切回日文字体。
	/// </summary>
	[HarmonyPatch(typeof(LocalizedText), "CheckLanguage")]
	internal static class LocalizedTextCheckPatch
	{
		private static void Postfix(LocalizedText __instance)
		{
			try
			{
				if (__instance == null || !FontApplier.IsChineseLanguage())
				{
					return;
				}
				FontApplier.Apply(__instance.GetComponent<Text>());
			}
			catch (Exception)
			{
			}
		}
	}

	/// <summary>
	/// 拦截游戏对 Text.fontSize 的赋值：游戏每设一次就当场改成与字体设计尺寸对齐的值。
	///
	/// 这是解决「切换画面时先是大号模糊、约 0.5 秒后才跳成小号清晰」的关键：
	/// 那个延迟正是 0.5 秒轮询扫描与游戏赋值在竞争（游戏的值显示期间就是模糊的）。
	/// 改为在属性写入点直接纠正后，画面一出现就是正确字号。
	/// </summary>
	[HarmonyPatch(typeof(Text), "set_fontSize")]
	internal static class TextFontSizePatch
	{
		private static void Prefix(Text __instance, ref int value)
		{
			try
			{
				if (__instance == null || !FontApplier.IsChineseLanguage() || !FontApplier.HasCJK(__instance.text))
				{
					return;
				}
				FontApplier.NoteSetterCall("set_fontSize", __instance, value);
				int baseSize = FontApplier.GetBaseSize(__instance, value);
				value = FontApplier.ForceLarge(__instance)
					? FontApplier.SizeLarge
					: FontApplier.QuantizeSize(baseSize);
				// 两处大字：字号取各自版式余量允许的整数倍（关卡选择 10、过场标题 20），
				// 避免游戏赋值后到下一次扫描之间闪一帧非整数倍的模糊字号。
				if (!FontApplier.ForceLarge(__instance))
				{
					int bigSize = LargeTitlePixelPolicy.TargetSize(
						__instance.gameObject.name, __instance.text);
					if (bigSize > 0 && FontApplier.GetTenDesignFont() != null)
					{
						value = bigSize;
					}
				}
			}
			catch (Exception)
			{
			}
		}
	}

	/// <summary>拦截 Text.font 赋值：把字体换成当前字号档位对应的中文字体。</summary>
	[HarmonyPatch(typeof(Text), "set_font")]
	internal static class TextFontPatch
	{
		private static void Prefix(Text __instance, ref Font value)
		{
			try
			{
				if (__instance == null || !FontApplier.IsChineseLanguage() || !FontApplier.HasCJK(__instance.text))
				{
					return;
				}
				FontApplier.NoteSetterCall("set_font", __instance, 0);
				int want = FontApplier.ForceLarge(__instance)
					? FontApplier.SizeLarge
					: FontApplier.QuantizeSize(
						FontApplier.GetBaseSize(__instance, __instance.fontSize));
				Font f = FontApplier.GetFontFor(want);
				// 两处大字改用 10px 设计宿主（10px=1:1 / 20px=2×），与 Apply 的取字体一致。
				if (!FontApplier.ForceLarge(__instance))
				{
					int bigSize = LargeTitlePixelPolicy.TargetSize(
						__instance.gameObject.name, __instance.text);
					if (bigSize > 0)
					{
						Font bigFont = FontApplier.GetTenDesignFont();
						if (bigFont != null)
						{
							f = bigFont;
						}
					}
				}
				if (f != null)
				{
					value = f;
				}
			}
			catch (Exception)
			{
			}
		}
	}
}
