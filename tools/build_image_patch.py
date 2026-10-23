"""Stage image replacements against an explicit baseline and verify serialized round-trip.

Does not install files or update Addressables catalogs. Bundle catalog metadata must
be synchronized by the release pipeline before installation.
"""
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from image_patch_policy import (japanese_sprite_names, select_runtime_tickets,
                                sprite_png_box)

import UnityPy
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import unity_env  # Install the project's serializer compatibility fixes.


def digest(data):
    return hashlib.sha256(data).hexdigest()


def key(obj):
    return (Path(obj.assets_file.name).name,obj.path_id)


def prepare_image(ticket, env, texture_object, image, original_images):
    """Restore JP-only Sprite rectangles without changing the approved PNGs."""
    names = japanese_sprite_names(ticket)
    if not names:
        return image, []
    found = {}
    for obj in env.objects:
        if obj.type.name != 'Sprite' or obj.assets_file is not texture_object.assets_file:
            continue
        data = obj.read_typetree()
        if data['m_Name'] not in names:
            continue
        ref = data['m_RD']['texture']
        if ref['m_FileID'] != 0 or ref['m_PathID'] != texture_object.path_id:
            raise RuntimeError(f"{ticket['id']}: protected Sprite references another texture")
        if data['m_Name'] in found:
            raise RuntimeError(f"{ticket['id']}: duplicate protected Sprite")
        found[data['m_Name']] = sprite_png_box(data['m_RD']['textureRect'], *image.size)
    if set(found) != set(names):
        raise RuntimeError(f"{ticket['id']}: missing protected Sprites: {set(names) - set(found)}")
    original_path = original_images / ticket['源文件']
    with Image.open(original_path) as source:
        original = source.convert('RGBA')
    if original.size != image.size:
        raise RuntimeError(f"{ticket['id']}: original PNG size mismatch")
    image = image.copy()
    regions = []
    for name in names:
        box = found[name]
        # No alpha mask: copy original RGBA bytes, including transparent pixels.
        image.paste(original.crop(box), box)
        regions.append({'sprite': name, 'png_box': box,
                        'original_png_sha256': digest(original_path.read_bytes())})
    return image, regions


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base-data-dir',required=True,type=Path,
                    help='Explicit baseline Data directory; use translated build for release integration.')
    ap.add_argument('--out-data-dir',required=True,type=Path)
    ap.add_argument('--images',type=Path,default=ROOT/'work/image_tickets_opt/deliverables-opt')
    ap.add_argument('--original-images',type=Path,default=ROOT/'work/image_tickets/originals',
                    help='Pristine extracted PNGs for restoring JP-only atlas regions.')
    args=ap.parse_args()
    base=args.base_data_dir.resolve();out=args.out_data_dir.resolve()
    if base==out or base in out.parents and out.name==base.name:
        raise SystemExit('Output must be separate from baseline')
    tickets=json.loads((ROOT/'work/image_tickets/tickets.json').read_text(encoding='utf-8'))
    tickets,excluded=select_runtime_tickets(tickets)
    groups=defaultdict(list)
    for t in tickets:
        kind,name=t['运行时来源'].split(': ',1)
        relative=Path('StreamingAssets/aa/StandaloneWindows64')/name if kind=='bundle' else Path(name)
        groups[(kind,relative)].append(t)
    report=[]
    for (kind,relative),items in groups.items():
        source=base/relative;target=out/relative
        if target.exists():
            raise SystemExit(f'Refusing to overwrite staged file: {target}')
        source_hash=digest(source.read_bytes())
        env=UnityPy.load(str(source));root=next(iter(env.files.values()))
        before={key(o):digest(o.get_raw_data()) for o in list(env.objects)}
        modified=set()
        image_records=[]
        expected_images={}
        for t in items:
            matches=[o for o in list(env.objects) if o.type.name=='Texture2D' and o.path_id==t['path_id']
                     and (kind=='bundle' or Path(o.assets_file.name).name==relative.name)]
            if len(matches)!=1:
                raise RuntimeError(f"{t['id']}: ambiguous/missing texture")
            obj=matches[0];tex=obj.read()
            im=Image.open(args.images/t['源文件']).convert('RGBA')
            if im.size!=(tex.m_Width,tex.m_Height):
                raise RuntimeError(f"{t['id']}: size mismatch")
            im,protected=prepare_image(t,env,obj,im,args.original_images)
            expected_images[t['id']]=im
            fmt=tex.m_TextureFormat
            metadata={'width':tex.m_Width,'height':tex.m_Height,'format':fmt,
                      'mip_count':tex.m_MipCount,'filter':tex.m_TextureSettings.m_FilterMode}
            tex.set_image(im,target_format=fmt,mipmap_count=max(1,tex.m_MipCount or 1))
            tex.save();modified.add(key(obj))
            image_records.append({'id':t['id'],'key':key(obj),'image':t['源文件'],
                                  'protected_japanese_regions':protected,'metadata_before':metadata})
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(root.save(packer='original') if kind=='bundle' else root.save())
        check=UnityPy.load(str(target))
        after={key(o):o for o in list(check.objects)}
        unexpected=[k for k,v in before.items() if k not in modified and
                    (k not in after or digest(after[k].get_raw_data())!=v)]
        if unexpected:
            raise RuntimeError(f'Untargeted serialized objects changed: {unexpected[:10]}')
        for rec in image_records:
            tex=after[tuple(rec['key'])].read()
            actual=tex.image.convert('RGBA')
            expected=expected_images[rec['id']]
            rec['roundtrip_pixel_equal']=actual.size==expected.size and actual.tobytes()==expected.tobytes()
            rec['format_preserved']=tex.m_TextureFormat==rec['metadata_before']['format']
            rec['filter_preserved']=tex.m_TextureSettings.m_FilterMode==rec['metadata_before']['filter']
            if not all(rec[k] for k in ['roundtrip_pixel_equal','format_preserved','filter_preserved']):
                raise RuntimeError(f'Roundtrip failed: {rec}')
        if digest(source.read_bytes())!=source_hash:
            raise RuntimeError('Baseline was modified')
        report.append({'file':str(relative),'baseline_sha256':source_hash,
                       'staged_sha256':digest(target.read_bytes()),'untargeted_objects_changed':0,
                       'textures':image_records})
    result={'status':'serialization_roundtrip_pass','baseline':str(base),'output':str(out),
            'installed':False,'catalog_updated':False,'in_game_verified':False,
            'release_note':'Stage against the current translated Data baseline, then synchronize bundle catalog metadata before release.',
            'excluded_japanese_only':excluded,'files':report}
    out.mkdir(parents=True,exist_ok=True)
    (out/'image_patch_roundtrip.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'files':len(report),
                      'textures':sum(len(r['textures']) for r in report),'excluded_japanese_only':excluded,
                      'report':str(out/'image_patch_roundtrip.json')},indent=2))


if __name__=='__main__':
    main()
