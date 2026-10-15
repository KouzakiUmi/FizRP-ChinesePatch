"""UnityPy environment helpers for Fiz And The Rainbow Planet.

Two UnityPy 1.25.4 issues have to be worked around before the game's own
MonoBehaviours can be read:

1. `TypeTreeGeneratorAPI` produces nodes for classes defined in the game's
   Assembly-CSharp.dll, but it does not emit the `kAlignBytes` (0x4000) meta
   flag that Unity's serializer uses to pad 1/2-byte fields up to 4 bytes.
   Without the flag every field after `m_Enabled` is read 3 bytes early.
2. The optional `UnityPyBoost` C++ reader ignores that meta flag entirely, so
   it must be disabled for generated typetrees.

Both fixes are installed on **import** of this module and are process-global:
`TypeTreeHelper.read_typetree_boost` is set to None and
`ObjectReader.generate_monobehaviour_node` is replaced.  Any other code in the
same process that imports UnityPy therefore inherits them.  `install_patches()`
is idempotent; `patches_installed()` reports whether they are active.
"""
from __future__ import annotations

import ntpath
import os

import UnityPy
import UnityPy.helpers.TypeTreeHelper as TypeTreeHelper
from UnityPy.files.ObjectReader import ObjectReader
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
from UnityPy.helpers.TypeTreeHelper import kAlignBytes

GAME_ROOT = os.environ.get("FIZRP_ROOT", r"E:\Steam\steamapps\common\FizRP")
DATA_DIR = os.path.join(GAME_ROOT, "FizAndTheRainbowPlanet_Data")
BUNDLE_DIR = os.path.join(DATA_DIR, "StreamingAssets", "aa", "StandaloneWindows64")
UNITY_VERSION = "2021.3.45f1"

# --------------------------------------------------------------------------
# workaround 1: the C++ typetree reader ignores alignment meta flags
# --------------------------------------------------------------------------
TypeTreeHelper.read_typetree_boost = None

# --------------------------------------------------------------------------
# workaround 2: generated typetrees are missing kAlignBytes on small ints
# --------------------------------------------------------------------------
_SMALL_INTS = frozenset(
    {"UInt8", "SInt8", "char", "bool", "UInt16", "SInt16", "short", "unsigned short"}
)


def _align_small_ints(node, parent_type=None):
    for child in node.m_Children:
        if child.m_Type in _SMALL_INTS and parent_type != "Array":
            child.m_MetaFlag = (child.m_MetaFlag or 0) | kAlignBytes
        _align_small_ints(child, child.m_Type)


_original_generate = ObjectReader.generate_monobehaviour_node


def _generate_monobehaviour_node(self, mb_node=None):
    node = _original_generate(self, mb_node)
    _align_small_ints(node)
    return node


_PATCHED = False


def install_patches() -> None:
    """Apply the two work-arounds. Safe to call repeatedly."""
    global _PATCHED
    if _PATCHED:
        return
    TypeTreeHelper.read_typetree_boost = None
    ObjectReader.generate_monobehaviour_node = _generate_monobehaviour_node
    _PATCHED = True


def patches_installed() -> bool:
    return _PATCHED


install_patches()

_generator: TypeTreeGenerator | None = None


def generator() -> TypeTreeGenerator:
    """Shared typetree generator built from the game's Managed DLLs."""
    global _generator
    if _generator is None:
        gen = TypeTreeGenerator(UNITY_VERSION)
        gen.load_local_game(GAME_ROOT)
        _generator = gen
    return _generator


def open_env(*paths: str) -> UnityPy.Environment:
    """Load serialized files / bundles and make MonoBehaviour reads work.

    Files are re-keyed by basename so that `m_FileID` externals such as
    `globalgamemanagers.assets` resolve.
    """
    env = UnityPy.load(*paths)
    env.files = {ntpath.basename(k): v for k, v in env.files.items()}
    env.cabs = {ntpath.basename(k).lower(): v for k, v in env.cabs.items()}
    env.typetree_generator = generator()
    return env


def game_file_env(*names: str) -> UnityPy.Environment:
    """Open files from the game's data dir by name plus the script file."""
    paths = [os.path.join(DATA_DIR, n) for n in names]
    if "globalgamemanagers.assets" not in names:
        paths.insert(0, os.path.join(DATA_DIR, "globalgamemanagers.assets"))
    return open_env(*paths)


# --------------------------------------------------------------------------
# class identification that never depends on a successful typetree read
# --------------------------------------------------------------------------
_scripts: dict[int, str] | None = None


def script_classes() -> dict[int, str]:
    """path_id -> class name for every MonoScript in globalgamemanagers.assets."""
    global _scripts
    if _scripts is None:
        env = UnityPy.load(os.path.join(DATA_DIR, "globalgamemanagers.assets"))
        table = {}
        for obj in env.objects:
            if obj.type.name == "MonoScript":
                table[obj.path_id] = obj.read_typetree().get("m_ClassName")
        _scripts = table
    return _scripts


def mb_class(obj, serialized_file) -> str | None:
    """Resolve a MonoBehaviour's script class from raw bytes.

    UnityPy cannot always build a typetree for this game's Assembly-CSharp
    classes, so the header is parsed by hand and the MonoScript looked up in
    the external `globalgamemanagers.assets` file.
    """
    from unity_raw import mb_header

    _go, _enabled, script, _name, _off = mb_header(obj.get_raw_data())
    file_id, path_id = script
    if file_id == 0:
        for other in serialized_file.objects.values():
            if other.path_id == path_id and other.type.name == "MonoScript":
                return other.read_typetree().get("m_ClassName")
        return None
    externals = getattr(serialized_file, "externals", None) or []
    if not 0 < file_id <= len(externals):
        return None
    target = ntpath.basename(str(externals[file_id - 1].path))
    if target != "globalgamemanagers.assets":
        return None
    return script_classes().get(path_id)


def mb_name(obj) -> str:
    from unity_raw import mb_header

    return mb_header(obj.get_raw_data())[3]
