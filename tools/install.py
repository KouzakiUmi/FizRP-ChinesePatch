"""Install the generated files over the real game, keeping timestamped backups."""
from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys
import time

GAME_ROOT = os.environ.get("FIZRP_ROOT", r"E:\Steam\steamapps\common\FizRP")
DATA_DIR = os.path.join(GAME_ROOT, "FizAndTheRainbowPlanet_Data")


def collect(payload_dir: str) -> list[tuple[str, str]]:
    """Every file under the payload, mirroring its relative path into the game.

    Must recurse: the patched Unity Localization bundles live under
    `StreamingAssets/aa/StandaloneWindows64/`, so a flat listing would silently
    install only the .assets files and leave the UI strings untranslated.
    """
    pairs = []
    for root, _dirs, names in os.walk(payload_dir):
        for name in sorted(names):
            src = os.path.join(root, name)
            rel = os.path.relpath(src, payload_dir)
            pairs.append((src, os.path.join(DATA_DIR, rel)))
    return sorted(pairs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", default="dist/FizAndTheRainbowPlanet_Data")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup-dir", default=None)
    args = ap.parse_args()

    if not os.path.isdir(DATA_DIR):
        print(f"game data folder not found: {DATA_DIR}", file=sys.stderr)
        return 2
    pairs = collect(args.payload)
    if not pairs:
        print("nothing to install", file=sys.stderr)
        return 2

    backup = args.backup_dir or os.path.join(
        GAME_ROOT, "_backup_" + time.strftime("%Y%m%d-%H%M%S"))
    print(f"game   : {DATA_DIR}")
    print(f"payload: {os.path.abspath(args.payload)}")
    print(f"backup : {backup}")
    for src, dst in pairs:
        state = "same" if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False) \
            else ("new" if not os.path.exists(dst) else "replace")
        print(f"  [{state:7s}] {os.path.basename(dst)}  "
              f"({os.path.getsize(src):,} bytes)")
        if args.dry_run or state == "same":
            continue
        os.makedirs(backup, exist_ok=True)
        if os.path.exists(dst):
            shutil.copy2(dst, os.path.join(backup, os.path.basename(dst)))
        shutil.copy2(src, dst)
    if args.dry_run:
        print("\ndry run: nothing written")
    else:
        print(f"\ndone. rollback by copying {backup} back over {DATA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
