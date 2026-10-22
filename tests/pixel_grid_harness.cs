// Tests the actual pure policy with live-capture widths/offsets, not a fake Unity renderer.
using System;
using FizRPLangMenu;

internal static class PauseHintPixelHarness
{
    private static void Check(bool value)
    {
        if (!value) throw new Exception("Pause hint policy regression");
    }

    private static float Target(float width, float textWidth)
    {
        float value;
        Check(PauseHintPixelPolicy.TryTargetX(-width / 2, width, textWidth, out value));
        return value;
    }

    private static float Apply(float inheritedX, bool active, bool hasCanvas, float textWidth)
    {
        if (!PauseHintPixelPolicy.Applies("ButtomText_Treasure", active, hasCanvas, true, false))
            return inheritedX;
        return Target(512, textWidth); // Assign, do not add to inheritedX.
    }

    private static int Main(string[] args)
    {
        try { Run(args[0]); return 0; }
        catch (Exception) { Console.WriteLine("Pause hint policy regression: " + args[0]); return 1; }
    }

    private static void Run(string name)
    {
        switch (name)
        {
            case "scope":
                Check(PauseHintPixelPolicy.IsTarget("ButtomText_Chara"));
                Check(PauseHintPixelPolicy.IsTarget("ButtomText_Menu"));
                Check(PauseHintPixelPolicy.IsTarget("ButtomText_Treasure"));
                Check(!PauseHintPixelPolicy.IsTarget("InfoText"));
                Check(!PauseHintPixelPolicy.IsTarget("TextTreasure"));
                Check(!PauseHintPixelPolicy.IsTarget("ButtomText_Treasure_Other"));
                Check(!PauseHintPixelPolicy.IsTarget(null));
                break;
            case "prefab":
                Check(Apply(0, false, false, 155) == 0);
                Check(Apply(0, true, false, 145) == 0);
                Check(Apply(-0.5f, false, true, 145) == -0.5f);
                break;
            case "clone":
                // Live clear instance X=-0.5; later instance inherited that offset,
                // then legacy code shifted it again to X=-1.0. Both must normalize to -0.5.
                Check(Apply(0, true, true, 145) == -0.5f);
                Check(Apply(-0.5f, true, true, 145) == -0.5f);
                Check(Apply(-1f, true, true, 145) == -0.5f);
                break;
            case "idempotent":
                float current = -0.5f;
                for (int i = 0; i < 1000; i++) current = Apply(current, true, true, 145);
                Check(current == -0.5f);
                for (int generation = 0; generation < 20; generation++)
                    Check(Apply(current, true, true, 145) == -0.5f);
                break;
            case "text-change":
                Check(Apply(-0.5f, true, true, 210) == 0);
                Check(Apply(0, true, true, 145) == -0.5f);
                Check(Apply(-1f, true, true, 210) == 0);
                break;
            case "measured-widths":
                Check(Target(256, 255) == -0.5f);
                Check(Target(512, 210) == 0);
                Check(Target(512, 145) == -0.5f);
                break;
            case "invalid":
                float output;
                Check(!PauseHintPixelPolicy.TryTargetX(float.NaN, 512, 145, out output));
                Check(!PauseHintPixelPolicy.TryTargetX(-256, float.PositiveInfinity, 145, out output));
                Check(!PauseHintPixelPolicy.TryTargetX(-256, 512, float.NaN, out output));
                Check(!PauseHintPixelPolicy.TryTargetX(-256, 512, 0, out output));
                Check(!PauseHintPixelPolicy.TryTargetX(-256, 0, 145, out output));
                Check(!PauseHintPixelPolicy.TryTargetX(-256, 512, -1, out output));
                Check(!PauseHintPixelPolicy.TryTargetX(float.MaxValue, float.MaxValue, 1, out output));
                break;
            case "language":
                Check(!PauseHintPixelPolicy.Applies("ButtomText_Treasure", true, true, true, true));
                Check(!PauseHintPixelPolicy.Applies("ButtomText_Treasure", true, true, false, false));
                Check(PauseHintPixelPolicy.Applies("ButtomText_Treasure", true, true, true, false));
                break;
            default: throw new ArgumentException("Unknown test case");
        }
    }
}
