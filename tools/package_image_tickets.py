"""Package PNG deliverables and inspectable QA, excluding experimental asset bundles."""
import argparse
import csv
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/image_tickets'

NOTES='''# 图像本地化交付 v1 — 2026-10-17

16 张 PNG 均为原生尺寸 RGBA；IMG-10 alpha 全不透明，IMG-14 全部 RGB 为纯白。
deliverables 是回灌输入；check_dark / check_light 是逐像素黑白底合成；preview4x 是最近邻放大检查图。
edit_masks 是允许修改范围；蒙版外 RGBA 与原图完全一致。允许区域内包含清除旧字后需要恢复的底色。

## 已完成验证

- 16 张指定原图与游戏 Texture2D 像素一致；实际 Sprite 切片见 texture_slices.json。
- 16 张尺寸、RGBA、透明规则、保护区域、黑白底合成均通过。
- IMG-04 两个红色禁止符号的原始 RGBA 像素逐点保留；下方空牌完全保留。
- IMG-02 原始右上叶子图标保留；IMG-05 数字木牌、问号与箭头保留；IMG-09 问号条保留。
- 使用原游戏资源作为明确基线，在隔离目录写入对应 4 个资源文件后重新读取；16 张与 PNG 像素完全一致。
- 回灌时保持 Texture2D 原格式和过滤方式；未指定修改的序列化对象原始字节未变。
- 负例验证：错误尺寸、非白色遮罩被检查器拒绝。

## 工单修正与版式取舍

1. IMG-03 必须保留两个独立切片，各为“索拉科的 / 钓鱼”，不能将全图压成一个标题。
2. IMG-04 两块文字牌都本地化；为在禁止圈左侧容纳完整意思，排为“立体保护区 / 禁止使用 / 必杀技”三行。
   这是对原工单保持行数规则的一处明确取舍。7px 小字经过手工像素修整，原生阅读空间仍然很小。
3. IMG-05 的中英文文字分别位于独立 32x32 切片，均替换为中文，未移动切片或箭头。
4. IMG-06 保留小字+大字两级；小字采用“测试 / 第1关…第7关 / 未知”，大字使用既有译名。
   IMG-07 仅大字，并清除了底部“空き領域 1”。原始空白横幅未改。
5. IMG-08 每个名字位于 32x16 区域，三字姓名采用每字 9x11 像素并保留白描边与原色。
   这是最紧的显示区域之一；没有移动或扩大 Sprite。
6. IMG-09 在原 128x16 横幅内使用 12px 中文；旧字覆盖处恢复底色，允许区外的原背景画面逐点保留。
7. IMG-10 原图文字实际为“フィズ”，不是“ソラコ”；头像旁改为“菲兹”。
   CanvasCamera.cs 的 SetCoin/SetRest 使用独立 Text 输出数字，因此按工单清除了底图固定 00/01。
   尚未据此声称已审计该贴图在所有场景中的引用。
8. IMG-14 只替换上方中文 alpha，原始边框与下方 RERUN EPISODE 原位保留；没有绘制深色底。
9. IMG-15/16 为 P2，已提供；IMG-15 的原始英文副标题完整保留。

## 回灌边界

这是 PNG 回灌输入与验证包，不是可直接安装的完整汉化补丁。
游戏安装目录没有被修改。未完成游戏内截图验收，未更新 Addressables catalog。
隔离测试基于原游戏资源，不能将其 sharedassets3.assets / sharedassets13.assets 直接覆盖现有汉化构建，
否则会丢失现有构建的其他文本、字体等修改。正式集成应以当前汉化 Data 目录为基线重新写入。

tools/build_image_patch.py 要求显式 --base-data-dir 与 --out-data-dir，并拒绝覆盖已有阶段文件。
修改 Addressables bundle 后，需要由发布流程同步 catalog 的大小与 CRC 等元数据并在游戏内验收。
本包不包含隔离测试中的资源文件，避免误作安装文件。

## 生成方式

使用内置 imagegen，原图输入，transparent_background=true；没有使用 API/CLI 生图。
生成器输出经用户授权，使用 Python/Pillow 提取字形、整理原尺寸、量化颜色、修整像素与合成原图。
小号禁止牌、关卡序号与宝物标题包含手工像素修字；没有使用系统字体直接贴字。
大标题等共享字形在对应英文/日文资产中复用，各自保留原切片关系。
tools 内为项目脚本副本，应在原项目目录运行；本交付包不含游戏原始资源与所有生成中间稿，不能作为独立源码环境运行。
'''


def update_tickets():
    replacements={
      '英日四行可压成中文两行，但须保持整体高度与居中':'实际有两个独立 Sprite 切片；每个切片分别为中文两行，禁止跨切片合并',
      '左牌：「立体保护区」/「禁止使用必杀技」；右牌可省或作「禁止使用必杀技」':'两块文字牌均为「立体保护区」/「禁止使用」/「必杀技」；保留各自禁止圈与下方空牌',
      '右下小字 ソラコ':'右下小字 フィズ（实际像素复核）',
      'ソラコ→索拉科；LIFE→生命':'フィズ→菲兹；LIFE→生命',
      '双线边框与深色底必须保留':'保留原始白色 alpha 边框，不绘制任何深色底',
    }
    for filename in ['TICKETS.md','_tickets_data.py']:
        path=BASE/filename;s=path.read_text(encoding='utf-8')
        for before,after in replacements.items():s=s.replace(before,after)
        if filename=='TICKETS.md':
            lines=s.splitlines();last_source=''
            for i,line in enumerate(lines):
                if '**运行时来源**' in line:last_source=line
                if 'bundle 里的副本才生效' in line and '`assets:' in last_source:
                    lines[i]='  - 指定目标为此 `.assets` 文件中的 Texture2D；按文件与 path_id 定位，不适用 bundle 副本提示。'
            s='\n'.join(lines)+'\n'
        path.write_text(s,encoding='utf-8')
    path=BASE/'tickets.json';items=json.loads(path.read_text(encoding='utf-8'))
    for t in items:
        for k,v in t.items():
            if isinstance(v,str):
                for before,after in replacements.items():v=v.replace(before,after)
                t[k]=v
    path.write_text(json.dumps(items,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    with (BASE/'tickets.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
    return items


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path);args=ap.parse_args()
    output=args.output.resolve()
    if output.exists():raise SystemExit(f'Refusing to overwrite package: {output}')
    items=update_tickets()
    (BASE/'NOTES.md').write_text(NOTES,encoding='utf-8')
    notes_path=BASE/'audit/IMPLEMENTATION_NOTES.md'
    s=notes_path.read_text(encoding='utf-8')
    s+='\n\n## 交付状态\n\n16 张原生 RGBA 已生成；结构验证与 4 个资源文件的 16 张回灌往返验证通过。详见 ../NOTES.md。未改游戏安装目录，未接入正式发布。\n'
    notes_path.write_text(s,encoding='utf-8')
    output.mkdir(parents=True)
    for folder in ['deliverables','check_dark','check_light','preview4x','edit_masks']:
        shutil.copytree(BASE/folder,output/folder)
    for name in ['NOTES.md','tickets.json','tickets.csv','TICKETS.md']:
        shutil.copy2(BASE/name,output/name)
    shutil.copy2(BASE/'GENERATION_PROMPTS.json',output/'GENERATION_PROMPTS.json')
    (output/'audit').mkdir()
    for name in ['texture_slices.json','composition_report.json','validation.json.txt','negative_control.json','IMPLEMENTATION_NOTES.md']:
        shutil.copy2(BASE/'audit'/name,output/'audit'/name)
    shutil.copy2(BASE/'roundtrip-v3/FizAndTheRainbowPlanet_Data/image_patch_roundtrip.json',output/'audit/image_patch_roundtrip.json')
    (output/'tools').mkdir()
    for name in ['audit_image_tickets.py','compose_image_tickets.py','validate_image_deliverables.py','build_image_patch.py','package_image_tickets.py']:
        shutil.copy2(ROOT/'tools'/name,output/'tools'/name)
    shutil.copy2(ROOT/'requirements-images.txt',output/'tools/requirements-images.txt')
    # Overview crops transparent margins for inspection only. Deliverable sizes stay unchanged.
    canvas=Image.new('RGB',(1600,1400),(48,51,57));d=ImageDraw.Draw(canvas)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17)
    small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',13)
    d.text((18,10),'FizRP 中文图像 · 16 张原生 RGBA · v1',font=font,fill='white')
    d.text((18,38),'预览裁去了透明留白；交付 PNG 保持原尺寸。结构与资源写入验证通过，游戏内显示待验。',font=small,fill=(200,205,215))
    for n,t in enumerate(items):
        im=Image.open(output/'deliverables'/t['源文件']).convert('RGBA');b=im.getchannel('A').getbbox()
        preview=im.crop(b)
        factor=min(4,370/preview.width,260/preview.height)
        preview=preview.resize((max(1,round(preview.width*factor)),max(1,round(preview.height*factor))),Image.Resampling.NEAREST)
        x=(n%4)*400;y=70+(n//4)*330
        d.rectangle((x+8,y+3,x+392,y+324),fill=(70,73,79),outline=(110,113,120))
        d.text((x+18,y+10),f"{t['id']}  {t['宽']}×{t['高']}",font=font,fill='white')
        canvas.paste(preview,(x+16+(368-preview.width)//2,y+48+(260-preview.height)//2),preview)
    canvas.save(output/'OVERVIEW.png')
    manifest=[]
    for t in items:
        p=output/'deliverables'/t['源文件']
        manifest.append({'id':t['id'],'file':str(Path('deliverables')/p.name),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                         'size':[t['宽'],t['高']],'mode':'RGBA','source':t['运行时来源'],'path_id':t['path_id']})
    (output/'manifest.json').write_text(json.dumps({'version':1,'date':'2026-10-17','textures':manifest},ensure_ascii=False,indent=2),encoding='utf-8')
    archive=output.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in output.rglob('*'):
            if p.is_file():z.write(p,Path(output.name)/p.relative_to(output))
    print(json.dumps({'output':str(output),'archive':str(archive),'pngs':len(manifest)},ensure_ascii=False))


if __name__=='__main__':main()
