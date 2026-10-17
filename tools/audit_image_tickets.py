"""Read-only texture identity and Sprite slicing audit for image tickets."""
import hashlib
import json
import sys
from pathlib import Path

import UnityPy
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from unity_env import DATA_DIR, BUNDLE_DIR


def main():
    base = ROOT / 'work/image_tickets'
    tickets = json.loads((base / 'tickets.json').read_text(encoding='utf-8'))
    cache = {}
    results = []
    for t in tickets:
        kind, name = t['运行时来源'].split(': ', 1)
        source = Path(BUNDLE_DIR if kind == 'bundle' else DATA_DIR) / name
        if str(source) not in cache:
            cache[str(source)] = UnityPy.load(str(source))
        env = cache[str(source)]
        matches = [o for o in env.objects if o.type.name == 'Texture2D' and o.path_id == t['path_id']
                   and (kind == 'bundle' or Path(o.assets_file.name).name == name)]
        if len(matches) != 1:
            raise RuntimeError(f"{t['id']}: expected one Texture2D, got {len(matches)}")
        obj = matches[0]
        tex = obj.read()
        original = Image.open(base / 'originals' / t['源文件']).convert('RGBA')
        actual = tex.image.convert('RGBA')
        sprites = []
        for s in env.objects:
            if s.type.name != 'Sprite' or s.assets_file is not obj.assets_file:
                continue
            tree = s.read_typetree()
            rd = tree.get('m_RD', {})
            ptr = rd.get('texture', {})
            if ptr.get('m_FileID') != 0 or ptr.get('m_PathID') != obj.path_id:
                continue
            rect = rd['textureRect']
            x, y, w, h = [int(rect[k]) for k in ('x', 'y', 'width', 'height')]
            sprites.append({'path_id': s.path_id, 'name': tree['m_Name'],
                            'rect_unity_bottom_left': rect,
                            'box_png_top_left': [x, actual.height-y-h, x+w, actual.height-y],
                            'pivot': tree.get('m_Pivot'), 'border': tree.get('m_Border')})
        results.append({'id': t['id'], 'source': str(source), 'serialized_file': obj.assets_file.name,
                        'path_id': obj.path_id, 'texture_name': tex.m_Name,
                        'size': list(actual.size), 'format': tex.m_TextureFormat,
                        'original_matches_runtime_pixels': actual.size == original.size and actual.tobytes() == original.tobytes(),
                        'original_sha256': hashlib.sha256((base / 'originals' / t['源文件']).read_bytes()).hexdigest(),
                        'sprites': sprites,
                        'scope': 'Local Sprite references in owning serialized file; scene/code and external references require separate review.'})
    out = base / 'audit/texture_slices.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    for r in results:
        print(r['id'], 'source_match=' + str(r['original_matches_runtime_pixels']), 'sprites=' + str(len(r['sprites'])))


if __name__ == '__main__':
    main()
