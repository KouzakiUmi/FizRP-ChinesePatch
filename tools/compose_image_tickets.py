"""Compose original-size textures from imagegen candidates; never writes game files."""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'work/image_tickets'
TICKETS = {t['id']: t for t in json.loads((BASE / 'tickets.json').read_text(encoding='utf-8'))}
REPORT = []


def original(id):
    return Image.open(BASE / 'originals' / TICKETS[id]['源文件']).convert('RGBA')


def candidate(id, version='candidate-v1'):
    return Image.open(BASE / 'generated_candidates' / f'{id}__{version}.png').convert('RGBA')


def components(mask, min_area=30):
    labels, n = ndimage.label(mask)
    sizes = np.bincount(labels.ravel())
    keep = sizes >= min_area
    keep[0] = False
    return keep[labels]


def white_mask(im, box=None, yellow=False):
    if box:
        im = im.crop(box)
    a = np.array(im)
    m = (a[:,:,3] > 180)
    if yellow:
        m &= (a[:,:,0] > 175) & (a[:,:,1] > 140) & (a[:,:,2] < 130)
    else:
        m &= np.min(a[:,:,:3], axis=2) > 210
    m = components(m, 20)
    mask = Image.fromarray((m*255).astype('uint8'))
    box = mask.getbbox()
    if not box:
        raise ValueError('no glyph pixels')
    return mask.crop(box)


def fit_mask(mask, size):
    mask = mask.resize(size, Image.Resampling.BOX)
    return mask.point(lambda a: 255 if a >= 112 else 0)


def glyph_rgba(mask, color=(255,255,255), outline=(0,0,0), stroke=1):
    mask = Image.fromarray(np.pad(np.array(mask), stroke))
    edge = mask.filter(ImageFilter.MaxFilter(stroke*2+1)) if stroke else mask
    im = Image.new('RGBA', mask.size, outline+(0,))
    im.putalpha(edge)
    fill = Image.new('RGBA',mask.size,color+(255,))
    im.paste(fill,(0,0),mask)
    return im


def split_glyphs(mask,count):
    a=np.array(mask)
    occupied=np.any(a>0,axis=0)
    labels,n=ndimage.label(~occupied)
    gaps=[]
    for k in range(1,n+1):
        xs=np.flatnonzero(labels==k)
        if xs[0]>0 and xs[-1]<mask.width-1:
            gaps.append((len(xs),int((xs[0]+xs[-1])/2)))
    cuts=sorted(x[1] for x in sorted(gaps,reverse=True)[:count-1])
    if len(cuts)!=count-1:
        cuts=[int(mask.width*i/count) for i in range(1,count)]
    edges=[0]+cuts+[mask.width]
    parts=[]
    for x0,x1 in zip(edges,edges[1:]):
        p=mask.crop((x0,0,x1,mask.height));b=p.getbbox()
        parts.append(p.crop((b[0],0,b[2],p.height)))
    return parts


def pixel_line(mask,count,cell,gap=1):
    parts=split_glyphs(mask,count)
    out=Image.new('L',(cell[0]*count+gap*(count-1),cell[1]))
    for i,p in enumerate(parts):
        out.paste(fit_mask(p,cell),(i*(cell[0]+gap),0))
    return out


def bitmap(rows):
    return Image.fromarray(np.array([[255 if c=='1' else 0 for c in row] for row in rows],dtype='uint8'))


# Native-grid hand corrections for generated tiny characters. These are drawn
# pixel patterns, not system-font rendering. Large generated artwork stays intact.
TINY={
 '立':['0001000','1111111','0010100','0010100','0100010','0100010','1111111'],
 '体':['0100100','0100100','0111111','1100100','0101110','0110101','0100100'],
 '保':['0101110','0101010','0101110','1100100','0111111','0101110','0110101'],
 '护':['0101000','1110111','0100101','0110111','1100100','0100100','0101000'],
 '区':['1111111','1000010','1010100','1001000','1010100','1100010','1111111'],
 '禁':['0100010','1110111','0100010','1010101','0011100','0001000','0101010'],
 '止':['0001000','0001000','0101110','0101000','0101000','0101000','1111111'],
 '使':['0100100','0111111','1100100','0111110','0101010','0100100','0111011'],
 '用':['0111110','0101010','0111110','0101010','0111110','0101010','0100010'],
 '必':['0001000','0001010','0010100','1010101','1001001','0100010','0011100'],
 '杀':['1000001','0100010','0011100','0001000','1111111','0011100','0101010'],
 '技':['0100100','1111111','0100100','0111110','1101010','0100100','0101011'],
 '第':['01010100','10101010','01111100','00000100','01111100','01010000','01111100','10010100'],
 '关':['0100010','0010100','0000000','1111111','0001000','0010100','1100011'],
}
DIGITS={
 '1':['00100','01100','00100','00100','00100','00100','01110'],
 '2':['01110','10001','00001','00010','00100','01000','11111'],
 '3':['11110','00001','00001','01110','00001','00001','11110'],
 '4':['00010','00110','01010','10010','11111','00010','00010'],
 '5':['11111','10000','10000','11110','00001','00001','11110'],
 '6':['01110','10000','10000','11110','10001','10001','01110'],
 '7':['11111','00001','00010','00100','01000','01000','01000'],
}


def tiny_phrase(text):
    masks=[bitmap(TINY[c] if c in TINY else DIGITS[c]) for c in text]
    out=Image.new('L',(sum(m.width for m in masks)+len(masks)-1,8))
    x=0
    for m in masks:
        out.paste(m,(x,0));x+=m.width+1
    return out


def save(id, im, allowed_boxes, note):
    orig = original(id)
    changed = np.any(np.array(im) != np.array(orig),axis=2)
    allowed = np.zeros((im.height,im.width), dtype=bool)
    for x0,y0,x1,y1 in allowed_boxes:
        allowed[y0:y1,x0:x1] = True
    outside = int(np.count_nonzero(changed & ~allowed))
    if outside:
        raise ValueError(f'{id}: {outside} changed protected pixels')
    filename=TICKETS[id]['源文件']
    for folder in ['deliverables','check_dark','check_light','preview4x','edit_masks']:
        (BASE/folder).mkdir(exist_ok=True)
    im.save(BASE/'deliverables'/filename)
    Image.fromarray((allowed*255).astype('uint8')).save(BASE/'edit_masks'/filename)
    for folder,color in [('check_dark',(0,0,0)),('check_light',(255,255,255))]:
        bg=Image.new('RGBA',im.size,color+(255,)); bg.alpha_composite(im)
        bg.convert('RGB').save(BASE/folder/filename)
    bg=Image.new('RGBA',im.size,(80,80,80,255));bg.alpha_composite(im)
    bg.resize((im.width*4,im.height*4),Image.Resampling.NEAREST).save(BASE/'preview4x'/filename)
    REPORT.append({'id':id,'size':list(im.size),'changed_pixels':int(changed.sum()),
                   'changed_protected_pixels':outside,'edit_boxes':allowed_boxes,'note':note})


def banner(id):
    im=original(id)
    mask=fit_mask(white_mask(candidate(id)),(105,20))
    text=glyph_rgba(mask)
    out=Image.new('RGBA',im.size,(0,0,0,0))
    out.alpha_composite(text,((im.width-text.width)//2,(im.height-text.height)//2))
    save(id,out,[(0,0,im.width,im.height)],'Imagegen Chinese glyphs; 1px black outline; integer pixel raster.')


def title():
    im=candidate('IMG-01')
    a=np.array(im)
    mask=(a[:,:,3]>=180) & (np.max(a[:,:,:3],axis=2)>30)
    mask=components(mask,100)
    b=Image.fromarray((mask*255).astype('uint8')).getbbox()
    # Include native black outline around the visible color glyphs.
    b=(max(0,b[0]-12),max(0,b[1]-12),min(im.width,b[2]+12),min(im.height,b[3]+12))
    crop=im.crop(b).resize((144,92),Image.Resampling.BOX)
    a=np.array(crop); alpha=(a[:,:,3]>=145)*255
    # Palette quantization removes incidental generated gradients/noise.
    rgb=Image.fromarray(a[:,:,:3]).quantize(colors=32).convert('RGB')
    crop=rgb.convert('RGBA');crop.putalpha(Image.fromarray(alpha.astype('uint8')))
    out=Image.new('RGBA',(256,224),(0,0,0,0));out.alpha_composite(crop,(56,46))
    save('IMG-01',out,[(0,0,256,224)],'Imagegen two-line Chinese title, 32-color quantization, hard alpha.')
    # Japanese title uses the same Chinese design, with its original English subtitle retained.
    source15=original('IMG-15')
    out15=Image.new('RGBA',source15.size,(0,0,0,0))
    out15.paste(source15.crop((35,124,129,132)),(35,124))
    small=crop.resize((126,76),Image.Resampling.NEAREST)
    out15.alpha_composite(small,(65,45))
    save('IMG-15',out15,[(0,0,256,124),(0,132,256,224),(0,124,35,132),(129,124,256,132)],'Same Chinese title glyphs; complete original English subtitle strip retained.')


def rerun():
    orig=original('IMG-14')
    m=white_mask(candidate('IMG-14'),(325,190,1270,680))
    m=fit_mask(m,(44,23))
    alpha=orig.getchannel('A')
    ImageDraw.Draw(alpha).rectangle((4,5,59,26),fill=0)
    m=fit_mask(m,(42,21));alpha.paste(m,(11,5))
    out=Image.new('RGBA',orig.size,(255,255,255,0));out.putalpha(alpha)
    save('IMG-14',out,[(4,5,60,27)],'Original border and lower English retained; generated Chinese alpha only; all RGB white.')


def color_crop(im,box,size,pink_only=False):
    im=im.crop(box)
    a=np.array(im)
    m=(a[:,:,3]>180)&(np.max(a[:,:,:3],axis=2)>40)
    if pink_only:
        m &= (a[:,:,0].astype(float)>a[:,:,1]*1.12)&(a[:,:,0].astype(float)>a[:,:,2]*1.03)
    m=components(m,40)
    b=Image.fromarray((m*255).astype('uint8')).getbbox()
    b=(max(0,b[0]-8),max(0,b[1]-8),min(im.width,b[2]+8),min(im.height,b[3]+8))
    if pink_only:
        keep=ndimage.binary_dilation(m,iterations=10)
        a[:,:,3]=np.where(keep,a[:,:,3],0)
        im=Image.fromarray(a)
    im=im.crop(b).resize(size,Image.Resampling.BOX)
    a=np.array(im)
    out=Image.fromarray(a[:,:,:3]).quantize(colors=32).convert('RGBA')
    out.putalpha(Image.fromarray(((a[:,:,3]>=140)*255).astype('uint8')))
    return out


def leafur():
    im=candidate('IMG-02');w,h=im.size
    upper=color_crop(im,(int(w*.19),0,int(w*.63),int(h*.54)),(48,25))
    middle=white_mask(im,(int(w*.39),int(h*.46),int(w*.49),int(h*.65)))
    mid=glyph_rgba(fit_mask(middle,(6,7)))
    lower=color_crop(im,(0,int(h*.55),w,h),(116,25),pink_only=True)
    for id in ['IMG-02','IMG-16']:
        out=original(id);out.paste((0,0,0,0),(0,0,128,64))
        out.alpha_composite(upper,(32,0));out.alpha_composite(mid,(60,26));out.alpha_composite(lower,(6,36))
        boxes=[(0,0,128,64)]
        if id=='IMG-02':
            out.paste(original(id).crop((93,0,128,32)),(93,0))
            boxes=[(0,0,93,32),(0,32,128,64)]
        save(id,out,boxes,'Generated Chinese title, original upper-right leaf preserved for IMG-02.')


def fishing():
    im=candidate('IMG-03');w,h=im.size
    out=original('IMG-03')
    boxes=[(38,7,216,80),(55,99,200,179)]
    for box,cb,size in zip(boxes,[(0,0,w,int(h*.20)),(0,int(h*.20),w,int(h*.43))],[(126,71),(126,76)]):
        out.paste((0,0,0,0),box)
        text=color_crop(im,cb,size)
        out.alpha_composite(text,((box[0]+box[2]-text.width)//2,(box[1]+box[3]-text.height)//2))
    save('IMG-03',out,boxes,'Two independent Chinese title slices; all pixels outside slices retained.')


def glyph_rows(id,expected,version='candidate-v1'):
    im=candidate(id,version)
    a=np.array(im)
    m=(a[:,:,3]>200)&(np.min(a[:,:,:3],axis=2)>215)
    m=components(m,50)
    occupied=np.count_nonzero(m,axis=1)>8
    # Join isolated dots inside a row, but keep the generous generated line gaps.
    occupied=ndimage.binary_closing(occupied,structure=np.ones(15))
    labels,n=ndimage.label(occupied)
    rows=[]
    for i in range(1,n+1):
        ys=np.flatnonzero(labels==i)
        if len(ys)<20:
            continue
        part=Image.fromarray((m[ys[0]:ys[-1]+1]*255).astype('uint8'))
        b=part.getbbox()
        if b:
            rows.append(part.crop(b))
    if len(rows)!=expected:
        raise ValueError(f'{id}: expected {expected} text rows, got {len(rows)}')
    return rows


def characters():
    rows=glyph_rows('IMG-08',6)
    orig=original('IMG-08');out=orig.copy()
    a=np.array(orig)
    for col,m in enumerate(rows):
        cell=a[:32,col*32:(col+1)*32]
        pix=cell[(cell[:,:,3]>0)&(np.min(cell[:,:,:3],axis=2)<220)]
        colors,counts=np.unique(pix[:,:3],axis=0,return_counts=True)
        color=tuple(int(x) for x in colors[counts.argmax()])
        count=2 if col in [0,3,4] else 3
        text=glyph_rgba(pixel_line(m,count,(10 if count==2 else 9,11)),color=color,outline=(255,255,255))
        for top in [0,16]:
            out.paste((0,0,0,0),(col*32,top,col*32+32,top+16))
            out.alpha_composite(text,(col*32+(32-text.width)//2,top+1))
    save('IMG-08',out,[(0,0,192,32)],'All twelve 32x16 name slices updated; each original character color sampled, white outline.')


def clear_banner_letters(out,box):
    a=np.array(out)
    x0,y0,x1,y1=box
    # All ribbons share the exact silhouette of the unused top white ribbon.
    # Its per-pixel alpha includes the original translucent edge/shadow.
    template=np.array(original('IMG-06'))[:48,:,3]
    for y in range(y0,y1):
        row=a[y]
        bg=row[5].copy()
        for x in range(x0,x1):
            alpha=int(template[y%48,x])
            a[y,x]=(*bg[:3],alpha) if alpha else (255,255,255,0)
    return Image.fromarray(a)


def stages():
    rows=glyph_rows('IMG-06',9)
    headers=glyph_rows('IMG-06',9,'headers-v1')
    for id in ['IMG-06','IMG-07']:
        out=original(id)
        boxes=[]
        count=9 if id=='IMG-06' else 8
        for i,m in enumerate(rows[:count]):
            y=48*(i+1)
            box=(17,y+5,224,y+48)
            out=clear_banner_letters(out,box);boxes.append(box)
            width=[96,96,96,96,96,48,96,120,96][i]
            text=glyph_rgba(fit_mask(m,(width,22)),outline=(0,0,0))
            out.alpha_composite(text,(20,y+20))
            if id=='IMG-06':
                hm=fit_mask(headers[i],(16,8)) if i in [0,8] else tiny_phrase(f'第{i}关')
                header=glyph_rgba(hm,stroke=0)
                out.alpha_composite(header,(24,y+7))
        if id=='IMG-07':
            out.paste((255,255,255,0),(0,432,256,480));boxes.append((0,432,256,480))
        save(id,out,boxes,'Original ribbon pixels retained outside grayscale text removal; IMG-07 development note cleared.')


def split_phrase(mask):
    # The four generated square Chinese characters have evenly spaced centers.
    a=np.array(mask)
    proj=np.count_nonzero(a,axis=0)
    labels,n=ndimage.label(proj>0)
    spans=[]
    for k in range(1,n+1):
        xs=np.flatnonzero(labels==k)
        if len(xs)>10:
            spans.append((int(xs[0]),int(xs[-1]+1)))
    if len(spans)==4:
        return [mask.crop((x0,0,x1,mask.height)) for x0,x1 in spans]
    return [mask.crop((int(i*mask.width/4),0,int((i+1)*mask.width/4),mask.height)) for i in range(4)]


def doors():
    rows=glyph_rows('IMG-05',2)
    out=original('IMG-05')
    boxes=[]
    for row,positions in zip(rows,[[(0,0),(32,32)],[(0,32),(64,32)]]):
        chars=split_phrase(row)
        for x,y in positions:
            # Keep the original lower arrow pixels below y+25.
            box=(x,y,x+32,y+25);out.paste((0,0,0,0),box);boxes.append(box)
            for i,m in enumerate(chars):
                text=glyph_rgba(fit_mask(m,(11,10)))
                out.alpha_composite(text,(x+3+(i%2)*14,y+(i//2)*12))
    save('IMG-05',out,boxes,'Four language-specific text cells localized; original arrows, numbered wood signs and question mark retained.')


def hud():
    rows=glyph_rows('IMG-11',3)
    out=original('IMG-11');out.paste((0,0,0,0),(0,0,64,56))
    for i,m in enumerate(rows):
        width=22 if i==0 else 27
        text=glyph_rgba(fit_mask(m,(width,10)))
        out.alpha_composite(text,(1,[5,24,41][i]))
    save('IMG-11',out,[(0,0,64,56)],'Three localized HUD labels; right side reserved for runtime digits.')
    out=original('IMG-10')
    boxes=[(71,7,105,16),(71,27,128,37),(71,39,128,49),(48,40,64,48)]
    a=np.array(out)
    for x0,y0,x1,y1 in boxes[:3]:
        for y in range(y0,y1):
            # Only remove grayscale label pixels. The original LIFE label overlaps the
            # upper-left of the bar; blue/orange bar pixels are always protected.
            for x in range(x0,x1):
                if np.ptp(a[y,x,:3].astype(int))<55:
                    a[y,x]=a[y,133]
    # Portrait caption actually reads フィズ, not ソラコ.
    for y in range(40,48):
        for x in range(48,64):
            if a[y,x,2]>a[y,x,0] and a[y,x,0]<150:
                a[y,x]=a[y,47]
    out=Image.fromarray(a)
    for i,m in enumerate(rows):
        text=glyph_rgba(fit_mask(m,(16 if i==0 else 20,7)),outline=(255,255,255))
        # Original mock HUD uses black fill and a white outline.
        text=glyph_rgba(fit_mask(m,(16 if i==0 else 20,7)),color=(0,0,0),outline=(255,255,255))
        out.alpha_composite(text,(72,[7,28,40][i]))
    fiz=glyph_rgba(fit_mask(glyph_rows('IMG-08',6)[0],(13,7)),color=(53,85,102),stroke=0)
    out.alpha_composite(fiz,(49,40))
    save('IMG-10',out,boxes,'Caption corrected to 菲兹 from actual pixels; static 00/01 removed; colored bar and inventory artwork retained.')


def treasure():
    rows=glyph_rows('IMG-06',9)
    out=original('IMG-09');a=np.array(out);boxes=[]
    widths=[47,48,53,58,41,47]
    # Remove white letter cores and their one-pixel outlines only.
    for i,oldw in enumerate(widths):
        y=(i+1)*16
        box=(13,y,max(66,18+oldw),y+14);boxes.append(box)
        region=a[y+1:y+12,13:18+oldw]
        core=np.min(region[:,:,:3],axis=2)>230
        oldmask=ndimage.binary_dilation(core,iterations=2)
        for yy in range(region.shape[0]):
            region[yy,oldmask[yy]]=a[y+1+yy,120]
        a[y+1:y+12,13:18+oldw]=region
    # Last gold label lies on a uniform dark band.
    goldbox=(20,112,74,120);boxes.append(goldbox)
    for y in range(112,120):
        for x in range(20,74):
            a[y,x]=a[y,75]
    out=Image.fromarray(a)
    for i,m in enumerate(rows[1:7]):
        count=2 if i==4 else 4
        text=glyph_rgba(pixel_line(m,count,(11,12)),outline=(80,110,110))
        out.alpha_composite(text,(14,(i+1)*16))
    # Hand-correct the two generated gold glyphs on their native 8px grid.
    gold_rows=['00010000001001111','01111110011101001','01000010001010101','00111100011100101',
               '00010000001010101','00111100001001001','00010100001010010','01111110001000100']
    gold=Image.fromarray(np.array([[255 if c=='1' else 0 for c in row] for row in gold_rows],dtype='uint8'))
    text=glyph_rgba(gold,color=(255,238,0),stroke=0)
    out.alpha_composite(text,(25,112))
    save('IMG-09',out,boxes,'Question-mark strip unchanged; original landscape retained outside old glyph removal; 12px Chinese labels with native-grid gold heading correction.')


def warning():
    rows=glyph_rows('IMG-04',3)
    out=original('IMG-04');orig=np.array(out);a=orig.copy()
    red=(orig[:,:,0].astype(int)>orig[:,:,1]*1.4)&(orig[:,:,0].astype(int)>orig[:,:,2]*1.4)&(orig[:,:,0]>60)
    editable=np.zeros(red.shape,dtype=bool)
    for left in [0,64]:
        area=a[:31,left:left+64]
        chroma=np.ptp(area[:,:,:3].astype(int),axis=2)
        letters=((chroma>70)|(np.min(area[:,:,:3],axis=2)>180))&~red[:31,left:left+64]
        letters=ndimage.binary_dilation(letters,iterations=1)&~red[:31,left:left+64]
        # Select letter colors, excluding neutral board and red prohibition marks.
        idx=ndimage.distance_transform_edt(letters,return_distances=False,return_indices=True)
        repaired=area[tuple(idx)];area[letters]=repaired[letters]
        a[:31,left:left+64]=area
    out=Image.fromarray(a)
    for left in [0,64]:
        for j,m in enumerate(rows):
            color=(153,255,170) if j==0 else (255,238,119)
            phrase=['立体保护区','禁止使用','必杀技'][j]
            text=glyph_rgba(tiny_phrase(phrase),color=color,stroke=0)
            x=left+2;y=[2,12,22][j]
            out.alpha_composite(text,(x,y))
    a=np.array(out);a[red]=orig[red];out=Image.fromarray(a)
    save('IMG-04',out,[(0,0,128,31)],'Two signs localized using three compact rows; original red prohibition pixels and empty lower sign retained exactly.')


def main():
    banner('IMG-12');banner('IMG-13');title();rerun();leafur();fishing()
    characters();stages();doors();hud();treasure();warning()
    (BASE/'audit/composition_report.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(REPORT,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
