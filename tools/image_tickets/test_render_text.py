"""Meaningful guards for font sizing, alpha, padding and clipping."""
import unittest
from pathlib import Path
from render_text import pick_size,matching_font,render

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'work'/'image_tickets_opt'


class RenderTests(unittest.TestCase):
    def test_policy_prefers_unscaled_before_doubling(self):
        path=str(BASE/'fonts/fusion-pixel-8px-proportional-zh_hans.ttf')
        self.assertEqual(pick_size(8,path),(8,1,8))
        self.assertEqual(pick_size(18,path),(12,1,12))
        self.assertEqual(pick_size(22,path),(12,2,24))
        self.assertEqual(pick_size(24,path),(12,2,24))
        with self.assertRaises(ValueError):pick_size(50,path)

    def test_forbidden_scales_and_font_mismatch(self):
        p=str(BASE/'fonts/fusion-pixel-8px-proportional-zh_hans.ttf')
        for size,scale in [(8,3),(8,2),(10,2),(16,1),(12,1)]:
            with self.subTest(size=size,scale=scale):
                with self.assertRaises(ValueError):render('生命',p,size,(255,255,255),scale=scale)

    def test_alpha_binary_and_automatic_matching_font(self):
        p=str(BASE/'fonts/fusion-pixel-8px-proportional-zh_hans.ttf')
        actual=matching_font(p,12)
        self.assertIn('12px',actual)
        im=render('关卡完成！',actual,12,(255,255,255),scale=2,canvas=(256,32))
        self.assertEqual(im.size,(256,32))
        self.assertEqual(set(im.getchannel('A').getdata()),{0,255})

    def test_overflow_and_offset_rejected(self):
        p=str(BASE/'fonts/fusion-pixel-8px-proportional-zh_hans.ttf')
        with self.assertRaises(ValueError):render('金币 :',p,8,(255,255,255),canvas=(10,8))
        with self.assertRaises(ValueError):render('生命',p,8,(255,255,255),canvas=(20,10),pad=(10,0))

    def test_outline_is_dilation_without_changing_ink(self):
        p=str(BASE/'fonts/fusion-pixel-8px-proportional-zh_hans.ttf')
        plain=render('生命',p,8,(255,255,255),outline_w=0)
        outlined=render('生命',p,8,(255,255,255),outline_w=1)
        self.assertEqual(outlined.size,(plain.width+2,plain.height+2))
        plain_ink=[p[:3]==(255,255,255) and p[3]>0 for p in plain.getdata()]
        outlined_ink=[p[:3]==(255,255,255) and p[3]>0 for p in outlined.getdata()]
        self.assertEqual(sum(plain_ink),sum(outlined_ink))


if __name__=='__main__':unittest.main()
