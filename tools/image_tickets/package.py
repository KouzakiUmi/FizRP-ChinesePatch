"""Package optimized textures, bundled font licenses and review evidence."""
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'work'/'image_tickets_opt'
PREV=ROOT/'work'/'image_tickets'

NOTES='''# 图像文字优化版 v2.4

按最新反馈：8 张使用随包 fusion-pixel 字体，IMG-11 改用先前生成的字形缩放，7 张沿用上一版。

## 交付

- deliverables-opt：16 张原生尺寸 RGBA PNG，命名与原工单一致。
- check_dark / check_light：黑、白底精确合成；preview4x：最近邻 4 倍检查图，仅供放大查看。
- glyph_layers：独立字体字形层，alpha 均严格为 0/255。
- edit_masks：允许的文字编辑范围，范围外 RGBA 与原图完全一致。
- render_log.md / render_log.json：逐图、逐层字体文件、设计尺寸、倍数、文字、颜色、描边、位置、对齐、清字方式。
- fonts：完整随包字体和未改动的 OFL.txt；授权文件必须随字体继续分发。
- alternatives：IMG-12/13 的 12px×2 备选，供对照，不属于本次默认回灌输入。

## 采用方案

IMG-04：8px×1，绿/黄单色。清除原文字像素后，从同一行/列的邻近底板或禁止圈底色恢复；
三行“立体保护区 / 禁止使用 / 必杀技”避开禁止圈，未裁切字形。原有红色禁止圈像素和下方空牌逐点保留。

IMG-05：12px×1，中文按两行置于四个原文字切片；木牌数字、问号、四个箭头逐点保留。

IMG-06/07：按最新反馈保留原英文大字，中文全名放在左上角小标题位置，使用 10px×1 白字，无描边。
IMG-06 只替换日文小标题；前八条使用原 IMG-07 相同小区域作为无字渐变底，最后一条从同一原图的相邻列逐行取样。
IMG-07 原图没有日文小标题，因此在对应空位补上相同中文名，仅八条，不新增 UNKNOWN STAGE。
所有英文大字行 RGBA 与各自原图完全一致，横幅、顶部空白条、切片位置不变；IMG-07 底部开发标注仍清除。
中文依次为：测试区域、糖浆平原、饼干沙漠、抹茶树海、莓果火山、浮岛、糖果之城、马卡龙月亮；IMG-06 另有名称不明。

IMG-08：8px×1，十二个独立 32x16 切片、原角色颜色、白描边。
每个新名字（含描边）的可见像素右下角，逐个匹配原图对应名字的可见像素右下角；不是整行居中，也不是对齐切片统一边缘。
12 个锚点均自动检查完全一致，未改变 Sprite rect/pivot，未越出各自切片。逐项坐标见 sprite_anchor_report.json。

IMG-09：关名 10px×1，问号条、右侧原画与各条底边保持不变。
唯一字号例外是底部“宝物”采用 8px×1：10px 字体实际墨高 9px，无法在原下边框 y119 上方容纳，
且不能移到前一个 Sprite。按工单“放不下就减小字号”的规则减到 8px。
清字仅针对旧字的颜色及其阴影，在原文字包围盒内用相邻可见行/列恢复底色；没有整块填纯色。

IMG-10：8px×1。原头像、物品槽、角标和可见血条像素保持不变；固定 00/01 清除，数字仍由游戏代码绘制。
原图头像旁写的是“フィズ”，因此保留上次复核结论，使用“菲兹”。
LIFE 原字覆盖血条顶边，清理该旧字时从血条同一行的完整列取样恢复 2px 周期图案；新“生命”放在血条上方。

IMG-11：按最新反馈，不使用像素字体。提取先前 imagegen 生成的字形，保持比例缩小到 9px 墨高，黑字 + 1px 白描边，不对字形膨胀加粗。三行顶部 Y=7/27/39，“剩余”顶部 Y=39。

IMG-14：按字号反馈改为 12px×2，实际墨高 22px，文字块 48×22px，在原文字区域内居中；RGB 全部纯白。原始边框及英文小字逐像素保留，包括其 85/170 半透明 alpha。
“字形 alpha 为 1 位”只针对新字形，不能对整张 T2 贴图阈值化，否则会破坏要求保留的原边框/背景。

IMG-01/02/03/15/16：按 T3 指令沿用上一版艺术字 PNG，文件逐字节一致。
IMG-12/13：按工单许可保留较自然的上一版 AI 字形；另提供 12px×2 备选。默认交付 PNG 与上一版逐字节一致。

## 渲染器修正

自动选型不再遍历 1–8 倍：先在 8/10/12px×1 中选最接近者；误差超过目标 40% 才考虑 12px×2；
不满足则明确报错。自动选型同时切换到同目录、同语言的对应设计尺寸字体文件。
显式禁止 scale≥3、8/10px×2、非设计字号、字体文件与字号不匹配，画布和 pad 溢出也直接报错，拒绝静默裁字。
描边依然用掩膜膨胀；整数倍缩放只用最近邻；新字体字形 alpha 阈值为 128。

## 验证与边界

- 5 项渲染器测试通过：选型、非法倍数、字体匹配、二值 alpha、描边、溢出等。
- 16 张尺寸、RGBA、黑白底合成、保护区差异及专门的装饰检查全部通过，详见 validation.json。
- 同一环境重复构建，16 张 PNG 逐字节一致，详见 reproducibility.json。
- 在隔离目录写入 4 个对应原始资源文件并重新导出，16 张 PNG 像素全部一致；未目标修改的序列化对象原始字节不变。
- 游戏安装目录未修改，尚未做游戏内截图验收；Addressables catalog 未更新。

本包是 PNG 回灌输入，不是完整安装补丁。正式集成需以当前汉化构建为基线重新写入，
并同步 bundle catalog 元数据，避免覆盖已有文本与字体补丁。
脚本应在 D:/FizRP-ChinesePatch 原项目目录运行；交付副本不含游戏原始资源和上一版全部中间稿。
'''


def preview(im,scale):
    bg=Image.new('RGBA',im.size,(80,80,80,255));bg.alpha_composite(im)
    return bg.convert('RGB').resize((im.width*scale,im.height*scale),Image.Resampling.NEAREST)


def comparison(output,items,filename):
    f=ImageFont.truetype(str(BASE/'fonts/fusion-pixel-12px-proportional-zh_hans.ttf'),12)
    height=55+sum((crop[3]-crop[1])*scale+42 for _,crop,scale in items)
    out=Image.new('RGB',(1800,height),(42,45,52));d=ImageDraw.Draw(out)
    for x,label in [(15,'ORIGINAL'),(615,'PREVIOUS AI'),(1215,'CURRENT RESULT')]:d.text((x,10),label,font=f,fill='white')
    d.text((15,30),'All views use identical crop and nearest-neighbor inspection zoom; delivered canvases stay native.',font=f,fill=(185,190,200))
    y=55
    for id,crop,scale in items:
        t=TICKETS[id];name=t['源文件'];d.text((15,y),f'{id}  inspection zoom x{scale}',font=f,fill='white')
        for col,folder in enumerate([PREV/'originals',PREV/'deliverables',BASE/'deliverables-opt']):
            im=Image.open(folder/name).convert('RGBA').crop(crop)
            p=preview(im,scale);out.paste(p,(col*600+15,y+22))
        y+=(crop[3]-crop[1])*scale+42
    out.save(output/filename)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path);args=ap.parse_args()
    output=args.output.resolve()
    if output.exists():raise SystemExit(f'Refusing to overwrite existing output: {output}')
    records=json.loads((BASE/'render_log.json').read_text(encoding='utf-8'))
    if len(records)!=16 or not json.loads((BASE/'validation.json').read_text(encoding='utf-8'))['all_pass']:
        raise SystemExit('Validation missing or failed')
    (BASE/'NOTES.md').write_text(NOTES,encoding='utf-8')
    output.mkdir(parents=True)
    for folder in ['deliverables-opt','check_dark','check_light','preview4x','edit_masks','glyph_layers','alternatives','fonts']:
        shutil.copytree(BASE/folder,output/folder)
    for name in ['TICKETS-OPT.md','NOTES.md','render_log.md','render_log.json','validation.json','reproducibility.json']:
        shutil.copy2(BASE/name,output/name)
    tools_dir=Path(__file__).resolve().parent
    for name in ['render_text.py','build.py','validate.py','test_render_text.py','package.py']:
        shutil.copy2(tools_dir/name,output/name)
    shutil.copy2(BASE/'roundtrip-v5/FizAndTheRainbowPlanet_Data/image_patch_roundtrip.json',output/'image_patch_roundtrip.json')
    shutil.copy2(BASE/'stage_preservation_report.json',output/'stage_preservation_report.json')
    shutil.copy2(BASE/'sprite_anchor_report.json',output/'sprite_anchor_report.json')
    shutil.copy2(BASE/'revision.json',output/'revision.json')
    shutil.copy2(BASE/'demo/rerun_size_fix.png',output/'RERUN_SIZE_COMPARISON.png')
    shutil.copy2(PREV/'audit/texture_slices.json',output/'texture_slices.json')
    shutil.copy2(PREV/'tickets.json',output/'tickets.json')
    shutil.copy2(BASE.parents[1]/'requirements-images.txt',output/'requirements-images.txt')
    for name in ['OFL.txt']:
        assert (output/'fonts'/name).read_bytes()==(BASE/'fonts'/name).read_bytes()
    manifest={'version':'opt-v2.4','font_optimized':8,'generated_resized':1,'previous_retained':7,'textures':[], 'font_files':[]}
    for r in records:
        t=TICKETS[r['id']];name=t['源文件'];p=output/'deliverables-opt'/name
        manifest['textures'].append({'id':r['id'],'file':str(Path('deliverables-opt')/name),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                                    'status':r['status'],'size':r['size'],'source':t['运行时来源'],'path_id':t['path_id']})
    for p in sorted((output/'fonts').iterdir()):
        if p.is_file():manifest['font_files'].append({'file':str(Path('fonts')/p.name),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    comparison(output,[('IMG-08',(0,0,192,32),3),('IMG-11',(0,0,64,56),4),('IMG-14',(0,0,64,40),4)],'COMPARISON_SMALL_TEXT.png')
    comparison(output,[('IMG-04',(0,0,128,64),4),('IMG-05',(0,0,128,64),4),('IMG-06',(0,48,224,192),2),
                       ('IMG-09',(0,0,128,128),4),('IMG-10',(0,0,256,56),2)],'COMPARISON_T2.png')
    archive=output.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in output.rglob('*'):
            if p.is_file():z.write(p,Path(output.name)/p.relative_to(output))
    print(json.dumps({'output':str(output),'archive':str(archive),'bytes':archive.stat().st_size},ensure_ascii=False))


TICKETS={t['id']:t for t in json.loads((PREV/'tickets.json').read_text(encoding='utf-8'))}
if __name__=='__main__':main()
