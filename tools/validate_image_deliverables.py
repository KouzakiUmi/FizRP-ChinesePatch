"""Validate localized PNGs without editing them; exit nonzero on any failure."""
import argparse
import json
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--directory', type=Path, default=ROOT / 'work/image_tickets/deliverables')
    ap.add_argument('--require-all', action='store_true')
    args = ap.parse_args()
    base = ROOT / 'work/image_tickets'
    tickets = json.loads((base / 'tickets.json').read_text(encoding='utf-8'))
    records = []
    for t in tickets:
        path = args.directory / t['源文件']
        errors = []
        if not path.exists():
            if args.require_all:
                errors.append('missing')
            records.append({'id': t['id'], 'status': 'missing', 'errors': errors})
            continue
        with Image.open(path) as im:
            if im.format != 'PNG' or im.mode != 'RGBA':
                errors.append('must be PNG RGBA')
            if im.size != (t['宽'], t['高']):
                errors.append(f'wrong size {im.size}')
            rgba = im.convert('RGBA')
            alpha = rgba.getchannel('A')
            if t['含透明'] == '否' and alpha.getextrema() != (255, 255):
                errors.append('opaque source must remain fully opaque')
            if t['含透明'] == '是' and alpha.getextrema()[0] == 255:
                errors.append('expected transparency')
            if alpha.getbbox() is None:
                errors.append('empty image')
            if t['id'] == 'IMG-14' and any(p[:3] != (255, 255, 255) for p in rgba.getdata()):
                errors.append('mask RGB must be white, including transparent pixels')
            original = Image.open(base / 'originals' / t['源文件']).convert('RGBA')
            edit_mask = args.directory.parent / 'edit_masks' / path.name
            if not edit_mask.exists():
                errors.append('missing edit mask')
            elif rgba.size == original.size:
                mask = Image.open(edit_mask).convert('L')
                if mask.size != rgba.size:
                    errors.append('wrong edit mask size')
                else:
                    changed = np.any(np.array(rgba) != np.array(original), axis=2)
                    if np.any(changed & (np.array(mask) == 0)):
                        errors.append('protected pixels changed')
            if t['id'] == 'IMG-04' and rgba.size == original.size:
                a=np.array(original)
                red=(a[:,:,0].astype(int)>a[:,:,1]*1.4)&(a[:,:,0].astype(int)>a[:,:,2]*1.4)&(a[:,:,0]>60)
                if np.any(np.array(rgba)[red] != a[red]):
                    errors.append('prohibition symbol pixels changed')
        for folder in ('check_dark', 'check_light'):
            preview = args.directory.parent / folder / path.name
            if not preview.exists():
                errors.append(f'missing {folder} preview')
            else:
                bg=Image.new('RGBA',rgba.size,((0,0,0) if folder=='check_dark' else (255,255,255))+(255,))
                bg.alpha_composite(rgba)
                actual=Image.open(preview).convert('RGB')
                if actual.size!=rgba.size or actual.tobytes()!=bg.convert('RGB').tobytes():
                    errors.append(f'{folder} preview differs from exact composite')
        records.append({'id': t['id'], 'status': 'failed' if errors else 'structural_pass', 'errors': errors})
    print(json.dumps(records, ensure_ascii=False, indent=2))
    print('Structural checks only; text, protected pixels and runtime appearance need separate acceptance.')
    raise SystemExit(1 if any(r['errors'] for r in records) else 0)


if __name__ == '__main__':
    main()
