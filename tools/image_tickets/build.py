"""Deterministic, native-size pixel-font optimization of image tickets."""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from render_text import render

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'work'/'image_tickets_opt'
PREV=ROOT/'work'/'image_tickets'
TICKETS={t['id']:t for t in json.loads((PREV/'tickets.json').read_text(encoding='utf-8'))}
RECORDS=[]


def original(id):return Image.open(PREV/'originals'/TICKETS[id]['源文件']).convert('RGBA')


def font(design):return BASE/'fonts'/f'fusion-pixel-{design}px-proportional-zh_hans.ttf'


def begin(id,category):
    return {'id':id,'category':category,'layers':[],'cleanup':[], 'edit_boxes':[],
            'status':'font_optimized' if category!='keep' else 'previous_retained'}


def layer(rec,text,design,color=(255,255,255),outline=(0,0,0),stroke=1,scale=1,**kwargs):
    im=render(text,str(font(design)),design,color,outline,stroke,scale=scale,**kwargs)
    if set(im.getchannel('A').getdata())-{0,255}:raise RuntimeError('Nonbinary glyph alpha')
    index=len(rec['layers']);name=f"{rec['id']}__{index:02d}.png"
    (BASE/'glyph_layers').mkdir(exist_ok=True)
    im.save(BASE/'glyph_layers'/name)
    rec['layers'].append({'file':str(Path('glyph_layers')/name),'font':str(Path('fonts')/font(design).name),
                          'design':design,'scale':scale,'text':text,'color':list(color),
                          'outline':list(outline) if outline else None,'outline_w':stroke,
                          'align':kwargs.get('align','center'),'line_align':kwargs.get('line_align','left'),
                          'line_gap':kwargs.get('line_gap',3),'size':list(im.size)})
    return im


def place(out,im,x,y,rec,alignment='left/top'):
    if min(x,y)<0 or x+im.width>out.width or y+im.height>out.height:
        raise ValueError(f"{rec['id']}: glyph placement overflows")
    out.alpha_composite(im,(x,y))
    rec['layers'][-1]['position']=[x,y]
    rec['layers'][-1]['placement_align']=alignment
    rec['edit_boxes'].append([x,y,x+im.width,y+im.height])


def save(id,out,rec,original_ref=None):
    src=original_ref if original_ref is not None else original(id)
    if out.size!=src.size:raise RuntimeError('Canvas changed')
    allowed=np.zeros((out.height,out.width),bool)
    for x0,y0,x1,y1 in rec['edit_boxes']:allowed[y0:y1,x0:x1]=True
    changed=np.any(np.array(out)!=np.array(src),axis=2)
    if np.any(changed&~allowed):raise RuntimeError(f'{id}: protected pixels changed')
    name=TICKETS[id]['源文件']
    for folder in ['deliverables-opt','check_dark','check_light','preview4x','edit_masks']:
        (BASE/folder).mkdir(exist_ok=True)
    out.save(BASE/'deliverables-opt'/name)
    Image.fromarray((allowed*255).astype('uint8')).save(BASE/'edit_masks'/name)
    for folder,color in [('check_dark',(0,0,0)),('check_light',(255,255,255))]:
        bg=Image.new('RGBA',out.size,color+(255,));bg.alpha_composite(out)
        bg.convert('RGB').save(BASE/folder/name)
    bg=Image.new('RGBA',out.size,(80,80,80,255));bg.alpha_composite(out)
    bg.resize((out.width*4,out.height*4),Image.Resampling.NEAREST).save(BASE/'preview4x'/name)
    rec['size']=list(out.size);rec['changed_pixels']=int(changed.sum());rec['protected_diff']=0
    rec['sha256']=hashlib.sha256((BASE/'deliverables-opt'/name).read_bytes()).hexdigest()
    RECORDS.append(rec)


def restore_from_neighbors(out,mask,known):
    """Only restore selected old glyph pixels, sampling original neighboring rows/columns."""
    src=np.array(out);a=src.copy()
    ys,xs=np.where(mask)
    for y,x in zip(ys,xs):
        same_row=np.flatnonzero(known[y])
        if len(same_row):
            xx=same_row[np.argmin(abs(same_row-x))];a[y,x]=src[y,xx];continue
        same_col=np.flatnonzero(known[:,x])
        if len(same_col):
            yy=same_col[np.argmin(abs(same_col-y))];a[y,x]=src[yy,x];continue
        raise RuntimeError(f'No safe neighbor for old letter at {x},{y}')
    return Image.fromarray(a)


def names():
    id='IMG-08';rec=begin(id,'T1');src=original(id);a=np.array(src)
    out=Image.new('RGBA',src.size,(0,0,0,0));rec['edit_boxes']=[[0,0,192,128]]
    for col,text in enumerate(['菲兹','琉特隆','索拉科','库玛','莉芙','露贝尔']):
        cell=a[:32,col*32:(col+1)*32];pix=cell[(cell[:,:,3]>0)&(np.min(cell[:,:,:3],axis=2)<220)]
        colors,counts=np.unique(pix[:,:3],axis=0,return_counts=True)
        color=tuple(int(v) for v in colors[counts.argmax()])
        for y in [0,16]:
            im=layer(rec,text,8,color,outline=(255,255,255))
            source_box=src.crop((col*32,y,col*32+32,y+16)).getchannel('A').getbbox()
            new_box=im.getchannel('A').getbbox()
            anchor=[col*32+source_box[2],y+source_box[3]]
            x=anchor[0]-new_box[2];top=anchor[1]-new_box[3]
            if x+new_box[0]<col*32 or top+new_box[1]<y:
                raise RuntimeError('Name overflows its original Sprite cell')
            place(out,im,x,top,rec,'exact original glyph bottom-right anchor, including white outline')
            rec['layers'][-1]['source_bbox_local']=list(source_box)
            rec['layers'][-1]['anchor_bottom_right_edge_png']=anchor
            rec['layers'][-1]['anchor_bottom_right_pixel_png']=[anchor[0]-1,anchor[1]-1]
    rec['cleanup']=['T1 transparent canvas rebuilt; twelve individual Sprite cells; each visible glyph bottom-right exactly matches its original counterpart, not cell center']
    save(id,out,rec)


def hud_labels():
    id='IMG-11';rec=begin(id,'T1');rec['status']='generated_resized';out=Image.new('RGBA',original(id).size,(0,0,0,0))
    rec['edit_boxes']=[[0,0,64,56]]
    spec=importlib.util.spec_from_file_location('generated_glyph_source',BASE.parents[1]/'tools/compose_image_tickets.py')
    source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
    rows=source.glyph_rows('IMG-11',3)
    for i,(text,y,mask) in enumerate(zip(['生命','金币 :','剩余 :'],[7,27,39],rows)):
        width=round(mask.width*9/mask.height)
        mask=mask.resize((width,9),Image.Resampling.LANCZOS).point(lambda a:255 if a>=128 else 0)
        mask=Image.fromarray(np.pad(np.array(mask),1))
        outline=mask.filter(ImageFilter.MaxFilter(3))
        im=Image.new('RGBA',mask.size,(255,255,255,0));im.putalpha(outline)
        im.paste((0,0,0,255),(0,0,im.width,im.height),mask)
        name=f'{id}__{i:02d}.png';im.save(BASE/'glyph_layers'/name)
        rec['layers'].append({'file':str(Path('glyph_layers')/name),'font':None,'design':None,'scale':None,
                              'source':'../image_tickets/generated_candidates/IMG-11__candidate-v1.png',
                              'method':'Extract previous imagegen glyph; proportional reduction to 9px ink; no glyph dilation',
                              'text':text,'color':[0,0,0],'outline':[255,255,255],'outline_w':1,
                              'align':'left','line_align':'left','line_gap':None,'size':list(im.size)})
        place(out,im,1,y,rec,'left aligned; original three row positions')
    rec['cleanup']=['Previous generated Chinese glyphs proportionally reduced; black fill, white outline only; no boldening or font rendering; row tops at original Y=7/27/39']
    save(id,out,rec)


def doors():
    id='IMG-05';rec=begin(id,'T2');out=original(id)
    for text,cells in [('选择\n关卡',[(0,0),(32,32)]),('返回\n广场',[(0,32),(64,32)])]:
        for x,y in cells:
            box=[x,y,x+32,y+24];out.paste((0,0,0,0),box);rec['edit_boxes'].append(box)
            im=layer(rec,text,12,line_gap=0,line_align='center')
            if im.height>24:raise RuntimeError('12px door lettering touches original arrow')
            place(out,im,x+(32-im.width)//2,y,rec,'center in original cell; arrow at local y24..26 protected')
    rec['cleanup']=['Clear original transparent text cells only, local y0..23; original arrows y24..26 untouched']
    save(id,out,rec)


def stages(id):
    rec=begin(id,'T2');src=original(id);out=src.copy();clean=original('IMG-07')
    names=['测试区域','糖浆平原','饼干沙漠','抹茶树海','莓果火山','浮岛','糖果之城','马卡龙月亮','名称不明']
    count=9 if id=='IMG-06' else 8
    for i,text in enumerate(names[:count]):
        y=48*(i+1)
        box=[24,y+7,104,y+18]
        rec['edit_boxes'].append(box)
        if id=='IMG-06':
            if i<8:
                # The original English atlas has the exact same ribbon and
                # English pixels, with no Japanese subheading. Use only this
                # tiny header rectangle, never touch the English title row.
                out.paste(clean.crop(box),(box[0],box[1]))
            else:
                # UNKNOWN STAGE exists only in IMG-06. Its header is an opaque,
                # horizontally uniform gradient; sample each original row.
                a=np.array(out)
                for yy in range(box[1],box[3]):
                    a[yy,box[0]:box[2]]=a[yy,5]
                out=Image.fromarray(a)
        im=layer(rec,text,10,outline=None,stroke=0)
        place(out,im,25,y+8,rec,'full Chinese stage name in original upper-left subheading; English unchanged')
    if id=='IMG-07':
        out.paste((255,255,255,0),(0,432,256,480));rec['edit_boxes'].append([0,432,256,480])
    rec['cleanup']=['Start from original texture; keep all large English title pixels and all Sprite geometry unchanged',
                    'IMG-06 replaces Japanese only within local x24..103,y7..17; first eight clean header backgrounds sampled from original IMG-07 counterpart, last header from adjacent original gradient rows',
                    'IMG-07 originally has no Japanese subheadings; add matching Chinese names in that same free header area; no main-title reconstruction']
    if id=='IMG-07':rec['cleanup'].append('Remove development annotation in otherwise unused last 48px row')
    save(id,out,rec)


def rerun():
    id='IMG-14';rec=begin(id,'T2');out=original(id)
    alpha=out.getchannel('A');box=[4,5,60,27];ImageDraw.Draw(alpha).rectangle((4,5,59,26),fill=0)
    out.putalpha(alpha);rec['edit_boxes'].append(box)
    im=layer(rec,'重播',12,outline=None,stroke=0,scale=2)
    x=(64-im.width)//2;y=5+(22-im.height)//2
    place(out,im,x,y,rec,'center in original upper text region')
    # Transparent RGB is significant for this runtime-tinted mask.
    a=np.array(out);a[:,:,:3]=255;out=Image.fromarray(a)
    rec['cleanup']=['Clear upper letter alpha only; exact original border and RERUN EPISODE preserved, including original 85/170 alpha']
    save(id,out,rec)


def warning():
    id='IMG-04';rec=begin(id,'T2');src=original(id);a=np.array(src)
    text_colors=[(255,255,153),(153,255,169),(176,176,112),(78,120,85),(255,255,255)]
    red=(a[:,:,0].astype(int)>a[:,:,1]*1.4)&(a[:,:,0].astype(int)>a[:,:,2]*1.4)&(a[:,:,0]>60)&(a[:,:,3]>0)
    out=src.copy()
    for left in [0,64]:
        mask=np.zeros(a.shape[:2],bool)
        for c in text_colors:mask|=np.all(a[:,:,:3]==c,axis=2)&(a[:,:,3]>0)
        roi=np.zeros(mask.shape,bool);roi[:28,left:left+64]=True;mask &=roi&~red
        known=roi&(((np.isin(a[:,:,0],[47,58]))&(a[:,:,0]==a[:,:,1])&(a[:,:,1]==a[:,:,2]))|red)&(a[:,:,3]>0)
        out=restore_from_neighbors(out,mask,known)
        rec['edit_boxes'].append([left,0,left+64,28])
        for j,text in enumerate(['立体保护区','禁止使用','必杀技']):
            color=(153,255,169) if j==0 else (255,255,153)
            im=layer(rec,text,8,color,outline=None,stroke=0)
            # Search the old title area for a location that leaves the original
            # prohibition circle completely unobscured, never clip a glyph.
            options=[]
            for x in range(left,left+5):
                for y in ([0,1,2,3] if j==0 else [10,11] if j==1 else [20,21]):
                    mask2=np.array(im.getchannel('A'))>0
                    overlap=int(np.count_nonzero(mask2&red[y:y+im.height,x:x+im.width]))
                    options.append((overlap,abs(x-left-2)+abs(y-[1,11,21][j]),x,y))
            overlap,_,x,y=min(options)
            if overlap:raise RuntimeError(f'Font warning label would cover original circle: {overlap}')
            place(out,im,x,y,rec,'fit inside original board without circle overlap')
    if np.any(np.array(out)[red]!=a[red]):raise RuntimeError('Prohibition symbol changed')
    rec['cleanup']=['Remove only known old text palette pixels; restore nearest unlettered grayscale background from same row/column; leave every prohibition-circle pixel intact']
    save(id,out,rec)


def treasure():
    id='IMG-09';rec=begin(id,'T2');src=original(id);a=np.array(src);out=src.copy()
    names=['糖浆平原','饼干沙漠','抹茶树海','莓果火山','浮岛','糖果之城']
    widths=[47,48,53,58,41,47]
    outlines=[]
    for i,text in enumerate(names):
        y=(i+1)*16;box=[13,y+2,18+widths[i],y+10];rec['edit_boxes'].append(box)
        # The leftmost safe part of each old English label supplies its text
        # palette; do not confuse colored landscape pixels with old text.
        pixels=a[y+2:y+10,14:40];colors,counts=np.unique(pixels.reshape(-1,4),axis=0,return_counts=True)
        bg=a[y+1,20]
        textcols=[tuple(c) for c in colors if c[3] and not np.array_equal(c,bg)]
        roi=np.zeros(a.shape[:2],bool);roi[box[1]:box[3],box[0]:box[2]]=True
        mask=np.zeros(roi.shape,bool)
        for c in textcols:mask|=np.all(a==c,axis=2)
        mask &=roi
        known=roi&~mask
        # Extend safe neighbor sampling by one original row above and below.
        known[y+1,13:box[2]]=True;known[y+10,13:box[2]]=True
        out=restore_from_neighbors(out,mask,known)
        target=bg[:3].astype(float)*.57
        dark=[c[:3] for c in colors if c[3] and max(c[:3])<210]
        outline=tuple(int(v) for v in min(dark,key=lambda c:np.linalg.norm(c.astype(float)-target)))
        outlines.append(outline)
    # Old gold text is isolated on the bottom dark strip. Restore each selected
    # foreground pixel from a clean neighbor on the same row, preserving shading.
    box=[20,112,56,119];rec['edit_boxes'].append(box)
    mask=np.zeros(a.shape[:2],bool);known=np.zeros_like(mask)
    for y in range(112,119):
        for x in range(20,56):
            r,g,b,alpha=map(int,a[y,x])
            if alpha and r>b+20 and g>b+20:mask[y,x]=True
    known[113:119,13:65]=np.ptp(a[113:119,13:65,:3].astype(int),axis=2)==0
    # The background is constant vertically here, with a light/dark transition
    # across columns. Use visible same-column samples first, then the nearest
    # known column, rather than letting different letter holes create stripes.
    columns=np.flatnonzero(np.any(known,axis=0))
    arr=np.array(out)
    for y,x in zip(*np.where(mask)):
        xx=int(columns[np.argmin(abs(columns-x))])
        yy_list=np.flatnonzero(known[:,xx]);yy=int(yy_list[np.argmin(abs(yy_list-y))])
        arr[y,x]=a[yy,xx]
    out=Image.fromarray(arr)
    for i,(text,outline) in enumerate(zip(names,outlines)):
        im=layer(rec,text,10,outline=outline)
        place(out,im,14,(i+1)*16+1,rec,'left aligned inside original 128x16 strip')
    im=layer(rec,'宝物',8,(255,255,0),outline=None,stroke=0)
    place(out,im,24,112,rec,'8px exception: preserve y119 lower border and remain within heading slice y112..127')
    rec['cleanup']=['Sample original old-text palette, clear its pixels only within label bounds using neighboring row/column backgrounds; gold heading palette and shadows restored from nearest grayscale neighbors; question-mark strip unchanged',
                    'Gold heading reduced from recommended 10 to 8px: 10px ink is 9px high and cannot fit above original y119 border within its y112..127 Sprite slice']
    save(id,out,rec)


def full_hud():
    id='IMG-10';rec=begin(id,'T2');src=original(id);a=np.array(src);out=a.copy()
    box=[72,7,104,16];rec['edit_boxes'].append(box)
    for y in range(7,16):
        for x in range(72,104):
            # Restore the original gradient above the bar, and its two-pixel
            # blue pattern where the old LIFE word had covered the top edge.
            out[y,x]=a[y,133] if y<12 else ((0,0,0,255) if x==72 else a[y,110+x%2])
    for y0,y1 in [(27,36),(39,48)]:
        rec['edit_boxes'].append([71,y0,128,y1])
        for y in range(y0,y1):
            for x in range(71,128):
                if np.ptp(a[y,x,:3].astype(int))<55:out[y,x]=a[y,133]
    # Correct original caption フィズ, preserving portrait artwork and frame.
    rec['edit_boxes'].append([48,40,64,48])
    for y in range(40,48):
        for x in range(48,64):
            if a[y,x,2]>a[y,x,0] and a[y,x,0]<150:out[y,x]=a[y,47]
    out=Image.fromarray(out)
    for text,y in [('生命',3),('金币 :',27),('剩余 :',39)]:
        im=layer(rec,text,8,(0,0,0),outline=(255,255,255))
        place(out,im,72,y,rec,'left aligned; LIFE above original bar, digits reserved')
    im=layer(rec,'菲兹',8,(53,85,102),outline=None,stroke=0)
    place(out,im,48,40,rec,'original portrait caption cell')
    rec['cleanup']=['Remove old grayscale labels/numbers only; sample cyan gradient per row; restore bar pattern under old LIFE text from same-row intact columns; remove portrait-name blue strokes only; keep inventory pixels exact']
    save(id,out,rec)


def keep(id,reason):
    rec=begin(id,'keep');im=Image.open(PREV/'deliverables'/TICKETS[id]['源文件']).convert('RGBA')
    rec['font']=None;rec['design']=None;rec['scale']=None
    rec['text']=TICKETS[id]['建议中文'];rec['color_outline_alignment']='unchanged previous PNG'
    rec['cleanup']=[reason];rec['edit_boxes']=[[0,0,im.width,im.height]]
    save(id,im,rec)


def alternatives():
    folder=BASE/'alternatives';folder.mkdir(exist_ok=True)
    for id,text in [('IMG-12','关卡完成！'),('IMG-13','获得宝珠！')]:
        im=render(text,str(font(12)),12,(255,255,255),outline=(0,0,0),outline_w=1,scale=2,canvas=(256,32))
        im.save(folder/TICKETS[id]['源文件'])


def write_logs():
    RECORDS.sort(key=lambda r:r['id'])
    (BASE/'render_log.json').write_text(json.dumps(RECORDS,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 优化渲染记录','', '所有字体渲染仅使用随包 fusion-pixel；无系统字体，无非整数缩放。',
           '字形层 alpha 为 0/255；原背景和边框已有的半透明 alpha 不进行全图阈值化。','']
    for r in RECORDS:
        lines += [f"## {r['id']} — {r['status']}",'',f"尺寸：{r['size'][0]}×{r['size'][1]}；保护区差异：{r['protected_diff']} 像素。",'']
        for l in r['layers']:
            text=l['text'].replace('\n',' / ')
            source=f"`{l['font']}`；design={l['design']}；scale={l['scale']}" if l['font'] else f"生成图来源 `{l['source']}`；字体不适用；{l['method']}"
            lines.append(f"- {source}；文字「{text}」；颜色={l['color']}；描边={l['outline']} / {l['outline_w']}px；位置={l['position']}；对齐={l['placement_align']}；行距={l['line_gap']}。")
            if 'anchor_bottom_right_pixel_png' in l:
                lines.append(f"  原字块局部边界={l['source_bbox_local']}；右下角最后像素坐标（含白边）={l['anchor_bottom_right_pixel_png']}。")
        if not r['layers']:
            lines.append(f"- 字体 / design / scale：不适用（沿用上一版 PNG）；文字：{r['text']}；颜色 / 描边 / 对齐 / 位置：与上一版逐字节一致。")
        lines += ['', '清字 / 保留方式：'+'；'.join(r['cleanup']), '']
    (BASE/'render_log.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    RECORDS.clear()
    names();hud_labels();doors();stages('IMG-06');stages('IMG-07');rerun();warning();treasure();full_hud()
    for id in ['IMG-01','IMG-02','IMG-03','IMG-15','IMG-16']:
        keep(id,'T3 artistic title, previous approved AI asset retained byte-for-byte in PNG pixel data')
    for id in ['IMG-12','IMG-13']:
        keep(id,'Optional T1: retain finer previous AI title; 12px×2 comparison is in alternatives/')
    alternatives();write_logs()
    used={l['file'] for r in RECORDS for l in r['layers']}
    for path in (BASE/'glyph_layers').glob('*.png'):
        if str(Path('glyph_layers')/path.name) not in used:path.unlink()
    print(json.dumps({'textures':len(RECORDS),'font_optimized':sum(r['status']=='font_optimized' for r in RECORDS),
                      'generated_resized':sum(r['status']=='generated_resized' for r in RECORDS),
                      'retained':sum(r['status']=='previous_retained' for r in RECORDS)},ensure_ascii=False))


if __name__=='__main__':main()
