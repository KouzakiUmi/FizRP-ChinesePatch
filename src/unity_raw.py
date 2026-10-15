"""Minimal raw readers for Unity 2021.3 serialized objects.

UnityPy's typetree generation fails for this build's Assembly-CSharp, so we
parse the few headers we need straight out of the serialized bytes.
"""
import struct

class R:
    def __init__(self, b, endian="<"):
        self.b = b; self.o = 0; self.e = endian
    def u32(self):
        v = struct.unpack_from(self.e+"I", self.b, self.o)[0]; self.o += 4; return v
    def i32(self):
        v = struct.unpack_from(self.e+"i", self.b, self.o)[0]; self.o += 4; return v
    def i64(self):
        v = struct.unpack_from(self.e+"q", self.b, self.o)[0]; self.o += 8; return v
    def align(self, n=4):
        self.o = (self.o + n - 1) // n * n
    def pptr(self):
        fid = self.i32(); pid = self.i64(); return (fid, pid)
    def string(self):
        n = self.i32(); s = self.b[self.o:self.o+n].decode("utf-8", "replace")
        self.o += n; self.align()
        return s

def mb_header(raw):
    """Return (m_GameObject, m_Enabled, m_Script, m_Name, payload_offset)."""
    r = R(raw)
    go = r.pptr()
    en = r.u32() & 0xFF
    r.align()
    sp = r.pptr()
    name = r.string()
    return go, en, sp, name, r.o

def font_header(raw):
    """UnityEngine.Font in 2021.3: name, then FontData."""
    r = R(raw)
    name = r.string()
    r.align()
    # m_FontData is a byte array: u32 length + bytes
    n = r.u32()
    # optional align differs by unity version; we return candidate slices
    return name, n, r.o
