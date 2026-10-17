"""Validate font provenance, protected artwork, pixel alpha and exact composites."""
import json
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'work'/'image_tickets_opt'
PREV=ROOT/'work'/'image_tickets'


def main():
    records=json.loads((BASE/'render_log.json').read_text(encoding='utf-8'))
    tickets={t['id']:t for t in json.loads((PREV/'tickets.json').read_text(encoding='utf-8'))}
    report=[];failed=[]
    for r in records:
        id=r['id'];t=tickets[id];name=t['源文件'];checks={}
        path=BASE/'deliverables-opt'/name
        im=Image.open(path);checks['png_rgba_native_size']=im.format=='PNG' and im.mode=='RGBA' and im.size==(t['宽'],t['高'])
        im=im.convert('RGBA');a=np.array(im);src=np.array(Image.open(PREV/'originals'/name).convert('RGBA'))
        mask=np.array(Image.open(BASE/'edit_masks'/name).convert('L'))>0
        checks['protected_rgba_exact']=not np.any(np.any(a!=src,axis=2)&~mask)
        if r['status']=='previous_retained':
            checks['previous_png_byte_exact']=path.read_bytes()==(PREV/'deliverables'/name).read_bytes()
        for n,l in enumerate(r['layers']):
            glyph=Image.open(BASE/l['file']).convert('RGBA')
            checks[f'glyph_{n}_binary_alpha']=set(glyph.getchannel('A').getdata())<={0,255}
            if l['font'] is not None:
                fp=(BASE/l['font']).resolve()
                checks[f'glyph_{n}_bundled_matching_font']=fp.parent==BASE/'fonts' and fp.is_file() and f"-{l['design']}px-" in fp.name
                checks[f'glyph_{n}_allowed_scale']=l['design'] in [8,10,12] and (l['scale']==1 or l['design']==12 and l['scale']==2)
            else:
                checks[f'glyph_{n}_generated_source_exists']=(BASE/l['source']).is_file()
            x,y=l['position'];w,h=l['size']
            checks[f'glyph_{n}_inside_canvas']=0<=x and 0<=y and x+w<=im.width and y+h<=im.height
        if r['category']=='T1':checks['whole_texture_binary_alpha']=set(im.getchannel('A').getdata())<={0,255}
        for folder,color in [('check_dark',(0,0,0)),('check_light',(255,255,255))]:
            expected=Image.new('RGBA',im.size,color+(255,));expected.alpha_composite(im)
            actual=Image.open(BASE/folder/name).convert('RGB')
            checks[f'{folder}_exact']=actual.size==im.size and actual.tobytes()==expected.convert('RGB').tobytes()
        if id=='IMG-04':
            red=(src[:,:,0].astype(int)>src[:,:,1]*1.4)&(src[:,:,0].astype(int)>src[:,:,2]*1.4)&(src[:,:,0]>60)&(src[:,:,3]>0)
            checks['all_original_prohibition_pixels_exact']=np.array_equal(a[red],src[red])
            checks['empty_sign_exact']=np.array_equal(a[32:],src[32:])
        if id=='IMG-05':
            checks['numbered_wood_signs_exact']=np.array_equal(a[:32,32:128],src[:32,32:128])
            checks['question_sign_exact']=np.array_equal(a[32:64,96:128],src[32:64,96:128])
            checks['all_four_arrows_exact']=all(np.array_equal(a[y+24:y+27,x:x+32],src[y+24:y+27,x:x+32]) for x,y in [(0,0),(0,32),(32,32),(64,32)])
        if id=='IMG-08':
            for y in [0,16]:
                for x in range(0,192,32):
                    before=Image.fromarray(src[y:y+16,x:x+32]).getchannel('A').getbbox()
                    after=im.crop((x,y,x+32,y+16)).getchannel('A').getbbox()
                    checks[f'name_{x}_{y}_bottom_right_exact']=after is not None and before[2:]==after[2:]
            for l in r['layers']:
                x,y=l['position'];w,h=l['size'];sx=(l['anchor_bottom_right_edge_png'][0]//32)*32
                sy=0 if l['anchor_bottom_right_edge_png'][1]<=16 else 16
                checks[f'name_{sx}_{sy}_no_cell_overflow']=x>=sx and y>=sy and x+w<=sx+32 and y+h<=sy+16
        if id in ['IMG-06','IMG-07']:
            checks['blank_ribbon_exact']=np.array_equal(a[:48],src[:48])
            count=9 if id=='IMG-06' else 8
            checks['all_original_english_rows_rgba_exact']=all(np.array_equal(a[48*(i+1)+18:48*(i+2)],src[48*(i+1)+18:48*(i+2)]) for i in range(count))
            for i in range(count):
                checks[f'english_title_{i}_exact']=np.array_equal(a[48*(i+1)+18:48*(i+2)],src[48*(i+1)+18:48*(i+2)])
            if id=='IMG-07':checks['development_note_removed']=not np.any(a[432:,:,3])
        if id=='IMG-09':
            checks['question_strip_exact']=np.array_equal(a[:16],src[:16])
            checks['right_side_artwork_exact']=np.array_equal(a[:,80:],src[:,80:])
            checks['all_strip_bottom_borders_exact']=all(np.array_equal(a[y],src[y]) for y in range(31,128,16))
            checks['heading_separator_exact']=np.array_equal(a[112:120,65:],src[112:120,65:])
        if id=='IMG-10':
            checks['alpha_opaque']=np.all(a[:,:,3]==255)
            checks['inventory_and_separator_exact']=np.array_equal(a[:,144:],src[:,144:])
            checks['visible_lower_life_bar_exact']=np.array_equal(a[16:24,72:128],src[16:24,72:128])
            bar=np.zeros(a.shape[:2],bool);bar[12:16,72:128]=True
            bar&=np.ptp(src[:,:,:3].astype(int),axis=2)>55
            checks['visible_colored_upper_life_bar_exact']=np.array_equal(a[bar],src[bar])
            portrait=np.zeros(a.shape[:2],bool);portrait[8:49,15:65]=True;portrait[40:48,48:64]=False
            checks['portrait_except_caption_exact']=np.array_equal(a[portrait],src[portrait])
        if id=='IMG-14':
            checks['all_rgb_white']=bool(np.all(a[:,:,:3]==255))
            keep=np.ones(a.shape[:2],bool);keep[5:27,4:60]=False
            checks['frame_and_english_exact_including_alpha']=np.array_equal(a[keep],src[keep])
        bad=[k for k,v in checks.items() if not v]
        report.append({'id':id,'passed':not bad,'checks':{k:bool(v) for k,v in checks.items()},'failed':bad})
        if bad:failed.append({'id':id,'failed':bad})
    result={'textures':len(records),'passed':sum(r['passed'] for r in report),'all_pass':not failed,'results':report,
            'alpha_scope':'Binary alpha is tested on generated glyph layers and T1 font textures; original nonbinary T2 background/frame alpha is preserved.'}
    (BASE/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'textures':len(records),'passed':result['passed'],'failures':failed},ensure_ascii=False))
    raise SystemExit(1 if failed or len(records)!=16 else 0)


if __name__=='__main__':main()
