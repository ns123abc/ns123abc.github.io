#!/usr/bin/env python3
"""Shrink an image for the site: at most twice its display width, metadata stripped.

    python3 tools/add_image.py ~/Desktop/IMG_1234.jpeg --width 420
    python3 tools/add_image.py images/slogo1.png --width 30 --palette --in-place

--width is the CSS width the page shows the image at (default 820, the widest the main
column gets). The output is at most twice that, for high-density screens, and is never
upscaled. A resize under 10% is skipped: resampling softens text for almost no saving.

New images go to images/<name>.jpg or .png, where <name> is the source name lowercased
with anything outside [a-z0-9_-] turned into "-". PNG stays PNG; everything else becomes
JPEG (quality 80, progressive). The script prints an <img> tag with width and height.

EXIF (including GPS), XMP, IPTC and comments are always removed. Colour profiles are kept,
so colours don't shift. When no resize is needed the pixels are left exactly as they are
and only metadata is removed, except that a JPEG is re-encoded if that makes it at least
30% smaller (the source was saved at a much higher quality than the site needs).

--palette reduces a PNG to 256 colours, which suits small icons; the script reports the
largest per-channel error so you can judge it. Without it, PNGs are lossless.

Needs Pillow: python3 -m pip install Pillow
"""
import argparse
import io
import os
import re
import struct
import sys

try:
    from PIL import Image, ImageChops, ImageOps
except ImportError:
    sys.exit("add_image.py needs Pillow: python3 -m pip install Pillow")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WIDTH = 820
RESIZE_SLACK = 1.10
JPEG_QUALITY = 80
JPEG_MIN_SAVING = 0.30

# JPEG APPn/COM segments worth keeping, by marker and payload prefix: JFIF header,
# ICC colour profile, Adobe colour-transform flag. Every other APPn (EXIF, XMP, IPTC,
# MPF...) and every comment is dropped.
JPEG_KEEP = {0xE0: b"JFIF\0", 0xE2: b"ICC_PROFILE\0", 0xEE: b"Adobe"}
# PNG chunks that describe colour; carried over from the source as raw bytes.
PNG_COLOUR = (b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"cICP")
PNG_KEEP = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"} | set(PNG_COLOUR)


def png_chunks(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    i = 8
    while i < len(data):
        (n,) = struct.unpack(">I", data[i : i + 4])
        ctype = data[i + 4 : i + 8]
        yield ctype, data[i : i + 12 + n]
        i += 12 + n
        if ctype == b"IEND":
            return


def strip_png(data):
    return data[:8] + b"".join(raw for ctype, raw in png_chunks(data) if ctype in PNG_KEEP)


def with_colour_chunks(encoded, source):
    """Insert the source PNG's colour chunks right after IHDR, where the spec wants them."""
    colour = b"".join(raw for ctype, raw in png_chunks(source) if ctype in PNG_COLOUR)
    ihdr_end = 8 + 12 + 13
    return encoded[:ihdr_end] + colour + encoded[ihdr_end:]


def strip_jpeg(data):
    """Drop metadata segments and anything after EOI; scan data is copied byte for byte."""
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    out, i = [b"\xff\xd8"], 2
    while True:
        while data[i + 1] == 0xFF:
            i += 1
        marker = data[i + 1]
        if marker == 0xD9:
            out.append(b"\xff\xd9")
            return b"".join(out)
        (seglen,) = struct.unpack(">H", data[i + 2 : i + 4])
        seg, i = data[i : i + 2 + seglen], i + 2 + seglen
        if marker == 0xDA:
            j = i
            while True:
                j = data.index(b"\xff", j)
                nxt = data[j + 1]
                if nxt == 0 or 0xD0 <= nxt <= 0xD7:
                    j += 2
                elif nxt == 0xFF:
                    j += 1
                else:
                    break
            out.append(seg + data[i:j])
            i = j
        elif 0xE0 <= marker <= 0xEF or marker == 0xFE:
            keep = JPEG_KEEP.get(marker)
            if keep and seg[4 : 4 + len(keep)] == keep:
                out.append(seg)
        else:
            out.append(seg)


def same_pixels(a, b):
    mode = "RGBA" if "A" in a.getbands() or "A" in b.getbands() else "RGB"
    return ImageChops.difference(a.convert(mode), b.convert(mode)).getbbox() is None


def max_error(a, b):
    mode = "RGBA" if "A" in a.getbands() else "RGB"
    return max(hi for _, hi in ImageChops.difference(a.convert(mode), b.convert(mode)).getextrema())


def encode_jpeg(im, icc):
    if im.mode not in ("RGB", "L"):
        im, icc = im.convert("RGB"), None
    im.info = {}
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True, icc_profile=icc)
    return buf.getvalue()


def encode_png(im, source_png, palette):
    """Return (bytes, note). Lossless unless palette is set."""
    if im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema() == (255, 255):
        im = im.convert(im.mode[:-1])
    note = "lossless"
    if im.mode in ("RGB", "RGBA") and (palette or im.getcolors(256)):
        method = Image.Quantize.FASTOCTREE if im.mode == "RGBA" else Image.Quantize.MAXCOVERAGE
        quantized = im.quantize(256, method=method)
        if same_pixels(im, quantized):
            im = quantized
        elif palette:
            note = f"256-colour palette, max error {max_error(im, quantized)}/255"
            im = quantized
    im.info = {}
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return with_colour_chunks(buf.getvalue(), source_png), note


def process(src, out, width, palette):
    with open(src, "rb") as f:
        data = f.read()
    im = Image.open(io.BytesIO(data))
    if getattr(im, "n_frames", 1) > 1:
        raise SystemExit(f"{src}: animated images aren't supported")
    src_format = im.format
    fmt = "PNG" if src_format == "PNG" else "JPEG"
    if palette and fmt != "PNG":
        raise SystemExit(f"{src}: --palette only applies to PNG")
    icc = im.info.get("icc_profile")
    rotated = im.getexif().get(0x0112, 1) != 1
    im = ImageOps.exif_transpose(im)
    if im.mode == "P" or im.mode not in ("RGB", "RGBA", "L", "LA"):
        has_alpha = "transparency" in im.info or "A" in im.getbands()
        im = im.convert("RGBA" if has_alpha else "RGB")
    if fmt == "JPEG" and "A" in im.getbands():
        raise SystemExit(f"{src}: has transparency; save it as PNG first")

    w0, h0 = im.size
    target = 2 * width
    resized = w0 > target * RESIZE_SLACK
    if resized:
        im = im.resize((target, max(1, round(h0 * target / w0))), Image.Resampling.LANCZOS)

    if fmt == "PNG":
        encoded, how = encode_png(im, data, palette)
        if not resized and not palette and not rotated:
            stripped = strip_png(data)
            if len(stripped) <= len(encoded):
                encoded, how = stripped, "lossless, metadata removed"
    else:
        encoded, how = encode_jpeg(im, icc), f"quality {JPEG_QUALITY}"
        if not resized and not rotated and src_format == "JPEG":
            stripped = strip_jpeg(data)
            if not same_pixels(Image.open(io.BytesIO(stripped)), Image.open(io.BytesIO(data))):
                raise SystemExit(f"{src}: metadata strip changed pixels; refusing")
            if len(encoded) > (1 - JPEG_MIN_SAVING) * len(stripped):
                encoded, how = stripped, "pixels untouched, metadata removed"

    check = Image.open(io.BytesIO(encoded))
    check.load()
    if check.getexif() or any(k in check.info for k in ("exif", "xmp", "XML:com.adobe.xmp", "photoshop", "comment")):
        raise SystemExit(f"{src}: metadata survived; refusing to write")
    if how.startswith("lossless") and not same_pixels(check, im):
        raise SystemExit(f"{src}: lossless PNG encode changed pixels; refusing to write")

    tmp = out + ".tmp"
    with open(tmp, "wb") as f:
        f.write(encoded)
    os.replace(tmp, out)

    w, h = check.size
    shown = min(width, w)
    rel = os.path.relpath(os.path.abspath(out), REPO)
    print(f"{rel}: {w0}x{h0} -> {w}x{h}, {len(data):,} -> {len(encoded):,} bytes ({how})")
    return f'<img src="{rel}" width="{shown}" height="{round(h * shown / w)}" alt="">'


def default_out(src, fmt):
    stem = os.path.splitext(os.path.basename(src))[0]
    name = re.sub(r"[^a-z0-9_-]+", "-", stem.lower()).strip("-") or "image"
    return os.path.join(REPO, "images", name + (".png" if fmt == "PNG" else ".jpg"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("src", nargs="+")
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="CSS display width in px (default %(default)s)")
    ap.add_argument("--palette", action="store_true", help="reduce a PNG to 256 colours (lossy; for icons)")
    where = ap.add_mutually_exclusive_group()
    where.add_argument("--out", help="output path (one source only)")
    where.add_argument("--in-place", action="store_true", help="overwrite each source at the same path")
    ap.add_argument("--force", action="store_true", help="overwrite an existing output file")
    args = ap.parse_args()
    if args.out and len(args.src) > 1:
        ap.error("--out takes a single source")

    for src in args.src:
        if args.in_place:
            out = src
        else:
            out = args.out or default_out(src, "PNG" if Image.open(src).format == "PNG" else "JPEG")
            if os.path.exists(out) and not args.force:
                raise SystemExit(f"{out} exists; pass --force to overwrite or --out to pick a name")
        tag = process(src, out, args.width, args.palette)
        if not args.in_place:
            print(tag)


if __name__ == "__main__":
    main()
