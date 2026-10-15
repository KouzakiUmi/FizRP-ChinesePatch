"""Byte-exact readers/writers for the game's own ScriptableObject classes.

UnityPy cannot generate a usable typetree for these Assembly-CSharp classes,
so the layouts are declared here from the decompiled sources (see
`work/decompiled/*.cs`) and verified by decoding + re-encoding every object and
comparing against the original bytes.

Serialization rules used by Unity 2021.3 Mono builds:

* every field starts 4-byte aligned;
* 1/2-byte primitives (`bool`, `UInt8`, `SInt16`, ...) are padded to 4 bytes;
* `string` = int32 length + UTF-8 bytes, padded to 4 bytes;
* `List<T>` = int32 count + count elements.
"""
from __future__ import annotations

import struct

PPTR = "pptr"
STR = "str"
I32 = "i32"
F32 = "f32"
BOOL = "bool"


class Reader:
    def __init__(self, data: bytes, offset: int = 0):
        self.data = data
        self.pos = offset

    def align(self) -> None:
        self.pos = (self.pos + 3) // 4 * 4

    def i32(self) -> int:
        self.align()
        value = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return value

    def f32(self) -> float:
        self.align()
        value = struct.unpack_from("<f", self.data, self.pos)[0]
        self.pos += 4
        return value

    def u8(self) -> int:
        self.align()
        value = self.data[self.pos]
        self.pos += 1
        return value

    def pptr(self) -> dict:
        self.align()
        file_id = self.i32()
        self.align()
        path_id = struct.unpack_from("<q", self.data, self.pos)[0]
        self.pos += 8
        return {"m_FileID": file_id, "m_PathID": path_id}

    def string(self) -> str:
        length = self.i32()
        text = self.data[self.pos:self.pos + length].decode("utf-8", "surrogateescape")
        self.pos += length
        self.align()
        return text


class Writer:
    def __init__(self):
        self.buf = bytearray()

    def align(self) -> None:
        while len(self.buf) % 4:
            self.buf.append(0)

    def i32(self, value: int) -> None:
        self.align()
        self.buf += struct.pack("<i", value)

    def f32(self, value: float) -> None:
        self.align()
        self.buf += struct.pack("<f", value)

    def u8(self, value: int) -> None:
        self.align()
        self.buf.append(value & 0xFF)

    def pptr(self, value: dict) -> None:
        self.i32(value.get("m_FileID", 0))
        self.buf += struct.pack("<q", value.get("m_PathID", 0))

    def string(self, value: str) -> None:
        self.align()
        raw = value.encode("utf-8", "surrogateescape")
        self.buf += struct.pack("<i", len(raw))
        self.buf += raw
        self.align()

    def bytes(self) -> bytes:
        return bytes(self.buf)


def read_value(reader: Reader, spec):
    if isinstance(spec, list):
        count = reader.i32()
        return [read_value(reader, spec[0]) for _ in range(count)]
    if isinstance(spec, tuple):
        return {name: read_value(reader, sub) for name, sub in spec[1]}
    if spec == STR:
        return reader.string()
    if spec == I32:
        return reader.i32()
    if spec == F32:
        return reader.f32()
    if spec == BOOL:
        return reader.u8()
    if spec == PPTR:
        return reader.pptr()
    raise ValueError(f"unknown spec {spec!r}")


def write_value(writer: Writer, spec, value) -> None:
    if isinstance(spec, list):
        writer.i32(len(value))
        for item in value:
            write_value(writer, spec[0], item)
        return
    if isinstance(spec, tuple):
        for name, sub in spec[1]:
            write_value(writer, sub, value[name])
        return
    if spec == STR:
        writer.string(value)
    elif spec == I32:
        writer.i32(value)
    elif spec == F32:
        writer.f32(value)
    elif spec == BOOL:
        writer.u8(value)
    elif spec == PPTR:
        writer.pptr(value)
    else:
        raise ValueError(f"unknown spec {spec!r}")


# --------------------------------------------------------------------------
# class layouts
# --------------------------------------------------------------------------
TALK_DATA = ("TalkData", [
    ("chara", I32), ("faceSpriteMode", I32), ("charaSprite", PPTR),
    ("text", STR), ("wait", F32), ("unityEventIndex", I32),
    ("unityTextEndEventIndex", I32),
])

TEXT_DATA = ("TextData", [
    ("textDatas", [("TextDataClass", [
        ("memo", STR), ("language", I32), ("strings", [STR])])]),
])

AUTO_TALK = ("AutoTalk_Data", [
    ("memo", STR), ("isManualMode", BOOL), ("isCheckViewedFlag", BOOL),
    ("talkedFlagKey", STR),
    ("talkDatas", [TALK_DATA]),
    ("locTalkDatas", [("LocTalkData", [("language", I32), ("talkDatas", [TALK_DATA])])]),
    ("nextTalk", PPTR),
])

TITLE_DATA = ("Title_Data", [
    ("isManualMode", BOOL),
    ("label", STR), ("label_en_machine", STR), ("label_en", STR),
    ("label_es", STR), ("label_fr", STR),
    ("info", STR), ("info_en_machine", STR), ("info_en", STR),
    ("info_es", STR), ("info_fr", STR),
    ("infoDisable", STR), ("infoDisable_en_machine", STR), ("infoDisable_en", STR),
    ("infoDisable_es", STR), ("infoDisable_fr", STR),
    ("isExtremity", BOOL), ("stopTitle", BOOL),
    ("top", I32), ("eventNum", I32), ("titleFunc", I32),
    ("flagKey", STR), ("isSirent", BOOL), ("sceneName", STR),
    ("children", [PPTR]), ("titleSpecialFunc", I32),
])

FONT_DATA_CLASS = ("FontDataClass", [
    ("memo", STR), ("language", I32), ("font", PPTR),
    ("size", I32), ("lineSpacing", F32),
])

LOC_FONT_DATA = ("LocFontData", [
    ("defaultFont", FONT_DATA_CLASS), ("fontDatas", [FONT_DATA_CLASS]),
])

DAMAGE_TALK = ("DamageTalk", [
    ("sensitivity", I32), ("charaSprite", PPTR), ("text", STR), ("wait", F32),
])

# Declaration order from DamageTalk_Data.SinglePlayerTalk. Note the enum has a
# `miss_capture` value but the class has no such List, so it must NOT appear here.
DAMAGE_LIST_NAMES = [
    "damage_normal", "damage_electric", "damage_water", "damage_vore",
    "damage_fire", "damage_stone", "damage_capture", "miss_normal",
    "miss_fall", "miss_electric", "miss_water", "miss_vore", "miss_fire",
    "miss_stone", "situation_pinch", "specialAttack",
]

DAMAGE_TALK_DATA = ("DamageTalk_Data", [
    ("player", [("SinglePlayerTalk",
                 [("charaName", STR), ("defaultCharaSprite", PPTR), ("defaultWait", F32)]
                 + [(name, [DAMAGE_TALK]) for name in DAMAGE_LIST_NAMES])]),
])

CLASSES = {name: (name, fields) for name, fields in
           [TEXT_DATA, AUTO_TALK, TITLE_DATA, LOC_FONT_DATA, DAMAGE_TALK_DATA]}

# header = m_GameObject PPtr + m_Enabled + m_Script PPtr + m_Name
HEADER_BYTES = 12 + 4 + 12


def header_end(raw: bytes) -> int:
    """Offset just past the MonoBehaviour header (after m_Name)."""
    reader = Reader(raw)
    reader.pptr()
    reader.u8()
    reader.align()
    reader.pptr()
    reader.string()
    return reader.pos


def decode(raw: bytes, class_name: str) -> dict:
    spec = CLASSES[class_name]
    reader = Reader(raw, header_end(raw))
    return read_value(reader, spec)


def encode(data: dict, class_name: str) -> bytes:
    spec = CLASSES[class_name]
    writer = Writer()
    write_value(writer, spec, data)
    return writer.bytes()
