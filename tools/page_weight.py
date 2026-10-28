#!/usr/bin/env python3
"""First-visit weight of the root HTML pages, and a --check ratchet.

    python3 tools/page_weight.py
    python3 tools/page_weight.py --check

Each total is the HTML file, plus main.css, plus the two Silkscreen woff2
files, plus every local image that page references.

--check exits 1 when a root page's favicon is not images/favicon.png, or
that file is over 8 KB, or any image under images/ is over 300 KB other than
slogo7.png and slogo8.png. The icon href in templates/page.html is printed
and does not fail the check.
"""
import argparse
import os
import sys
from html.parser import HTMLParser

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAVICON = "images/favicon.png"
FAVICON_MAX = 8 * 1024
IMAGE_MAX = 300 * 1024
ALLOW_LARGE = {"slogo7.png", "slogo8.png"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif"}
CHROME_FILES = (
    "main.css",
    "fonts/silkscreen-regular.woff2",
    "fonts/silkscreen-bold.woff2",
)
CHROME_IMAGES = {
    "mlogo.jpg",
    "slogo1.png",
    "slogo2.png",
    "slogo3.png",
    "slogo4.png",
    "favicon.png",
}


class _Refs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.icons = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        self._take(tag, attrs)

    handle_startendtag = handle_starttag

    def _take(self, tag, attrs):
        values = {}
        for key, value in attrs:
            values[key.lower()] = value or ""
        if tag == "link" and "icon" in values.get("rel", "").lower().split():
            self.icons.append(values.get("href", ""))
        elif tag == "img":
            self.images.append(values.get("src", ""))


def _norm_href(href):
    href = (href or "").strip()
    if href.startswith("./"):
        href = href[2:]
    return href


def _local_path(page_dir, src):
    src = (src or "").strip()
    if not src or src.startswith(("#", "data:")):
        return None
    lower = src.lower()
    if lower.startswith(("http://", "https://", "//", "mailto:")):
        return None
    src = src.split("#", 1)[0].split("?", 1)[0]
    return os.path.normpath(os.path.join(page_dir, src))


def _filesize(path):
    return os.path.getsize(path) if os.path.isfile(path) else 0


def _pages(root):
    names = []
    for name in os.listdir(root):
        if name.endswith(".html") and os.path.isfile(os.path.join(root, name)):
            names.append(name)
    return sorted(names, key=str.lower)


def _parse(path):
    refs = _Refs()
    with open(path, encoding="utf-8", errors="replace") as fh:
        refs.feed(fh.read())
    refs.close()
    return refs


def template_icon(root):
    path = os.path.join(root, "templates", "page.html")
    if not os.path.isfile(path):
        return "(templates/page.html missing)"
    icons = _parse(path).icons
    if not icons:
        return "(none)"
    return _norm_href(icons[0])


def weights(root):
    """Return (rows, problems). A row is (filename, total bytes, why)."""
    problems = []
    rows = []
    chrome = sum(_filesize(os.path.join(root, rel)) for rel in CHROME_FILES)
    favicon_path = os.path.join(root, "images", "favicon.png")
    saw_favicon = False
    for name in _pages(root):
        path = os.path.join(root, name)
        refs = _parse(path)
        if not refs.icons:
            problems.append(f"{name}: no favicon (expected {FAVICON})")
        for href in refs.icons:
            if _norm_href(href) != FAVICON:
                problems.append(f"{name}: favicon is {href.strip() or '(empty)'}, expected {FAVICON}")
            else:
                saw_favicon = True
        seen = set()
        extra = []
        image_bytes = 0
        for src in list(refs.icons) + refs.images:
            local = _local_path(root, src)
            if local is None or local in seen or not os.path.isfile(local):
                continue
            seen.add(local)
            image_bytes += os.path.getsize(local)
            base = os.path.basename(local)
            if base not in CHROME_IMAGES:
                extra.append(base)
        why = ", ".join(extra) if extra else "text plus chrome"
        rows.append((name, os.path.getsize(path) + chrome + image_bytes, why))
    if saw_favicon or os.path.isfile(favicon_path):
        if not os.path.isfile(favicon_path):
            problems.append(f"{FAVICON} is missing")
        else:
            size = os.path.getsize(favicon_path)
            if size > FAVICON_MAX:
                problems.append(f"{FAVICON} is {size:,} bytes, over 8 KB")
    images = os.path.join(root, "images")
    if os.path.isdir(images):
        for dirpath, dirnames, filenames in os.walk(images):
            dirnames.sort()
            for name in sorted(filenames):
                if os.path.splitext(name)[1].lower() not in IMAGE_EXT:
                    continue
                if name in ALLOW_LARGE:
                    continue
                path = os.path.join(dirpath, name)
                if not os.path.isfile(path):
                    continue
                size = os.path.getsize(path)
                if size > IMAGE_MAX:
                    rel = os.path.relpath(path, root).replace(os.sep, "/")
                    problems.append(f"{rel} is {size:,} bytes, over 300 KB")
    return rows, problems


def _print_report(root, rows):
    chrome_bits = []
    chrome_total = 0
    for rel in CHROME_FILES:
        size = _filesize(os.path.join(root, rel))
        chrome_total += size
        chrome_bits.append(f"{rel} {size:,}")
    print(f"template icon: {template_icon(root)}")
    print("chrome: " + " + ".join(chrome_bits) + f" = {chrome_total:,} bytes")
    print()
    name_w = max([len("page")] + [len(name) for name, _, _ in rows])
    byte_w = max([len("bytes")] + [len(f"{total:,}") for _, total, _ in rows])
    print(f"{'page':<{name_w}}  {'bytes':>{byte_w}}  why")
    for name, total, why in rows:
        print(f"{name:<{name_w}}  {total:>{byte_w},}  {why}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when the favicon or an image is over the limit",
    )
    args = parser.parse_args(argv)
    rows, problems = weights(REPO)
    _print_report(REPO, rows)
    if problems:
        print("\n".join(problems), file=sys.stderr)
    if args.check and problems:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
