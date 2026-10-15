"""Report which codepoints a TTF can actually render."""
import os
import struct
import sys


def cmap_codepoints(path):
    b = open(path, "rb").read()
    n = struct.unpack(">H", b[4:6])[0]
    tables = {}
    for i in range(n):
        r = 12 + i * 16
        tables[b[r:r + 4].decode("latin1")] = struct.unpack(">II", b[r + 8:r + 16])
    off, _ = tables["cmap"]
    ntab = struct.unpack(">H", b[off + 2:off + 4])[0]
    best = None
    for i in range(ntab):
        pid, eid, sub = struct.unpack(">HHI", b[off + 4 + i * 8:off + 12 + i * 8])
        fmt = struct.unpack(">H", b[off + sub:off + sub + 2])[0]
        if fmt == 4 and (pid, eid) in ((3, 1), (0, 3), (0, 4), (3, 10)):
            best = off + sub
    if not best:
        return set()
    segx2 = struct.unpack(">H", b[best + 6:best + 8])[0]
    seg = segx2 // 2
    ends = struct.unpack(">%dH" % seg, b[best + 14:best + 14 + segx2])
    starts = struct.unpack(">%dH" % seg, b[best + 16 + segx2:best + 16 + 2 * segx2])
    deltas = struct.unpack(">%dh" % seg, b[best + 16 + 2 * segx2:best + 16 + 3 * segx2])
    ranges = struct.unpack(">%dH" % seg, b[best + 16 + 3 * segx2:best + 16 + 4 * segx2])
    out = set()
    for i in range(seg):
        if starts[i] == 0xFFFF:
            continue
        for cp in range(starts[i], ends[i] + 1):
            if ranges[i] == 0:
                gid = (cp + deltas[i]) & 0xFFFF
            else:
                # idRangeOffset is relative to its own slot in the segment arrays
                idro = best + 16 + 3 * segx2 + 2 * i
                addr = idro + ranges[i] + 2 * (cp - starts[i])
                if addr + 2 > len(b):
                    continue
                gid = struct.unpack(">H", b[addr:addr + 2])[0]
                if gid:
                    gid = (gid + deltas[i]) & 0xFFFF
            if gid:
                out.add(cp)
    return out


SAMPLES = {
    "中文常用": "你我的是不了在有个人这个上下来到时要就说出会可以去到",
    "中文标点": "，。！？；：、（）《》「」…—·",
    "日文假名": "あいうえおアイウエオんをがざだばぱゃゅょっ",
    "日文汉字": "日本語会話設定音楽終了開始続戻",
    "拉丁": "ABCabc0123.,!?'\"-+%@#&*()[]",
}

if __name__ == "__main__":
    for path in sys.argv[1:]:
        if not os.path.exists(path):
            continue
        cps = cmap_codepoints(path)
        name = os.path.basename(path)
        parts = []
        for label, sample in SAMPLES.items():
            hit = sum(1 for ch in sample if ord(ch) in cps)
            parts.append(f"{label} {hit}/{len(sample)}")
        print(f"{name:44s} glyphs={len(cps):6d}  " + " | ".join(parts))
