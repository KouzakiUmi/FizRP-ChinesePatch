"""Isolated RGBA region restoration; no game assets are loaded."""
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
try:
    from PIL import Image
    from build_image_patch import prepare_image
except ImportError as exc:
    raise unittest.SkipTest('Needs the image build dependencies: ' + str(exc))


class ImageRegionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fizrp-image-region-test-')
        self.base = Path(self.temp.name).resolve()
        self.addCleanup(self.clean_temp)
        self.asset = object()
        self.texture = types.SimpleNamespace(assets_file=self.asset, path_id=2036942083307812923)
        self.ticket = {'id': 'IMG-04', '源文件': 'original.png',
                       '运行时来源': 'bundle: localization-assets-shared_assets_all.bundle',
                       'path_id': self.texture.path_id}
        self.original = Image.new('RGBA', (4, 4), (20, 30, 40, 0))
        self.original.putpixel((0, 0), (50, 60, 70, 127))
        self.original.save(self.base / 'original.png')
        data = {'m_Name': 'ひっさつ禁止_0', 'm_RD': {
            'texture': {'m_FileID': 0, 'm_PathID': self.texture.path_id},
            'textureRect': {'x': 0, 'y': 2, 'width': 2, 'height': 2}}}
        self.sprite = types.SimpleNamespace(type=types.SimpleNamespace(name='Sprite'),
                                            assets_file=self.asset, read_typetree=lambda: data)
        self.env = types.SimpleNamespace(objects=[self.sprite])

    def clean_temp(self):
        target = Path(self.temp.name).resolve()
        assert target == self.base and target.parent == Path(tempfile.gettempdir()).resolve()
        assert target.name.startswith('fizrp-image-region-test-')
        self.temp.cleanup()

    def test_original_rgba_is_copied_without_alpha_blending(self):
        chinese = Image.new('RGBA', (4, 4), (255, 0, 0, 255))
        before = chinese.tobytes()
        result, regions = prepare_image(self.ticket, self.env, self.texture, chinese, self.base)
        self.assertEqual(result.crop((0, 0, 2, 2)).tobytes(), self.original.crop((0, 0, 2, 2)).tobytes())
        self.assertEqual(result.crop((2, 0, 4, 4)).tobytes(), chinese.crop((2, 0, 4, 4)).tobytes())
        self.assertEqual(result.crop((0, 2, 2, 4)).tobytes(), chinese.crop((0, 2, 2, 4)).tobytes())
        self.assertEqual(chinese.tobytes(), before)
        self.assertEqual(regions[0]['png_box'], (0, 0, 2, 2))

    def test_missing_or_duplicate_protected_sprite_fails_closed(self):
        for sprites in ([], [self.sprite, self.sprite]):
            with self.assertRaises(RuntimeError):
                prepare_image(self.ticket, types.SimpleNamespace(objects=sprites), self.texture,
                              self.original, self.base)

    def test_original_image_size_mismatch_fails_closed(self):
        with self.assertRaises(RuntimeError):
            prepare_image(self.ticket, self.env, self.texture,
                          Image.new('RGBA', (8, 8)), self.base)

    def test_unrelated_texture_needs_no_original_image(self):
        ticket = dict(self.ticket, path_id=999)
        image = Image.new('RGBA', (4, 4))
        actual, regions = prepare_image(ticket, self.env, self.texture, image, self.base / 'absent')
        self.assertIs(actual, image)
        self.assertEqual(regions, [])


if __name__ == '__main__':
    unittest.main()
