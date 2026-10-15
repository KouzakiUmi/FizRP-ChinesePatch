"""Shared constants for the FizRP localization toolkit."""
from __future__ import annotations

# Order MUST match the game's `Language` enum (work/decompiled/Language.cs):
#   Japanese=0, English_Machine=1, English=2, French=3, Spanish=4, Max=5
LANGS = ["ja", "en_machine", "en", "fr", "es"]
LANG_LABELS = {
    "ja": "日本語",
    "en_machine": "English (machine)",
    "en": "English",
    "fr": "Français",
    "es": "Español",
}
# Unity Localization locale codes used by the game's Addressables groups
LOCALE_BUNDLES = {
    "en": "localization-string-tables-english(en)_assets_all.bundle",
    "ja": "localization-string-tables-japanese(ja)_assets_all.bundle",
    "fr": "localization-string-tables-french(fr)_assets_all.bundle",
    "es": "localization-string-tables-spanish(es)_assets_all.bundle",
}
# SharedTableData (the key table) lives in its own bundle.
SHARED_TABLE_BUNDLE = "localization-assets-shared_assets_all.bundle"
LOCALES_BUNDLE = "localization-locales_assets_all.bundle"

STR_TABLE_BUNDLE = {
    "en": "localization-string-tables-english(en)_assets_all.bundle",
    "fr": "localization-string-tables-french(fr)_assets_all.bundle",
    "ja": "localization-string-tables-japanese(ja)_assets_all.bundle",
    "es": "localization-string-tables-spanish(es)_assets_all.bundle",
}

CSV_COLUMNS = ["id", "kind", "file", "path_id", "source", "index", "path",
               "comment"] + ["text_" + l for l in LANGS] + ["text_zh_Hans"]
