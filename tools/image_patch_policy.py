"""Runtime scope for Chinese image replacements, independent of the artwork archive."""

import math

JAPANESE_IMAGE_BUNDLE = 'bundle: localization-assets-japanese(ja)_assets_all.bundle'
SHARED_IMAGE_BUNDLE = 'bundle: localization-assets-shared_assets_all.bundle'

# These Sprites live in otherwise shared textures. Keep only their Japanese
# rectangles pristine; removing the texture would also remove Chinese sprites.
_JAPANESE_SPRITES = {
    (SHARED_IMAGE_BUNDLE, -8012239730153050717): ('SoracoFishingLogo_0',),
    (SHARED_IMAGE_BUNDLE, 2036942083307812923): ('ひっさつ禁止_0',),
    (SHARED_IMAGE_BUNDLE, 171799377990236673): (
        '扉サイン_PauseArea_0', '扉サイン_PauseArea_Hiroba'),
    ('assets: sharedassets3.assets', 36): tuple(
        'UICharaBG_Name_jp_' + name for name in
        ('Fiz', 'Rythron', 'Soraco', 'Kyuma', 'Leafur', 'Rubell')),
}


def japanese_sprite_names(ticket):
    return _JAPANESE_SPRITES.get((ticket['运行时来源'], ticket['path_id']), ())


def sprite_png_box(rect, width, height):
    """Enclose Unity's bottom-left float rectangle in top-left PNG texels."""
    x, y, w, h = (rect[k] for k in ('x', 'y', 'width', 'height'))
    if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
        raise ValueError('Invalid sprite rectangle')
    box = (math.floor(x), height - math.ceil(y + h),
           math.ceil(x + w), height - math.floor(y))
    if box[0] < 0 or box[1] < 0 or box[2] > width or box[3] > height:
        raise ValueError('Sprite rectangle outside texture')
    return box


def japanese_only_reason(ticket):
    """Match runtime resource identity, not Japanese characters in an asset name.

    The Japanese stage-call sheet is selected only by CanvasCamera's Japanese
    branch. Its non-Japanese counterpart is sharedassets3.assets:57 (IMG-07).
    Japanese localization-bundle images are not used by the Chinese/es locale.
    Mixed/shared textures must remain eligible, even if their names are Japanese.
    """
    source = ticket['运行时来源']
    if source == JAPANESE_IMAGE_BUNDLE:
        return 'Japanese localization image bundle; not used by Chinese/es'
    if source == 'assets: sharedassets3.assets' and ticket['path_id'] == 32:
        return 'Japanese-only stage-call sheet; Chinese uses path_id 57'
    return None


def select_runtime_tickets(tickets):
    selected, excluded = [], []
    for ticket in tickets:
        reason = japanese_only_reason(ticket)
        if reason:
            excluded.append({'id': ticket['id'], 'source': ticket['运行时来源'],
                             'path_id': ticket['path_id'], 'reason': reason})
        else:
            selected.append(ticket)
    return selected, excluded
