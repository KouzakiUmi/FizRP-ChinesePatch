"""Round-trip every custom-class MonoBehaviour and assert byte equality."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from custom_types import CLASSES, decode, encode, header_end
from unity_env import DATA_DIR, mb_class, open_env

files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".assets"))
stats, failures = {}, []
for fname in files:
    env = open_env(os.path.join(DATA_DIR, fname))
    sf = env.files[fname]
    for obj in sf.objects.values():
        if obj.type.name != "MonoBehaviour":
            continue
        cls = mb_class(obj, sf)
        if cls not in CLASSES:
            continue
        raw = obj.get_raw_data()
        try:
            data = decode(raw, cls)
            again = encode(data, cls)
        except Exception as exc:  # noqa: BLE001
            failures.append((fname, obj.path_id, cls, f"EXC {type(exc).__name__}: {exc}"))
            continue
        stats[cls] = stats.get(cls, 0) + 1
        payload = raw[header_end(raw):]
        if again != payload:
            failures.append((fname, obj.path_id, cls, f"size {len(again)} != {len(payload)}"))
print("round-trip OK:", stats, "total", sum(stats.values()))
print("failures:", len(failures))
for row in failures[:20]:
    print("   ", row)
