"""Fail when a new email or a photo metadata segment shows up.

The public address nxsareen@gmail.com is allowed only in nikhil_sareen.html
and content/nikhil_sareen.md. Any other email-shaped string in the root HTML
or under content/ fails. A JPEG APP1 segment, or a PNG text chunk (tEXt,
zTXt, iTXt) or eXIf chunk, under images/ fails. Stdlib only.
"""
import os
import re
import shutil
import struct
import tempfile
import unittest
import zlib

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PUBLIC_EMAIL = b"nxsareen@gmail.com"
BIO_PAGES = ("nikhil_sareen.html", "content/nikhil_sareen.md")
EMAIL = re.compile(br"[A-Za-z0-9._%+\-]+@[A-Za-z0-9][A-Za-z0-9.\-]*\.[A-Za-z]{2,}")
PNG_META = {b"tEXt", b"zTXt", b"iTXt", b"eXIf"}
PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def jpeg_has_app1(data):
    """True when a JPEG has an APP1 segment (EXIF, XMP) before the scan."""
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return False
    i, n = 2, len(data)
    while i + 1 < n:
        if data[i] != 0xFF:
            return False
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            return False
        marker = data[i]
        i += 1
        if marker == 0xD9:
            return False
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            continue
        if i + 2 > n:
            return False
        seglen = (data[i] << 8) | data[i + 1]
        if seglen < 2 or i + seglen > n:
            return False
        if marker == 0xE1:
            return True
        if marker == 0xDA:
            return False
        i += seglen
    return False


def png_meta_chunks(data):
    """PNG text chunks and eXIf chunks. Colour profiles (iCCP) are not metadata here."""
    found = []
    if len(data) < 8 or data[:8] != PNG_SIG:
        return found
    i, n = 8, len(data)
    while i + 8 <= n:
        length = struct.unpack(">I", data[i : i + 4])[0]
        ctype = data[i + 4 : i + 8]
        if i + 12 + length > n:
            break
        if ctype in PNG_META:
            found.append(ctype.decode("ascii"))
        i += 12 + length
        if ctype == b"IEND":
            break
    return found


def _text_files(root):
    for name in sorted(os.listdir(root)):
        if name.endswith(".html"):
            path = os.path.join(root, name)
            if os.path.isfile(path):
                yield path
    content = os.path.join(root, "content")
    if not os.path.isdir(content):
        return
    for dirpath, dirnames, filenames in os.walk(content):
        dirnames.sort()
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)


def _image_files(root):
    images = os.path.join(root, "images")
    if not os.path.isdir(images):
        return
    for dirpath, dirnames, filenames in os.walk(images):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if os.path.isfile(path):
                yield path


def scan(root):
    """Violation strings for root HTML, content/, and images/. Empty means clean."""
    problems = []
    for path in _text_files(root):
        with open(path, "rb") as fh:
            data = fh.read()
        rel = _rel(root, path)
        for match in EMAIL.findall(data):
            if match == PUBLIC_EMAIL and rel in BIO_PAGES:
                continue
            problems.append(f"{rel}: email {match.decode('ascii', 'replace')}")
    for path in _image_files(root):
        with open(path, "rb") as fh:
            data = fh.read()
        rel = _rel(root, path)
        if jpeg_has_app1(data):
            problems.append(f"{rel}: JPEG APP1 segment")
        for chunk in png_meta_chunks(data):
            problems.append(f"{rel}: PNG {chunk} chunk")
    return problems


def _png(*chunks):
    def chunk(ctype, payload):
        crc = zlib.crc32(ctype + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + ctype + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    parts = [PNG_SIG, chunk(b"IHDR", ihdr)]
    for ctype, payload in chunks:
        parts.append(chunk(ctype, payload))
    parts.append(chunk(b"IEND", b""))
    return b"".join(parts)


class PrivacyTest(unittest.TestCase):
    def test_repo_allows_only_the_public_bio_email(self):
        self.assertEqual(scan(REPO), [])
        bio = os.path.join(REPO, "nikhil_sareen.html")
        with open(bio, "rb") as fh:
            self.assertIn(PUBLIC_EMAIL, fh.read())
        later = os.path.join(REPO, "content", "nikhil_sareen.md")
        if os.path.isfile(later):
            with open(later, "rb") as fh:
                self.assertIn(PUBLIC_EMAIL, fh.read())

    def test_second_email_fails(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        with open(os.path.join(root, "about.html"), "w", encoding="utf-8") as fh:
            fh.write("<p>Write to other.person@example.com please.</p>\n")
        with open(os.path.join(root, "nikhil_sareen.html"), "w", encoding="utf-8") as fh:
            fh.write("nxsareen@gmail.com and also second@example.org\n")
        problems = scan(root)
        self.assertTrue(any("about.html: email other.person@example.com" in p for p in problems))
        self.assertTrue(any("nikhil_sareen.html: email second@example.org" in p for p in problems))
        self.assertFalse(any(p.endswith("email nxsareen@gmail.com") for p in problems))

    def test_public_email_outside_the_bio_fails(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        os.makedirs(os.path.join(root, "content"))
        with open(os.path.join(root, "about.html"), "w", encoding="utf-8") as fh:
            fh.write("nxsareen@gmail.com\n")
        with open(os.path.join(root, "content", "about.md"), "w", encoding="utf-8") as fh:
            fh.write("see nxsareen@gmail.com\n")
        problems = scan(root)
        self.assertEqual(
            problems,
            [
                "about.html: email nxsareen@gmail.com",
                "content/about.md: email nxsareen@gmail.com",
            ],
        )

    def test_jpeg_app1_fails_and_colour_profile_does_not(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        images = os.path.join(root, "images")
        os.makedirs(images)
        exif = b"Exif\x00\x00"
        app1 = b"\xff\xd8\xff\xe1" + struct.pack(">H", 2 + len(exif)) + exif + b"\xff\xd9"
        icc = b"ICC_PROFILE\x00" + b"\x00" * 8
        app2 = b"\xff\xd8\xff\xe2" + struct.pack(">H", 2 + len(icc)) + icc + b"\xff\xd9"
        with open(os.path.join(images, "tagged.jpg"), "wb") as fh:
            fh.write(app1)
        self.assertEqual(scan(root), ["images/tagged.jpg: JPEG APP1 segment"])
        with open(os.path.join(images, "tagged.jpg"), "wb") as fh:
            fh.write(app2)
        self.assertEqual(scan(root), [])

    def test_png_text_and_exif_chunks_fail(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        images = os.path.join(root, "images")
        os.makedirs(images)
        path = os.path.join(images, "note.png")
        cases = {
            b"tEXt": b"Comment\x00hi",
            b"zTXt": b"Comment\x00\x00" + zlib.compress(b"hi"),
            b"iTXt": b"Comment\x00\x00\x00\x00\x00hi",
            b"eXIf": b"Exif\x00\x00",
        }
        for ctype, payload in cases.items():
            with open(path, "wb") as fh:
                fh.write(_png((ctype, payload)))
            self.assertEqual(
                scan(root),
                [f"images/note.png: PNG {ctype.decode('ascii')} chunk"],
                ctype,
            )
        with open(path, "wb") as fh:
            fh.write(_png())
        self.assertEqual(scan(root), [])
