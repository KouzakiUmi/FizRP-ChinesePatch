# -*- coding: utf-8 -*-
"""像素字渲染器：用项目同款字体把中文渲染成「1 位像素 + 描边」，供贴图重制使用。

设计要点（为什么必须这么做）：
1. 必须**阈值化**成 1 位 alpha。像素字体在非整数倍尺寸下会被 FreeType 抗锯齿，
   边缘出现灰阶杂边；阈值化后每个像素非 0 即 255，与游戏原生像素画一致。
2. 描边用「掩膜膨胀 1px」，而不是再画一遍更大的字——后者会改变笔画宽度。
3. 对齐用「内框 + 锚点」计算，避免每张图手调坐标。

用法示例：
    python render_text.py --font fonts/fusion-pixel-12px-proportional-zh_hans.ttf \
        --size 12 --text "关卡完成！" --color 255,255,255 --outline 0,0,0 \
        --canvas 256x32 --align center --valign middle --out demo.png
"""
import argparse
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def pick_size(target_h, font_path, candidates=(8, 10, 12)):
    """给目标字高挑「设计尺寸 × 整数倍」，避免非整数放大把像素字形弄糊。

    返回 (design_size, scale, 实际字高)。
    """
    if target_h <= 0:
        raise ValueError('目标字高必须为正数')
    design = min(candidates, key=lambda d: (abs(d - target_h), d))
    error = abs(design - target_h)
    if error <= target_h * .4:
        return design, 1, design
    if 12 in candidates and abs(24 - target_h) <= target_h * .4:
        return 12, 2, 24
    raise ValueError('允许的 8/10/12px×1 或 12px×2 无法达到目标；应保留 AI 版本')


def matching_font(font_path, size):
    """自动选型时同步选择同目录、同语言的设计尺寸文件。"""
    path = Path(font_path)
    name = re.sub(r'fusion-pixel-(8|10|12)px-', f'fusion-pixel-{size}px-', path.name)
    result = path.with_name(name)
    if not result.is_file():
        raise ValueError(f'缺少匹配设计尺寸的字体：{result}')
    return str(result)


def render(text, font_path, size, color, outline=(0, 0, 0), outline_w=1,
           canvas=None, align="center", valign="middle", pad=(0, 0), scale=1,
           line_gap=3, line_align="left"):
    """把 text 渲染成像素级 1 位 RGBA。支持 \n 多行（行距 line_gap 像素）。"""
    if size not in (8, 10, 12) or scale not in (1, 2) or (scale == 2 and size != 12):
        raise ValueError('仅允许 8/10/12px×1 或 12px×2；禁止其他字号和倍数')
    match = re.search(r'fusion-pixel-(8|10|12)px-', Path(font_path).name)
    if match and int(match.group(1)) != size:
        raise ValueError('字体文件的设计尺寸与 size 不一致；不可缩放字体轮廓冒充另一设计尺寸')
    if outline_w < 0 or line_gap < 0:
        raise ValueError('描边和行距不能为负数')
    font = ImageFont.truetype(font_path, size)
    lines = text.split("\n")

    # 1) 逐行量字，取最大宽度、累计高度
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    boxes = [probe.textbbox((0, 0), ln, font=font, anchor="lt") if ln else (0, 0, 0, 0)
             for ln in lines]
    widths = [b[2] - b[0] for b in boxes]
    heights = [b[3] - b[1] for b in boxes]
    tw = max(widths) if widths else 0
    th = sum(heights) + line_gap * max(0, len(lines) - 1)
    w = tw + outline_w * 2
    h = th + outline_w * 2

    # 2) 画字形掩膜（逐行），再阈值化成 1 位
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    y = outline_w
    for ln, box, lh in zip(lines, boxes, heights):
        if ln:
            lw = box[2] - box[0]
            if line_align == "center":
                xoff = outline_w + (tw - lw) // 2
            elif line_align == "right":
                xoff = outline_w + (tw - lw)
            else:
                xoff = outline_w
            d.text((xoff - box[0], y - box[1]), ln, font=font, fill=255, anchor="lt")
        y += lh + line_gap
    mask = mask.point(lambda v: 255 if v >= 128 else 0)

    # 3) 描边 = 掩膜向 8 邻域膨胀 outline_w 次
    stroke = Image.new("L", (w, h), 0)
    sp, mp = stroke.load(), mask.load()
    for dy in range(-outline_w, outline_w + 1):
        for dx in range(-outline_w, outline_w + 1):
            if dx == 0 and dy == 0:
                continue
            for yy in range(h):
                for xx in range(w):
                    if mp[xx, yy]:
                        ty, tx = yy + dy, xx + dx
                        if 0 <= ty < h and 0 <= tx < w:
                            sp[tx, ty] = 255

    # 4) 合成 RGBA
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if outline is not None and outline_w > 0:
        out.paste(Image.new("RGBA", (w, h), tuple(outline) + (255,)), (0, 0), stroke)
    out.paste(Image.new("RGBA", (w, h), tuple(color) + (255,)), (0, 0), mask)

    # 5) 整数倍最近邻放大（描边宽度同步放大）
    if scale > 1:
        out = out.resize((w * scale, h * scale), Image.NEAREST)
        w, h = out.size

    # 6) 放进画布并对齐
    if canvas:
        cw, ch = canvas
        if w > cw or h > ch:
            raise ValueError(f'文字块 {w}x{h} 超出画布 {cw}x{ch}；请调整字号或换行')
        lay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        px, py = pad
        x = ((cw - w) // 2 + px) if align == "center" else (
            (cw - w - px) if align == "right" else px)
        y = ((ch - h) // 2 + py) if valign == "middle" else (
            (ch - h - py) if valign == "bottom" else py)
        if x < 0 or y < 0 or x + w > cw or y + h > ch:
            raise ValueError('对齐或 pad 导致文字超出画布；拒绝静默裁切')
        lay.paste(out, (x, y), out)
        return lay
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True)
    ap.add_argument("--size", type=int, default=0, help="设计尺寸；给 --target-height 时可省略")
    ap.add_argument("--text", required=True)
    ap.add_argument("--color", default="255,255,255")
    ap.add_argument("--outline", default="0,0,0")
    ap.add_argument("--outline-w", type=int, default=1)
    ap.add_argument("--scale", type=int, default=1, help="整数倍最近邻放大")
    ap.add_argument("--line-gap", type=int, default=3, help="多行行距(px)；按原图行距实测调整")
    ap.add_argument("--line-align", default="left", choices=["left", "center", "right"],
                    help="多行时块内每行的对齐方式")
    ap.add_argument("--target-height", type=int, default=0,
                    help="给目标字高，自动选 设计尺寸×整数倍 并覆盖 --size/--scale")
    ap.add_argument("--canvas", default=None, help="WxH")
    ap.add_argument("--align", default="center", choices=["left", "center", "right"])
    ap.add_argument("--valign", default="middle", choices=["top", "middle", "bottom"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    size, scale = a.size, a.scale
    if not a.target_height and not a.size:
        ap.error("必须给 --size 或 --target-height")
    if a.target_height:
        size, scale, real = pick_size(a.target_height, a.font)
        a.font = matching_font(a.font, size)
        print("auto: target=%d -> design=%d x%d = %dpx" % (a.target_height, size, scale, real))
    cv = tuple(int(v) for v in a.canvas.lower().split("x")) if a.canvas else None
    col = tuple(int(v) for v in a.color.split(","))
    outl = tuple(int(v) for v in a.outline.split(",")) if a.outline != "none" else None
    img = render(a.text, a.font, size, col, outl, a.outline_w, cv, a.align, a.valign,
                 scale=scale, line_gap=a.line_gap, line_align=a.line_align)
    img.save(a.out)
    print("saved", a.out, img.size)
