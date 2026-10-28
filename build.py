#!/usr/bin/env python3
"""Build NEO: content/<slug>.md and content/log/YYYY-MM-DD.md -> site/<slug>.html.

    python3 build.py               writes site/ and exits 1 on errors
    python3 build.py --out DIR     builds elsewhere (an existing DIR must be named "site")

The site model is the one in AGENTS.md: `site.pages[slug]` is a `Page`, `site.wanted[slug]`
lists the pages linking to a target that has no page, and `BASE_URL` is the public origin.

If `extras.py` sits next to `content/`, it is imported and may define two hooks:
  extend(site)       after content is loaded, before links are resolved and pages rendered;
                     it may add `Page`s to `site.pages` or edit their `body_md`.
  build(site, out)   after the pages are written; use `site.render(page)` for a full HTML
                     page and `site.write(path, data)` to add files.
"""
import argparse
import dataclasses
import datetime
import html
import importlib.util
import os
import posixpath
import re
import shutil
import string
import subprocess
import sys
import time
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

BASE_URL = "https://ns123abc.github.io"
SITE_NAME = "NEO"
ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = ("main.css", "fonts", "images")
FIELDS = ("title", "parent", "created", "date", "date_approx", "summary", "aliases")

SLUG = re.compile(r"[a-z0-9_-]+")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
YEAR = re.compile(r"\d{4}")
WIKILINK = re.compile(r"\[\[([^\[\]\n|]*?)(?:\\?\|([^\[\]\n]*))?\]\]")
FRONT_LINE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*):(.*)")


class BuildError(Exception):
    pass


@dataclasses.dataclass
class Page:
    slug: str
    title: str
    parent: str | None = None
    kind: str = "page"  # page, log or list
    created: str | None = None  # YYYY-MM-DD strings throughout
    date: str | None = None
    date_approx: bool = False
    updated: str | None = None
    summary: str | None = None
    body_md: str = ""
    html: str = ""  # rendered body only; Site.render wraps it in the template
    links: list = dataclasses.field(default_factory=list)
    backlinks: list = dataclasses.field(default_factory=list)
    path: str | None = None  # source file relative to the root; None for generated pages

    def __getitem__(self, key):
        return getattr(self, key)


def _esc(text):
    return html.escape(text, quote=True)


@dataclasses.dataclass
class Site:
    root: str
    pages: dict = dataclasses.field(default_factory=dict)
    wanted: dict = dataclasses.field(default_factory=dict)
    errors: list = dataclasses.field(default_factory=list)
    warnings: list = dataclasses.field(default_factory=list)
    template: string.Template | None = None
    out: str | None = None
    written: set = dataclasses.field(default_factory=set)
    refs: list = dataclasses.field(default_factory=list)  # (source, url) for non-wiki links

    def error(self, where, message):
        self.errors.append(f"{where}: {message}")

    def warn(self, where, message):
        self.warnings.append(f"{where}: {message}")

    def nav(self, page):
        """One <ul> per level from the top down to `page`, then one for its children."""
        chain, cur = [], page
        while cur is not None and cur.slug not in chain:
            chain.append(cur.slug)
            cur = self.pages.get(cur.parent) if cur.parent else None
        chain.reverse()
        children = {}
        for p in self.pages.values():
            if p.kind != "log" and p.slug != "index":
                children.setdefault(p.parent, []).append(p)
        html_cols = []
        for col in [children.get(None, [])] + [children.get(s, []) for s in chain]:
            items = []
            for p in sorted(col, key=lambda p: p.slug):
                if p.slug == page.slug:
                    a = f'<a href="{p.slug}.html" aria-current="page">'
                elif p.slug in chain:
                    a = f'<a class="parent" href="{p.slug}.html">'
                else:
                    a = f'<a href="{p.slug}.html">'
                items.append(f"<li>{a}{_esc(p.title)}</a></li>")
            if items:
                html_cols.append("<ul>" + "".join(items) + "</ul>")
        return "".join(html_cols)

    def running(self, page):
        """Parent and created date under the title. Absent when created was not set."""
        if not page.created:
            return ""
        parts = []
        parent = self.pages.get(page.parent) if page.parent else None
        if parent is not None:
            parts.append(_esc(parent.title))
        elif page.parent:
            parts.append(_esc(page.parent))
        parts.append(f'<time datetime="{_esc(page.created)}">{_esc(page.created)}</time>')
        return f'<p class="running">{" · ".join(parts)}</p>\n'

    def render(self, page):
        incoming = " ".join(f'<a href="{b}.html">{_esc(self.pages[b].title)}</a>'
                            for b in page.backlinks if b in self.pages)
        return self.template.substitute(
            doc_title=_esc(f"{page.title} — {SITE_NAME}"),
            description=f'\n<meta name="description" content="{_esc(page.summary)}">' if page.summary else "",
            nav=self.nav(page),
            kind=_esc(page.kind),
            title=_esc(page.title),
            running=self.running(page),
            body=page.html,
            incoming=f'<section class="incoming"><b>incoming</b>: {incoming}</section>' if incoming else "",
        )

    def _claim(self, relpath):
        relpath = posixpath.normpath(relpath)
        if relpath in self.written:
            raise BuildError(f"{relpath} is written twice")
        self.written.add(relpath)
        dest = os.path.join(self.out, relpath)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        return dest

    def write(self, relpath, data):
        with open(self._claim(relpath), "wb") as fh:
            fh.write(data.encode("utf-8") if isinstance(data, str) else data)

    def copy(self, relpath):
        shutil.copyfile(os.path.join(self.root, relpath), self._claim(relpath))


def _wikilink(state, silent):
    if not state.src.startswith("[[", state.pos):
        return False
    m = WIKILINK.match(state.src, state.pos)
    if not m:
        return False
    target, text = m.group(1).strip(), m.group(2)
    text = target if text is None else text.strip()
    if not SLUG.fullmatch(target) or not text:
        if not silent:
            state.env.setdefault("bad", set()).add(m.group(0))
        return False
    if not silent:
        tok = state.push("link_open", "a", 1)
        if target in state.env.get("known", ()):
            tok.attrs = {"href": f"{target}.html"}
        else:
            tok.attrs = {"class": "wanted", "href": f"wanted.html#{target}"}
        tok.meta = {"wikilink": target}
        state.push("text", "", 0).content = text
        state.push("link_close", "a", -1)
    state.pos = m.end()
    return True


MD = MarkdownIt("commonmark", {"xhtmlOut": False}).enable(["table", "strikethrough"])
MD.inline.ruler.before("link", "wikilink", _wikilink)


class _Refs(HTMLParser):
    """href/src values, and <img> tags without alt text, in a chunk of raw HTML."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.refs, self.no_alt = [], []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.refs += [attrs[k] or "" for k in ("href", "src") if k in attrs]
        if tag == "img" and not (attrs.get("alt") or "").strip():
            self.no_alt.append(attrs.get("src") or "")

    handle_startendtag = handle_starttag


def _walk(tokens):
    for tok in tokens:
        yield tok
        if tok.children:
            yield from _walk(tok.children)


def _is_day(value):
    if not DAY.fullmatch(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_list(tokens):
    return any(a.type == "heading_open" and a.tag == "h2" and YEAR.fullmatch(b.content.strip())
               for a, b in zip(tokens, tokens[1:]))


def parse_front_matter(text):
    """Split a file into (meta, body, problems). Front matter is flat `key: value` lines."""
    lines = text.lstrip("\ufeff").replace("\r\n", "\n").split("\n")
    if lines[0].rstrip() != "---":
        return {}, "\n".join(lines), []
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() == "---"), None)
    if end is None:
        return {}, "\n".join(lines), ["front matter has no closing ---"]
    meta, problems = {}, []
    for n, line in enumerate(lines[1:end], 2):
        if not line.strip():
            continue
        m = FRONT_LINE.fullmatch(line.rstrip())
        if not m:
            problems.append(f"line {n}: not a flat 'key: value' line: {line.strip()!r}")
            continue
        key, value = m.group(1), m.group(2).strip()
        if key not in FIELDS:
            problems.append(f"line {n}: unknown key {key!r} (allowed: {', '.join(FIELDS)})")
        elif key in meta:
            problems.append(f"line {n}: duplicate key {key!r}")
        else:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            meta[key] = value
    return meta, "\n".join(lines[end + 1:]), problems


def _git_updated(root, site):
    """Last-edited date per file, from a single `git log` over content/."""
    def git(*args):
        return subprocess.run(["git", "-C", root, *args], capture_output=True, check=True,
                              text=True, encoding="utf-8").stdout
    try:
        if git("rev-parse", "--is-shallow-repository").strip() == "true":
            site.warn("git", "shallow clone, so 'updated' is left empty (clone with fetch-depth: 0)")
            return {}
        log = git("-c", "core.quotepath=off", "log", "--format=%x00%as", "--name-only",
                  "--relative", "--", "content")
    except (OSError, subprocess.CalledProcessError):
        return {}
    dates, day = {}, None
    for line in log.splitlines():
        if line.startswith("\x00"):
            day = line[1:]
        elif line:
            dates.setdefault(line, day)
    return dates


def load(root):
    site = Site(root=root)
    try:
        with open(os.path.join(root, "templates", "page.html"), encoding="utf-8") as fh:
            site.template = string.Template(fh.read())
    except FileNotFoundError:
        site.error("templates/page.html", "missing")

    sources = []
    for sub, kind in (("content", "page"), ("content/log", "log")):
        folder = os.path.join(root, sub)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            rel = f"{sub}/{name}"
            if name.startswith("."):
                continue
            if os.path.isdir(os.path.join(folder, name)):
                if rel != "content/log":
                    site.error(rel, "unexpected directory (only content/log/ is allowed)")
            elif name.endswith(".md"):
                sources.append((rel, kind, name[:-3]))
            else:
                site.error(rel, "unexpected file (content/ holds only .md files)")

    by_slug = {}
    for rel, _, stem in sources:
        by_slug.setdefault(stem.lower(), []).append(rel)
    for paths in by_slug.values():
        if len(paths) > 1:
            site.error(paths[0], f"same slug as {', '.join(paths[1:])}: slugs must be unique "
                                 "ignoring case (macOS treats About.md and about.md as one file)")

    for rel, kind, stem in sources:
        if len(by_slug[stem.lower()]) > 1:
            continue
        if kind == "page" and not SLUG.fullmatch(stem):
            site.error(rel, f"bad slug {stem!r}: use only lowercase a-z, 0-9, _ and -")
            continue
        if kind == "log" and not _is_day(stem):
            site.error(rel, "log entries are named YYYY-MM-DD.md")
            continue
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            meta, body, problems = parse_front_matter(fh.read())
        for problem in problems:
            site.error(rel, problem)

        title = meta.get("title", "")
        if not title:
            if kind == "page":
                site.error(rel, "missing title")
            title = stem
        created = meta.get("created") or None
        if created and not _is_day(created):
            site.error(rel, f"created must be a YYYY-MM-DD date, got {created!r}")
        date = meta.get("date") or None
        if kind == "log":
            if date and date != stem:
                site.error(rel, f"date {date!r} doesn't match the file name, which is the entry's date")
            date = stem
        elif date:
            site.error(rel, "date is for log entries only")
        approx = meta.get("date_approx") or "false"
        if approx not in ("true", "false"):
            site.error(rel, f"date_approx must be true or false, got {approx!r}")
        if kind == "page" and _is_list(MD.parse(body, {})):
            kind = "list"
        site.pages[stem] = Page(slug=stem, title=title, parent=meta.get("parent") or None, kind=kind,
                                created=created, date=date, date_approx=approx == "true",
                                summary=meta.get("summary") or None, body_md=body, path=rel)

    updated = _git_updated(root, site)
    for page in site.pages.values():
        page.updated = updated.get(page.path)
    return site


def _scan(site, where, tokens):
    """Collect non-wiki links for the post-write check, and flag content problems."""
    prev, warned_h1 = None, False
    for tok in _walk(tokens):
        if tok.type == "link_open" and "wikilink" not in tok.meta:
            site.refs.append((where, tok.attrGet("href") or ""))
        elif tok.type == "image":
            src = tok.attrGet("src") or ""
            site.refs.append((where, src))
            if not tok.content.strip():
                site.warn(where, f"image without alt text: {src}")
        elif tok.type in ("html_block", "html_inline"):
            raw = _Refs(tok.content)
            site.refs += [(where, url) for url in raw.refs]
            for src in raw.no_alt:
                site.warn(where, f"image without alt text: {src}")
        elif tok.type == "heading_open" and tok.tag == "h1" and not warned_h1:
            warned_h1 = True
            site.warn(where, "has its own '# ' heading; the template already adds <h1> from the title")
        elif (tok.type == "inline" and prev is not None and prev.type in ("td_open", "th_open")
              and tok.content.count("[[") != tok.content.count("]]")):
            site.error(where, f"wikilink split across table cells in {tok.content!r}; "
                              "inside tables write [[slug\\|text]]")
        prev = tok


def process(site):
    site.pages = {slug: site.pages[slug] for slug in sorted(site.pages)}
    pages = site.pages
    where = {slug: p.path or f"extras.py ({slug})" for slug, p in pages.items()}

    for slug, page in pages.items():
        if page.slug != slug or not SLUG.fullmatch(slug):
            site.error(where[slug], f"bad slug {page.slug!r}")
        if page.parent is None:
            continue
        if page.parent == "index":
            site.error(where[slug], "top-level pages have no parent; remove 'parent: index'")
        elif page.parent not in pages:
            site.error(where[slug], f"parent {page.parent!r} has no page")
    if "index" not in pages:
        site.error("content/index.md", "missing (the logo links to index.html)")

    cycles = set()
    for slug in pages:
        trail, cur = [], slug
        while cur in pages and cur not in trail:
            trail.append(cur)
            cur = pages[cur].parent
        if cur in trail:
            cycle = trail[trail.index(cur):]
            if frozenset(cycle) not in cycles:
                cycles.add(frozenset(cycle))
                site.error(where[min(cycle)], f"parent cycle: {' -> '.join(cycle + [cur])}")

    known = frozenset(pages)
    for slug, page in pages.items():
        env = {"known": known}
        tokens = MD.parse(page.body_md, env)
        for raw in sorted(env.get("bad", ())):
            site.error(where[slug], f"bad wikilink {raw}: the target must be a slug "
                                    "([a-z0-9_-]) and the text can't be empty")
        page.links = sorted({tok.meta["wikilink"] for tok in _walk(tokens) if "wikilink" in tok.meta})
        page.html = MD.renderer.render(tokens, MD.options, env)
        _scan(site, where[slug], tokens)

    wanted = {}
    for page in pages.values():
        page.backlinks = []
    for page in pages.values():
        for target in page.links:
            if target not in pages:
                wanted.setdefault(target, []).append(page.slug)
            elif target != page.slug:
                pages[target].backlinks.append(page.slug)
    site.wanted = dict(sorted(wanted.items()))


def _reset(root, out):
    root, real_out = os.path.realpath(root), os.path.realpath(out)
    if os.path.commonpath([root, real_out]) == real_out:
        raise BuildError(f"refusing to build into {out}: it contains the source")
    if os.path.exists(out):
        if os.path.basename(real_out) != "site":
            raise BuildError(f"refusing to clear {out}: an existing output directory must be named 'site'")
        shutil.rmtree(out)
    os.makedirs(out)


def write(site, out):
    _reset(site.root, out)
    site.out, site.written = out, set()
    for name in STATIC:
        src = os.path.join(site.root, name)
        if os.path.isfile(src):
            site.copy(name)
        elif os.path.isdir(src):
            for dirpath, dirnames, filenames in os.walk(src):
                dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
                for filename in sorted(f for f in filenames if not f.startswith(".")):
                    site.copy(os.path.relpath(os.path.join(dirpath, filename), site.root))
    for page in site.pages.values():
        site.write(f"{page.slug}.html", site.render(page))


def _local(url):
    """The site-relative file an internal URL points at; '' if unusable; None if external."""
    if url.startswith("#"):
        return None
    parts = urlsplit(url)
    if parts.scheme or parts.netloc:
        return None
    path = posixpath.normpath(unquote(parts.path).lstrip("/")) if parts.path else ""
    if path in ("", ".", "..") or path.startswith("../"):
        return ""
    return path


def check_refs(site):
    """Every non-wiki internal link and image, in content and template, must exist in site/."""
    refs = [("templates/page.html", url) for url in _Refs(site.template.template).refs] + site.refs
    seen = set()
    for where, url in refs:
        path = _local(url)
        if path is None or (where, url) in seen:
            continue
        seen.add((where, url))
        if not path or not os.path.isfile(os.path.join(site.out, path)):
            stem = posixpath.splitext(posixpath.basename(path))[0].lower()
            hint = f" (did you mean [[{stem}]]?)" if stem in site.pages and url.endswith(".html") else ""
            site.error(where, f"broken link {url!r}{hint}")


def _load_extras(root):
    path = os.path.join(root, "extras.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("extras", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(root=ROOT, out=None):
    """Build `root`/content into `out` (default `root`/site). Returns the Site; check `.errors`."""
    root = os.path.abspath(root)
    out = os.path.abspath(out or os.path.join(root, "site"))
    if not os.path.isdir(os.path.join(root, "content")):
        site = Site(root=root)
        site.warn("content/", "missing, so there is nothing to build and site/ is left alone")
        return site
    site = load(root)
    if site.errors:
        return site
    extras = _load_extras(root)
    if hasattr(extras, "extend"):
        extras.extend(site)
    process(site)
    if site.errors:
        return site
    try:
        write(site, out)
        if hasattr(extras, "build"):
            extras.build(site, out)
    except BuildError as exc:
        site.error("build", str(exc))
        return site
    check_refs(site)
    return site


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build site/ from content/.")
    parser.add_argument("--root", default=ROOT, help="repository root (default: this file's folder)")
    parser.add_argument("--out", help="output directory (default: ROOT/site)")
    args = parser.parse_args(argv)
    start = time.perf_counter()
    site = build(args.root, args.out)
    for message in site.warnings:
        print(f"warning: {message}", file=sys.stderr)
    for message in site.errors:
        print(f"error: {message}", file=sys.stderr)
    if site.errors:
        print(f"build failed with {len(site.errors)} error(s)", file=sys.stderr)
        return 1
    if not site.pages:
        return 0
    kinds = [p.kind for p in site.pages.values()]
    print(f"built {kinds.count('page')} pages, {kinds.count('list')} lists, {kinds.count('log')} log "
          f"entries, {len(site.wanted)} wanted, in {(time.perf_counter() - start) * 1000:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.modules.setdefault("build", sys.modules[__name__])
    sys.exit(main())
