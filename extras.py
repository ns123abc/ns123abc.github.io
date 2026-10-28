"""Generated pages and files for build.py.

build.py imports this file and calls two hooks:
  extend(site)       before links are resolved: adds one page per year and appends the newest
                     entries to the home page, so [[2022]] is a real link rather than a wanted one.
  build(site, out)   after the pages are written: wanted.html, 404.html, feed.xml, sitemap.xml,
                     robots.txt, corpus.jsonl, llms.txt and llms-full.txt.

Generated pages carry only structure and the user's existing words. Feed ids are tag: URIs, so
they survive a change of BASE_URL; every other absolute URL is built from BASE_URL.

A year page shows that year's log entries in full, oldest first, then each list page's `## YYYY`
section. It links to the entries and lists themselves; links inside the embedded text are kept as
rendered HTML, so they don't count twice in backlinks or the wanted page.

corpus.jsonl has one JSON record per line, for each page and log entry and for each list item
(`- **Title**: Creator. Year`). An item's `year` is its `## YYYY` heading and `made` is the year
after the creator. `text` is the Markdown body exactly as written, without front matter.
"""
import html
import json
import os
import re
import unicodedata
from urllib.parse import urljoin, urlsplit

import build as neo

FEED = "feed.xml"
FEED_SIZE = 20
RECENT = 10
YEAR_PARENT = "now"  # year pages sit under this page in the nav, or at the top level without it
TAG = "tag:ns123abc.github.io,2026:"
AUTHOR = "Nikhil Sareen"
RESERVED = ("404", "wanted")

ITEM = re.compile(r"\*\*\s*(.+?)\s*\*\*\s*:\s*(.*)", re.S)
MADE = re.compile(r"(.*?)\s*\.\s*(\d{4})")
START_TAG = re.compile(r"<[A-Za-z][^>]*>")
URL_ATTR = re.compile(r"""(\s(?:href|src)=)(["'])(.*?)\2""", re.S)
NOT_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _esc(text):
    return html.escape(text, quote=True)


def _xml(text):
    return html.escape(NOT_XML.sub("", text), quote=False)


def _md(text):
    """Plain text as Markdown that renders to exactly that text."""
    return re.sub(r"([!-/:-@\[-`{-~])", r"\\\1", text)


def _key(text):
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def _url(base, slug):
    return f"{base}/" if slug == "index" else f"{base}/{slug}.html"


def _when(page):
    """The day a page was written: a log entry's date, or a page's `created`."""
    return page.date if page.kind == "log" else page.created


def _day(page):
    when = _when(page)
    return f"~{when}" if when and page.date_approx else when


def _authored(site):
    """Pages from content/: home, the other pages by slug, then log entries by date."""
    pages = [p for p in site.pages.values() if p.path]
    rest = sorted((p for p in pages if p.kind != "log"), key=lambda p: (p.slug != "index", p.slug))
    return rest + sorted((p for p in pages if p.kind == "log"), key=lambda p: p.slug)


def _recent(site, n):
    """The `n` newest log entries and created pages, newest first. Home is never listed."""
    dated = [p for p in _authored(site) if p.slug != "index" and _when(p)]
    return sorted(sorted(dated, key=lambda p: p.slug), key=_when, reverse=True)[:n]


def _sections(page):
    """(year, markdown) for each top-level `## YYYY` section of a page."""
    lines = page.body_md.split("\n")
    tokens = neo.MD.parse(page.body_md, {})
    heads = [(a, b.content.strip()) for a, b in zip(tokens, tokens[1:])
             if a.type == "heading_open" and a.level == 0 and a.tag in ("h1", "h2")]
    for i, (tok, text) in enumerate(heads):
        if tok.tag == "h2" and neo.YEAR.fullmatch(text):
            end = heads[i + 1][0].map[0] if i + 1 < len(heads) else len(lines)
            yield text, "\n".join(lines[tok.map[1]:end])


def _years(site):
    """{year: (log entries, [(list page, section markdown)])}, sorted by year."""
    years = {}
    for page in _authored(site):
        if page.kind == "log":
            years.setdefault(page.date[:4], ([], []))[0].append(page)
        elif page.kind == "list":
            for year, markdown in _sections(page):
                years.setdefault(year, ([], []))[1].append((page, markdown))
    return dict(sorted(years.items()))


def _embed(markdown, known):
    """Rendered Markdown as one raw HTML block, so its links aren't parsed again."""
    rendered = neo.MD.render(markdown, {"known": known})
    if not rendered.strip():
        return ""
    # A raw HTML block ends at the first blank line; &#10; keeps blank lines inside <pre>.
    return "<div>\n" + re.sub(r"\n(?=[ \t]*\n)", "&#10;", rendered) + "</div>"


def _append(page, markdown):
    page.body_md = page.body_md.rstrip("\n") + "\n\n" + markdown


def _year_md(entries, sections, known):
    parts = []
    for entry in entries:
        head = f"## [[{entry.slug}|{_day(entry)}]]"
        parts += [head if entry.title == entry.date else f"{head} {_md(entry.title)}",
                  _embed(entry.body_md, known)]
    for page, markdown in sections:
        linkable = not re.search(r"[\[\]\n]", page.title)
        parts += [f"## [[{page.slug}|{page.title}]]" if linkable else f"## [[{page.slug}]]",
                  _embed(markdown, known)]
    return "\n\n".join(part for part in parts if part) + "\n"


def _recent_html(pages):
    items = []
    for page in pages:
        day = f'<time datetime="{_when(page)}">{_day(page)}</time>'
        if page.title == _when(page):
            items.append(f'<li><a href="{page.slug}.html">{day}</a></li>\n')
        else:
            items.append(f'<li>{day} <a href="{page.slug}.html">{_esc(page.title)}</a></li>\n')
    return "<ul>\n" + "".join(items) + "</ul>\n"


def extend(site):
    for slug in RESERVED:
        if slug in site.pages:
            site.error(site.pages[slug].path or slug, f"{slug}.html is generated by extras.py; use another slug")
    years = _years(site)
    known = frozenset(site.pages) | frozenset(years)
    for year, (entries, sections) in years.items():
        body = _year_md(entries, sections, known)
        if year in site.pages:
            _append(site.pages[year], body)
        else:
            parent = YEAR_PARENT if YEAR_PARENT in site.pages else None
            site.pages[year] = neo.Page(slug=year, title=year, parent=parent, body_md=body)
    recent = _recent(site, RECENT)
    if "index" in site.pages and recent:
        _append(site.pages["index"], _recent_html(recent))


def _wanted_html(site):
    rows = sorted(site.wanted.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    items = "".join(f'<li id="{slug}"><b>{slug}</b>: '
                    + " ".join(f'<a href="{s}.html">{_esc(site.pages[s].title)}</a>' for s in sources)
                    + "</li>\n" for slug, sources in rows)
    return f"<ul>\n{items}</ul>\n" if rows else ""


def _not_found(site):
    """The page GitHub Pages serves for any missing path, so its relative links need a base."""
    items = "".join(f'<li><a href="{p.slug}.html">{_esc(p.title)}</a></li>\n'
                    for p in _authored(site) if p.kind != "log")
    doc = site.render(neo.Page(slug="404", title="404", html=f"<ul>\n{items}</ul>\n" if items else ""))
    base = urlsplit(neo.BASE_URL).path.rstrip("/") + "/"
    charset = '<meta charset="utf-8">\n'
    if charset not in doc:
        raise neo.BuildError("404.html: the template has no <meta charset> line to put <base> after")
    return doc.replace(charset, f'{charset}<base href="{_esc(base)}">\n', 1)


def _absolute(fragment, url):
    """Resolve href and src values against the page's public URL, inside tags only."""
    def tag(m):
        return URL_ATTR.sub(lambda a: f"{a.group(1)}{a.group(2)}{urljoin(url, a.group(3))}{a.group(2)}",
                            m.group(0))
    return START_TAG.sub(tag, fragment)


def _stamp(day):
    return f"{day}T00:00:00Z"


def _atom(site, base):
    entries, newest = [], "1970-01-01"
    for page in _recent(site, FEED_SIZE):
        published = _when(page)
        updated = max(published, page.updated or published)
        newest = max(newest, updated)
        url = _url(base, page.slug)
        summary = f"<summary>{_xml(page.summary)}</summary>\n" if page.summary else ""
        entries.append("<entry>\n"
                       f"<title>{_xml(page.title)}</title>\n"
                       f'<link rel="alternate" type="text/html" href="{_esc(url)}"/>\n'
                       f"<id>{TAG}{page.slug}</id>\n"
                       f"<published>{_stamp(published)}</published>\n"
                       f"<updated>{_stamp(updated)}</updated>\n"
                       f"{summary}"
                       f'<content type="html">{_xml(_absolute(page.html, url))}</content>\n'
                       "</entry>\n")
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<feed xmlns="http://www.w3.org/2005/Atom">\n'
            f"<title>{_xml(neo.SITE_NAME)}</title>\n"
            f'<link rel="alternate" type="text/html" href="{_esc(base)}/"/>\n'
            f'<link rel="self" type="application/atom+xml" href="{_esc(base)}/{FEED}"/>\n'
            f"<id>{TAG}{FEED}</id>\n"
            f"<updated>{_stamp(newest)}</updated>\n"
            f"<author><name>{_xml(AUTHOR)}</name></author>\n"
            + "".join(entries) + "</feed>\n")


def _sitemap(site, base):
    sources = {year: entries + [page for page, _ in sections]
               for year, (entries, sections) in _years(site).items()}
    sources["index"] = _recent(site, RECENT)
    rows = []
    for page in sorted(site.pages.values(), key=lambda p: p.slug):
        days = [d for d in [page.updated] + [s.updated for s in sources.get(page.slug, [])] if d]
        lastmod = f"<lastmod>{max(days)}</lastmod>" if days else ""
        rows.append(f"<url><loc>{_xml(_url(base, page.slug))}</loc>{lastmod}</url>\n")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(rows) + "</urlset>\n")


def _source(site, page):
    with open(os.path.join(site.root, page.path), encoding="utf-8") as fh:
        return neo.parse_front_matter(fh.read())[1].strip("\n")


def _items(site, page, text, base):
    tokens = neo.MD.parse(text, {})
    section, ids, seen, records = None, {}, set(), []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and tok.level == 0 and tok.tag in ("h1", "h2"):
            section = tokens[i + 1].content.strip() or None
            continue
        if not (tok.type == "inline" and i >= 2 and tokens[i - 1].type == "paragraph_open"
                and tokens[i - 2].type == "list_item_open" and tokens[i - 2].level == 1
                and tokens[i - 2].markup in ("-", "*", "+")):
            continue
        m = ITEM.fullmatch(tok.content.strip())
        if not m:
            continue
        title, rest = m.group(1), m.group(2).strip()
        made = MADE.fullmatch(rest)
        creator, made = (made.group(1), made.group(2)) if made else (rest, None)
        year = section if section and neo.YEAR.fullmatch(section) else None
        dup = (section, title.lower(), creator.lower())
        if dup in seen:
            site.warn(page.path, f"{title!r} is listed twice under {section or 'the top'}")
        seen.add(dup)
        base_id = f"{page.slug}/{year or _key(section or '') or '-'}/{_key(title) or 'item'}"
        ids[base_id] = ids.get(base_id, 0) + 1
        records.append({
            "id": base_id if ids[base_id] == 1 else f"{base_id}-{ids[base_id]}",
            "kind": "item", "title": title, "url": _url(base, page.slug), "list": page.slug,
            "section": section, "year": year, "creator": creator or None, "made": made,
            "text": tok.content.strip(),
        })
    return records


def _corpus(site, base, sources):
    authored = _authored(site)
    ids = {p.slug for p in authored}
    records = []
    for page in authored:
        records.append({
            "id": page.slug, "kind": page.kind, "title": page.title, "url": _url(base, page.slug),
            "path": page.path, "parent": page.parent, "created": page.created, "date": page.date,
            "date_approx": page.date_approx, "updated": page.updated, "summary": page.summary,
            "links": page.links, "backlinks": [b for b in page.backlinks if b in ids],
            "text": sources[page.slug],
        })
        if page.kind == "list":
            records += _items(site, page, sources[page.slug], base)
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def _link_text(text):
    return re.sub(r"([\\\[\]])", r"\\\1", text)


def _llms(site, base):
    authored = _authored(site)
    index = site.pages.get("index")
    lines = [f"# {neo.SITE_NAME}", ""]
    if index is not None and index.summary:
        lines += [f"> {index.summary}", ""]

    def item(page, name):
        note = f": {page.summary}" if page.summary else ""
        return f"- [{_link_text(name)}]({_url(base, page.slug)}){note}"

    lines += ["## Pages", ""] + [item(p, p.title) for p in authored if p.kind != "log"] + [""]
    logs = [p for p in reversed(authored) if p.kind == "log"]
    if logs:
        lines += ["## Log", ""]
        lines += [item(p, _day(p) if p.title == p.date else f"{_day(p)} {p.title}") for p in logs] + [""]
    lines += ["## Files", ""] + [f"- [{name}]({base}/{name})" for name in ("llms-full.txt", "corpus.jsonl", FEED)]
    return "\n".join(lines) + "\n"


def _llms_full(site, base, sources):
    index = site.pages.get("index")
    parts = [f"# {neo.SITE_NAME}\n\n" + (f"> {index.summary}\n\n" if index is not None and index.summary else "")
             + f"{base}/\n"]
    for page in _authored(site):
        meta = [("url", _url(base, page.slug)), ("kind", page.kind), ("parent", page.parent),
                ("date", page.date), ("date_approx", "true" if page.date_approx else None),
                ("created", page.created), ("updated", page.updated), ("summary", page.summary)]
        head = f"# {page.title}\n\n" + "\n".join(f"{k}: {v}" for k, v in meta if v)
        body = sources[page.slug]
        parts.append(head + (f"\n\n{body}" if body else "") + "\n")
    return "\n".join(parts)


def build(site, out):
    base = neo.BASE_URL.rstrip("/")
    sources = {p.slug: _source(site, p) for p in _authored(site)}
    site.write("wanted.html", site.render(neo.Page(slug="wanted", title="wanted", html=_wanted_html(site))))
    site.write("404.html", _not_found(site))
    site.write(FEED, _atom(site, base))
    site.write("sitemap.xml", _sitemap(site, base))
    site.write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n")
    site.write("corpus.jsonl", _corpus(site, base, sources))
    site.write("llms.txt", _llms(site, base))
    site.write("llms-full.txt", _llms_full(site, base, sources))
