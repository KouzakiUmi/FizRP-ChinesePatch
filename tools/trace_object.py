import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unity_env import DATA_DIR, mb_class, open_env
from custom_types import CLASSES, Reader, header_end, STR, I32, F32, BOOL, PPTR

def trace(reader, spec, depth, log, limit=None):
    pad = "  " * depth
    if isinstance(spec, list):
        n = reader.i32(); log.append(f"{pad}LIST size={n} @{reader.pos}")
        for i in range(n):
            log.append(f"{pad}[{i}]")
            trace(reader, spec[0], depth + 1, log)
        return
    if isinstance(spec, tuple):
        for name, sub in spec[1]:
            p0 = reader.pos
            trace(reader, sub, depth + 1, log) if isinstance(sub, (list, tuple)) else None
            if not isinstance(sub, (list, tuple)):
                val = {STR: reader.string, I32: reader.i32, F32: reader.f32, BOOL: reader.u8, PPTR: reader.pptr}[sub]()
                log.append(f"{pad}{name}: {str(val)[:50]!r} @{p0}->{reader.pos}")
        return

def dump(fname, pid):
    env = open_env(os.path.join(DATA_DIR, fname))
    sf = env.files[fname]
    obj = sf.objects[pid]
    cls = mb_class(obj, sf)
    raw = obj.get_raw_data()
    reader = Reader(raw, header_end(raw))
    log = []
    try:
        trace(reader, CLASSES[cls], 0, log)
    except Exception as exc:
        log.append(f"!! {type(exc).__name__}: {exc}")
    print(f"=== {fname} pid={pid} {cls} rawlen={len(raw)} hdr={header_end(raw)} end={reader.pos}")
    for line in log[:14] + ["..."] + log[-14:]:
        print(line)

if __name__ == "__main__":
    dump(sys.argv[1], int(sys.argv[2]))
