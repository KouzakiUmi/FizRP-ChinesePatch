"""Image language-scope regressions; no Unity/game files or image libraries needed."""
from pathlib import Path
import unittest

from tools.image_patch_policy import (JAPANESE_IMAGE_BUNDLE, japanese_sprite_names,
                                      select_runtime_tickets, sprite_png_box)

ROOT = Path(__file__).resolve().parents[1]
SHARED = 'bundle: localization-assets-shared_assets_all.bundle'
ASSETS = 'assets: sharedassets3.assets'


def ticket(number, source, path_id):
    return {'id': 'IMG-%02d' % number, '运行时来源': source, 'path_id': path_id,
            '名称': '日文名称也可能是共享资源'}


class ImagePatchPolicyTests(unittest.TestCase):
    def test_japanese_stage_sheet_excluded_but_chinese_sheet_kept(self):
        jp = ticket(6, ASSETS, 32)
        chinese = ticket(7, ASSETS, 57)
        selected, excluded = select_runtime_tickets([jp, chinese])
        self.assertEqual(selected, [chinese])
        self.assertEqual([t['id'] for t in excluded], ['IMG-06'])

    def test_japanese_title_bundle_excluded(self):
        selected, excluded = select_runtime_tickets([
            ticket(15, JAPANESE_IMAGE_BUNDLE, 2853699348273556055),
            ticket(16, JAPANESE_IMAGE_BUNDLE, 1514627115771595891)])
        self.assertEqual(selected, [])
        self.assertEqual([t['id'] for t in excluded], ['IMG-15', 'IMG-16'])
        self.assertTrue(all(t['reason'] for t in excluded))

    def test_shared_images_with_japanese_names_kept(self):
        images = [ticket(1, SHARED, 6686869478942759292),
                  ticket(2, SHARED, -7982049647970367283),
                  ticket(4, SHARED, 2036942083307812923),
                  ticket(8, ASSETS, 36)]
        self.assertEqual(select_runtime_tickets(images), (images, []))

    def test_filter_uses_resource_identity_not_ticket_number(self):
        shared = ticket(15, SHARED, 32)
        jp = ticket(99, ASSETS, 32)
        self.assertEqual(select_runtime_tickets([shared, jp])[0], [shared])

    def test_catalog_sixteen_becomes_thirteen_without_mutation(self):
        images = [ticket(i, SHARED, i) for i in range(1, 17)]
        images[5] = ticket(6, ASSETS, 32)
        images[14] = ticket(15, JAPANESE_IMAGE_BUNDLE, 2853699348273556055)
        images[15] = ticket(16, JAPANESE_IMAGE_BUNDLE, 1514627115771595891)
        before = [dict(t) for t in images]
        selected, excluded = select_runtime_tickets(images)
        self.assertEqual(len(selected), 13)
        self.assertEqual(len(excluded), 3)
        self.assertEqual(images, before)
        self.assertEqual(select_runtime_tickets(selected), (selected, []))

    def test_only_ten_japanese_slices_are_protected_in_four_atlases(self):
        images = [ticket(3, SHARED, -8012239730153050717),
                  ticket(4, SHARED, 2036942083307812923),
                  ticket(5, SHARED, 171799377990236673), ticket(8, ASSETS, 36)]
        self.assertEqual([len(japanese_sprite_names(t)) for t in images], [1, 1, 2, 6])
        self.assertEqual(japanese_sprite_names(ticket(7, ASSETS, 57)), ())
        self.assertEqual(japanese_sprite_names(ticket(8, SHARED, 36)), ())

    def test_unity_bottom_left_box_is_converted_without_clipping_edges(self):
        self.assertEqual(sprite_png_box({'x': 32, 'y': 112, 'width': 32, 'height': 16},
                                       192, 128), (32, 0, 64, 16))
        self.assertEqual(sprite_png_box({'x': 1.1, 'y': 2.2, 'width': 3.3, 'height': 4.4},
                                       10, 10), (1, 3, 5, 8))

    def test_invalid_or_outside_sprite_rect_is_rejected(self):
        for rect in ({'x': -1, 'y': 0, 'width': 2, 'height': 2},
                     {'x': 0, 'y': 0, 'width': 0, 'height': 2},
                     {'x': float('nan'), 'y': 0, 'width': 2, 'height': 2}):
            with self.assertRaises(ValueError):
                sprite_png_box(rect, 10, 10)

    def test_injection_filters_before_grouping_or_loading_assets(self):
        source = (ROOT / 'tools/build_image_patch.py').read_text(encoding='utf-8')
        filter_at = source.index('tickets,excluded=select_runtime_tickets(tickets)')
        self.assertLess(filter_at, source.index('for t in tickets:'))
        self.assertLess(filter_at, source.index('UnityPy.load(str(source))'))
        self.assertIn("'excluded_japanese_only':excluded", source)


if __name__ == '__main__':
    unittest.main()
