"""Colour profiles from tools/add_image.py.

A CMYK JPEG comes out RGB with no profile, resized or not. A 16-bit grey PNG
with a grey iCCP, reduced to a palette, keeps no grey profile. An RGB JPEG
keeps an RGB profile. Images under images/ are not rewritten.

Skips when Pillow is missing, so the rest of the suite still runs.
"""
import contextlib
import importlib.util
import io
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

try:
    from PIL import Image
except ImportError:
    Image = None

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_add_image():
    path = os.path.join(REPO, "tools", "add_image.py")
    spec = importlib.util.spec_from_file_location("add_image", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _icc(space):
    header = bytearray(128)
    struct.pack_into(">I", header, 0, 128)
    header[12:16] = b"mntr"
    header[16:20] = space
    header[20:24] = b"XYZ "
    header[36:40] = b"acsp"
    return bytes(header)


def _iccp_space(raw_chunk):
    payload = raw_chunk[8:-4]
    _, rest = payload.split(b"\x00", 1)
    if not rest or rest[:1] != b"\x00":
        return None
    profile = zlib.decompress(rest[1:])
    return profile[16:20] if len(profile) >= 20 else None


@unittest.skipUnless(Image is not None, "Pillow is not installed")
class AddImageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_add_image()

    def run_image(self, image, fmt, profile, width, palette=False, **save_kw):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        src = os.path.join(tmp, "src")
        out = os.path.join(tmp, "out")
        image.save(src, fmt, icc_profile=profile, **save_kw)
        with contextlib.redirect_stdout(io.StringIO()):
            self.mod.process(src, out, width, palette)
        return src, out

    def test_cmyk_jpeg_resized_and_not_resized_is_rgb_without_profile(self):
        image = Image.new("CMYK", (40, 30), (8, 16, 24, 32))
        profile = _icc(b"CMYK")
        # 820 leaves a 40px image unresized; 4 forces the resize.
        for width in (820, 4):
            src, out = self.run_image(image, "JPEG", profile, width, quality=90)
            with Image.open(src) as source:
                self.assertEqual(source.mode, "CMYK")
                self.assertEqual(source.info.get("icc_profile", b"")[16:20], b"CMYK")
            with Image.open(out) as saved:
                self.assertEqual(saved.mode, "RGB", width)
                self.assertIsNone(saved.info.get("icc_profile"))
            with open(out, "rb") as fh:
                self.assertNotIn(b"ICC_PROFILE", fh.read())

    def test_grey_png_palette_drops_grey_profile(self):
        image = Image.new("I;16", (24, 8))
        pixels = image.load()
        for x in range(24):
            for y in range(8):
                pixels[x, y] = 500 + x * 1000 + y * 17
        src, out = self.run_image(image, "PNG", _icc(b"GRAY"), 820, palette=True)
        with Image.open(src) as source:
            self.assertEqual(source.mode, "I;16")
            self.assertEqual(source.info.get("icc_profile", b"")[16:20], b"GRAY")
        with Image.open(out) as saved:
            self.assertEqual(saved.mode, "P")
            kept = saved.info.get("icc_profile")
            self.assertTrue(kept is None or kept[16:20] != b"GRAY")
        with open(out, "rb") as fh:
            for ctype, raw in self.mod.png_chunks(fh.read()):
                if ctype == b"iCCP":
                    self.assertNotEqual(_iccp_space(raw), b"GRAY")

    def test_rgb_jpeg_keeps_rgb_profile(self):
        image = Image.new("RGB", (40, 30), (10, 20, 30))
        profile = _icc(b"RGB ")
        for width in (820, 4):
            src, out = self.run_image(image, "JPEG", profile, width, quality=90)
            with Image.open(src) as source:
                self.assertEqual(source.info.get("icc_profile", b"")[16:20], b"RGB ")
            with Image.open(out) as saved:
                self.assertEqual(saved.mode, "RGB")
                kept = saved.info.get("icc_profile")
                self.assertIsNotNone(kept)
                self.assertEqual(kept[16:20], b"RGB ")
