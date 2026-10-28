"""Tests for extras.py. Run with `python3 -m unittest discover -s tests` (or pytest)."""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock
from urllib.parse import unquote, urlsplit

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import build  # noqa: E402

ATOM = "{http://www.w3.org/2005/Atom}"
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

BASE = {
    "content/index.md": "---\ntitle: home\n---\n\nSee [[now|recent changes]].\n",
    "content/now.md": "---\ntitle: now\ncreated: 2022-08-20\n---\n\n[[2022]] [[2019]]\n",
    "content/about.md": "---\ntitle: about\ncreated: 2022-09-01\nsummary: Who & why.\n---\n\n"
                        "About [[ghost]], [[ghost|boo]] and [[spook]].\n",
    "content/nikhil_sareen.md": "---\ntitle: Nikhil Sareen\nparent: about\n---\n\nHello.\n",
    "content/reading.md": "---\ntitle: reading\nparent: about\ncreated: 2022-08-29\n---\n\n"
                          "## Incoming\n\n- **SICP**: Abelson and Sussman\n\n"
                          "## 2022\n\n- **Crime and Punishment**: Fyodor Dostoevsky\n- ** Life 3.0 ** : Max Tegmark. 2017\n\n"
                          "### notes\n\nsub\n\n"
                          "## 2021\n\n- **Genius Makers**: Cade Metz\n",
    "content/log/2022-08-27.md": "---\ndate_approx: true\n---\n\nRead [[reading]] and [[ghost]].\n",
    "content/log/2022-09-02.md": "---\ntitle: Tiny bots\n---\n\nA dream.\n",
    "main.css": "body { color: black }\n",
    "images/mlogo.jpg": b"\xff\xd8logo",
    "images/slogo1.png": b"\x89PNG1",
    "images/slogo2.png": b"\x89PNG2",
    "images/slogo3.png": b"\x89PNG3",
    "images/slogo4.png": b"\x89PNG4",
    "images/favicon.png": b"\x89PNGf",
}


def _put(root, rel, data):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data.encode("utf-8") if isinstance(data, str) else data)


def snapshot(folder):
    files = {}
    for dirpath, _, filenames in os.walk(folder):
        for name in filenames:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as fh:
                files[os.path.relpath(path, folder)] = fh.read()
    return files


def main_of(page):
    return page[page.index("<main>"):page.index("</main>")]


class ExtrasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = os.path.join(self.tmp, "repo")
        self.out = os.path.join(self.tmp, "out", "site")

    def make(self, files=None, drop=()):
        merged = {k: v for k, v in BASE.items() if k not in drop}
        merged.update(files or {})
        for rel, data in merged.items():
            if data is not None:
                _put(self.root, rel, data)
        for rel in ("templates/page.html", "extras.py"):
            os.makedirs(os.path.dirname(os.path.join(self.root, rel)), exist_ok=True)
            shutil.copyfile(os.path.join(REPO, rel), os.path.join(self.root, rel))

    def build(self, files=None, drop=(), ok=True, updated=None):
        self.make(files, drop)
        with mock.patch.object(build, "_git_updated", return_value=updated or {}):
            site = build.build(self.root, self.out)
        if ok:
            self.assertEqual(site.errors, [])
        return site

    def read(self, name):
        with open(os.path.join(self.out, name), encoding="utf-8") as fh:
            return fh.read()

    def corpus(self):
        return [json.loads(line) for line in self.read("corpus.jsonl").splitlines()]


class YearTest(ExtrasTest):
    def test_year_links_resolve_and_only_years_with_writing_exist(self):
        site = self.build()
        self.assertIn('<a href="2022.html">2022</a>', self.read("now.html"))
        self.assertEqual(sorted(s for s in site.pages if s.isdigit()), ["2021", "2022"])
        self.assertIn("2019", site.wanted)
        self.assertNotIn("2022", site.wanted)

    def test_year_page_embeds_entries_then_list_sections(self):
        site = self.build()
        body = main_of(self.read("2022.html"))
        first, second = site.pages["2022-08-27"], site.pages["2022-09-02"]
        self.assertIn('<h2><a href="2022-08-27.html">~2022-08-27</a></h2>\n<div>\n' + first.html + "</div>", body)
        self.assertIn('<h2><a href="2022-09-02.html">2022-09-02</a> Tiny bots</h2>\n<div>\n' + second.html, body)
        self.assertIn('<h2><a href="reading.html">reading</a></h2>', body)
        order = [body.index(s) for s in ("~2022-08-27", "Tiny bots", "Crime and Punishment", "<h3>notes</h3>")]
        self.assertEqual(order, sorted(order))
        for other in ("SICP", "Genius Makers"):
            self.assertNotIn(other, body)
        self.assertIn("Genius Makers", self.read("2021.html"))

    def test_embedded_links_do_not_count_twice(self):
        site = self.build()
        self.assertEqual(site.pages["2022-08-27"].backlinks, ["2022"])
        self.assertEqual(site.pages["reading"].backlinks, ["2021", "2022", "2022-08-27"])
        self.assertEqual(site.wanted["ghost"], ["2022-08-27", "about"])
        self.assertIn('<a class="wanted" href="wanted.html#ghost">ghost</a>', self.read("2022.html"))
        self.assertIn('<section class="incoming"><b>incoming</b>: <a href="2022.html">2022</a></section>',
                      self.read("2022-08-27.html"))

    def test_year_pages_sit_under_now(self):
        site = self.build()
        self.assertEqual(site.pages["2022"].parent, "now")
        top = re.search(r'<nav class="main-nav"><ul>(.*?)</ul>', self.read("about.html")).group(1)
        self.assertNotIn("2022", top)
        self.assertIn('<ul><li><a href="2021.html">2021</a></li><li><a href="2022.html">2022</a></li></ul>',
                      self.read("now.html"))
        self.assertIn('<a href="2022.html" aria-current="page">2022</a>', self.read("2022.html"))

    def test_without_now_year_pages_are_top_level(self):
        site = self.build({"content/index.md": "---\ntitle: home\n---\n\nhi\n"}, drop=["content/now.md"])
        self.assertIsNone(site.pages["2022"].parent)

    def test_a_written_year_page_gets_the_generated_part_appended(self):
        site = self.build({"content/2022.md": "---\ntitle: The year\n---\n\nMy own words.\n"})
        self.assertEqual(site.pages["2022"].path, "content/2022.md")
        body = main_of(self.read("2022.html"))
        self.assertTrue(body.startswith("<main><h1>The year</h1>\n<p>My own words.</p>\n<h2>"))
        self.assertIn("Tiny bots", body)

    def test_blank_lines_in_code_survive(self):
        code = "```\na\n\n  \nb\n```\n\n    x\n\n    y\n"
        site = self.build({"content/log/2022-08-27.md": code})
        pres = lambda text: [html.unescape(p) for p in re.findall(r"<pre>(.*?)</pre>", text, re.S)]
        self.assertEqual(pres(self.read("2022.html")), pres(site.pages["2022-08-27"].html))
        self.assertEqual(pres(self.read("2022.html")), ["<code>a\n\n  \nb\n</code>", "<code>x\n\ny\n</code>"])

    def test_entry_titles_are_shown_literally(self):
        site = self.build({"content/log/2022-09-02.md": "---\ntitle: *a* [[x]] <b>&\n---\n\nhi\n"})
        self.assertNotIn("x", site.wanted)
        self.assertIn('<h2><a href="2022-09-02.html">2022-09-02</a> *a* [[x]] &lt;b&gt;&amp;</h2>',
                      self.read("2022.html"))

    def test_reserved_slugs_fail(self):
        site = self.build({"content/wanted.md": "---\ntitle: w\n---\n", "content/404.md": "---\ntitle: x\n---\n"},
                          ok=False)
        self.assertIn("content/wanted.md: wanted.html is generated by extras.py; use another slug", site.errors)
        self.assertIn("content/404.md: 404.html is generated by extras.py; use another slug", site.errors)


class HomeTest(ExtrasTest):
    def test_recent_entries_follow_the_users_words(self):
        site = self.build()
        body = main_of(self.read("index.html"))
        self.assertEqual(body, '<main><h1>home</h1>\n<p>See <a href="now.html">recent changes</a>.</p>\n<ul>\n'
                               '<li><time datetime="2022-09-02">2022-09-02</time> <a href="2022-09-02.html">Tiny bots</a></li>\n'
                               '<li><time datetime="2022-09-01">2022-09-01</time> <a href="about.html">about</a></li>\n'
                               '<li><time datetime="2022-08-29">2022-08-29</time> <a href="reading.html">reading</a></li>\n'
                               '<li><a href="2022-08-27.html"><time datetime="2022-08-27">~2022-08-27</time></a></li>\n'
                               '<li><time datetime="2022-08-20">2022-08-20</time> <a href="now.html">now</a></li>\n'
                               "</ul>\n")
        self.assertEqual(site.pages["index"].links, ["now"])
        self.assertNotIn("index", site.pages["2022-09-02"].backlinks)

    def test_recent_entries_are_capped_and_ties_go_by_slug(self):
        logs = {f"content/log/2023-01-{d:02}.md": "x\n" for d in range(1, 13)}
        pages = {f"content/p{i}.md": f"---\ntitle: p{i}\ncreated: 2023-01-12\n---\n" for i in (2, 1)}
        self.build({**logs, **pages})
        links = re.findall(r'<li>.*?href="([^"]+)"', main_of(self.read("index.html")))
        self.assertEqual(links, ["2023-01-12.html", "p1.html", "p2.html"] + [f"2023-01-{d:02}.html" for d in range(11, 4, -1)])

    def test_a_list_ending_the_home_page_stays_tight(self):
        self.build({"content/index.md": "---\ntitle: home\n---\n\n- a\n- b\n"})
        self.assertIn("<ul>\n<li>a</li>\n<li>b</li>\n</ul>\n<ul>\n<li><time", self.read("index.html"))


class WantedTest(ExtrasTest):
    def test_wanted_page_lists_targets_by_reference_count(self):
        self.build()
        page = self.read("wanted.html")
        self.assertIn("<title>wanted — NEO</title>", page)
        self.assertIn('<main><h1>wanted</h1>\n<ul>\n'
                      '<li id="ghost"><b>ghost</b>: <a href="2022-08-27.html">2022-08-27</a> <a href="about.html">about</a></li>\n'
                      '<li id="2019"><b>2019</b>: <a href="now.html">now</a></li>\n'
                      '<li id="spook"><b>spook</b>: <a href="about.html">about</a></li>\n'
                      "</ul>\n</main>", page)
        self.assertNotIn("aria-current", page)

    def test_every_wanted_link_has_an_anchor(self):
        self.build()
        ids = set(re.findall(r'<li id="([^"]+)"', self.read("wanted.html")))
        for name in os.listdir(self.out):
            if name.endswith(".html"):
                for slug in re.findall(r'href="wanted\.html#([^"]+)"', self.read(name)):
                    self.assertIn(slug, ids, name)

    def test_no_wanted_targets(self):
        self.build({"content/about.md": "---\ntitle: about\n---\n\nx\n",
                    "content/now.md": "---\ntitle: now\n---\n\nx\n",
                    "content/log/2022-08-27.md": "x\n"})
        self.assertIn("<main><h1>wanted</h1>\n</main>", self.read("wanted.html"))


class NotFoundTest(ExtrasTest):
    def test_404_has_a_base_and_lists_the_pages(self):
        self.build()
        page = self.read("404.html")
        self.assertIn('<head>\n<meta charset="utf-8">\n<base href="/">\n<meta name="viewport"', page)
        self.assertIn("<title>404 — NEO</title>", page)
        self.assertIn('<main><h1>404</h1>\n<ul>\n<li><a href="index.html">home</a></li>\n'
                      '<li><a href="about.html">about</a></li>\n<li><a href="nikhil_sareen.html">Nikhil Sareen</a></li>\n'
                      '<li><a href="now.html">now</a></li>\n'
                      '<li><a href="reading.html">reading</a></li>\n</ul>\n</main>', page)
        self.assertNotIn("ns123abc.github.io", page)

    def test_base_follows_the_path_of_base_url(self):
        with mock.patch.object(build, "BASE_URL", "https://sareen.wiki/neo/"):
            self.build()
        self.assertIn('<base href="/neo/">', self.read("404.html"))


class FeedTest(ExtrasTest):
    UPDATED = {"content/about.md": "2026-10-28", "content/log/2022-09-02.md": "2022-08-01"}

    def feed(self):
        root = ET.fromstring(self.read("feed.xml").encode("utf-8"))
        return root, root.findall(f"{ATOM}entry")

    def test_feed_is_atom_newest_first(self):
        self.build(updated=self.UPDATED)
        root, entries = self.feed()
        self.assertEqual(root.findtext(f"{ATOM}id"), "tag:ns123abc.github.io,2026:feed.xml")
        self.assertEqual(root.findtext(f"{ATOM}updated"), "2026-10-28T00:00:00Z")
        self.assertEqual(root.findtext(f"{ATOM}author/{ATOM}name"), "Nikhil Sareen")
        self.assertEqual([e.findtext(f"{ATOM}id") for e in entries],
                         [f"tag:ns123abc.github.io,2026:{s}" for s in ("2022-09-02", "about", "reading", "2022-08-27", "now")])
        about = entries[1]
        self.assertEqual(about.findtext(f"{ATOM}published"), "2022-09-01T00:00:00Z")
        self.assertEqual(about.findtext(f"{ATOM}updated"), "2026-10-28T00:00:00Z")
        self.assertEqual(about.findtext(f"{ATOM}summary"), "Who & why.")
        self.assertEqual(about.find(f"{ATOM}link").get("href"), "https://ns123abc.github.io/about.html")
        self.assertEqual(entries[0].findtext(f"{ATOM}updated"), "2022-09-02T00:00:00Z")
        self.assertIsNone(entries[0].find(f"{ATOM}summary"))

    def test_ids_do_not_depend_on_base_url(self):
        self.build()
        ids = [e.findtext(f"{ATOM}id") for e in self.feed()[1]]
        with mock.patch.object(build, "BASE_URL", "https://sareen.wiki"):
            self.build()
        root, entries = self.feed()
        self.assertEqual([e.findtext(f"{ATOM}id") for e in entries], ids)
        self.assertEqual(entries[1].find(f"{ATOM}link").get("href"), "https://sareen.wiki/about.html")
        self.assertIn("https://sareen.wiki/feed.xml", self.read("feed.xml"))

    def test_content_urls_are_absolute_and_code_is_untouched(self):
        self.build({"content/log/2022-09-02.md": "[[reading]] [[ghost]] ![a](images/x%20y.png) [t](#top) "
                                                 "[e](https://e.org/) `src='k.png'`\n",
                    "images/x y.png": b"png"})
        content = self.feed()[1][0].findtext(f"{ATOM}content")
        for url in ('href="https://ns123abc.github.io/reading.html"', 'href="https://ns123abc.github.io/wanted.html#ghost"',
                    'src="https://ns123abc.github.io/images/x%20y.png"', 'href="https://ns123abc.github.io/2022-09-02.html#top"',
                    'href="https://e.org/"', "<code>src='k.png'</code>"):
            self.assertIn(url, content)

    def test_feed_skips_home_generated_and_undated_pages_and_is_capped(self):
        logs = {f"content/log/2023-02-{d:02}.md": "x\n" for d in range(1, 26)}
        self.build({**logs, "content/undated.md": "---\ntitle: u\n---\n"})
        ids = [e.findtext(f"{ATOM}id").rsplit(":", 1)[1] for e in self.feed()[1]]
        self.assertEqual(ids, [f"2023-02-{d:02}" for d in range(25, 5, -1)])

    def test_empty_feed_is_still_valid(self):
        undated = {f"content/{slug}.md": f"---\ntitle: {slug}\n---\n" for slug in ("index", "about", "nikhil_sareen")}
        self.build(undated, drop=[k for k in BASE if k.startswith("content/")])
        root, entries = self.feed()
        self.assertEqual(entries, [])
        self.assertEqual(root.findtext(f"{ATOM}updated"), "1970-01-01T00:00:00Z")


class SitemapTest(ExtrasTest):
    def test_sitemap_lists_every_page_with_lastmod(self):
        self.build(updated={"content/index.md": "2026-01-01", "content/reading.md": "2026-03-03",
                            "content/log/2022-08-27.md": "2026-02-02", "content/about.md": "2026-04-04"})
        root = ET.fromstring(self.read("sitemap.xml").encode("utf-8"))
        rows = {u.findtext(f"{SITEMAP}loc"): u.findtext(f"{SITEMAP}lastmod") for u in root}
        base = "https://ns123abc.github.io"
        self.assertEqual(rows, {
            f"{base}/": "2026-04-04", f"{base}/2021.html": "2026-03-03", f"{base}/2022.html": "2026-03-03",
            f"{base}/2022-08-27.html": "2026-02-02", f"{base}/2022-09-02.html": None, f"{base}/about.html": "2026-04-04",
            f"{base}/nikhil_sareen.html": None, f"{base}/now.html": None, f"{base}/reading.html": "2026-03-03"})

    def test_robots_allows_everything(self):
        with mock.patch.object(build, "BASE_URL", "https://sareen.wiki"):
            self.build()
        self.assertEqual(self.read("robots.txt"), "User-agent: *\nAllow: /\n\nSitemap: https://sareen.wiki/sitemap.xml\n")


class CorpusTest(ExtrasTest):
    def test_one_record_per_page_and_entry(self):
        self.build(updated={"content/about.md": "2026-10-28"})
        records = self.corpus()
        pages = [r for r in records if r["kind"] != "item"]
        self.assertEqual([r["id"] for r in pages],
                         ["index", "about", "nikhil_sareen", "now", "reading", "2022-08-27", "2022-09-02"])
        self.assertEqual(pages[1], {
            "id": "about", "kind": "page", "title": "about", "url": "https://ns123abc.github.io/about.html",
            "path": "content/about.md", "parent": None, "created": "2022-09-01", "date": None, "date_approx": False,
            "updated": "2026-10-28", "summary": "Who & why.", "links": ["ghost", "spook"], "backlinks": [],
            "text": "About [[ghost]], [[ghost|boo]] and [[spook]]."})
        self.assertEqual(pages[0]["text"], "See [[now|recent changes]].")
        self.assertEqual(pages[0]["url"], "https://ns123abc.github.io/")
        self.assertEqual((pages[4]["kind"], pages[4]["backlinks"]), ("list", ["2022-08-27"]))
        self.assertEqual(pages[5]["date"], "2022-08-27")
        self.assertTrue(pages[5]["date_approx"])
        self.assertEqual(len({r["id"] for r in records}), len(records))
        self.assertNotIn('\\u', self.read("corpus.jsonl"))

    def test_list_items(self):
        self.build({"content/reading.md": BASE["content/reading.md"] + "- **Genius Makers**: Cade Metz\n"
                                          "- **Kafka**: Max Brod. 1937\n- not an item\n  - **Nested**: x\n"})
        items = [r for r in self.corpus() if r["kind"] == "item"]
        self.assertEqual([(r["id"], r["section"], r["year"], r["title"], r["creator"], r["made"]) for r in items], [
            ("reading/incoming/sicp", "Incoming", None, "SICP", "Abelson and Sussman", None),
            ("reading/2022/crime-and-punishment", "2022", "2022", "Crime and Punishment", "Fyodor Dostoevsky", None),
            ("reading/2022/life-3-0", "2022", "2022", "Life 3.0", "Max Tegmark", "2017"),
            ("reading/2021/genius-makers", "2021", "2021", "Genius Makers", "Cade Metz", None),
            ("reading/2021/genius-makers-2", "2021", "2021", "Genius Makers", "Cade Metz", None),
            ("reading/2021/kafka", "2021", "2021", "Kafka", "Max Brod", "1937"),
        ])
        self.assertEqual(items[2]["text"], "** Life 3.0 ** : Max Tegmark. 2017")
        self.assertEqual(items[2]["url"], "https://ns123abc.github.io/reading.html")

    def test_duplicate_items_warn(self):
        site = self.build({"content/reading.md": BASE["content/reading.md"] + "- **genius makers**: Cade Metz\n"})
        self.assertIn("content/reading.md: 'genius makers' is listed twice under 2021", site.warnings)


class LlmsTest(ExtrasTest):
    def test_llms_txt(self):
        self.build({"content/index.md": "---\ntitle: home\nsummary: A wiki.\n---\n\nhi\n"})
        base = "https://ns123abc.github.io"
        self.assertEqual(self.read("llms.txt"), "\n".join([
            "# NEO", "", "> A wiki.", "",
            "## Pages", "", f"- [home]({base}/): A wiki.", f"- [about]({base}/about.html): Who & why.",
            f"- [Nikhil Sareen]({base}/nikhil_sareen.html)", f"- [now]({base}/now.html)", f"- [reading]({base}/reading.html)", "",
            "## Log", "", f"- [2022-09-02 Tiny bots]({base}/2022-09-02.html)", f"- [~2022-08-27]({base}/2022-08-27.html)", "",
            "## Files", "", f"- [llms-full.txt]({base}/llms-full.txt)", f"- [corpus.jsonl]({base}/corpus.jsonl)",
            f"- [feed.xml]({base}/feed.xml)", ""]))

    def test_llms_full_has_every_source_body_verbatim(self):
        self.build()
        full = self.read("llms-full.txt")
        self.assertTrue(full.startswith("# NEO\n\nhttps://ns123abc.github.io/\n\n# home\n\nurl: https://ns123abc.github.io/\n"
                                        "kind: page\n\nSee [[now|recent changes]].\n\n# about\n"))
        self.assertIn("# 2022-08-27\n\nurl: https://ns123abc.github.io/2022-08-27.html\nkind: log\n"
                      "date: 2022-08-27\ndate_approx: true\n\nRead [[reading]] and [[ghost]].\n", full)
        for rel, text in BASE.items():
            if rel.startswith("content/"):
                self.assertIn(build.parse_front_matter(text)[1].strip("\n"), full)
        self.assertNotIn("<time", full)
        self.assertNotIn("\n# 2022\n", full)


class OutputTest(ExtrasTest):
    def run_cli(self, out, seed):
        env = dict(os.environ, PYTHONHASHSEED=str(seed))
        return subprocess.run([sys.executable, os.path.join(REPO, "build.py"), "--root", self.root, "--out", out],
                              capture_output=True, text=True, env=env)

    def test_two_builds_are_byte_identical(self):
        self.make()
        a, b = os.path.join(self.tmp, "a", "site"), os.path.join(self.tmp, "b", "site")
        for out, seed in ((a, 1), (b, 2)):
            result = self.run_cli(out, seed)
            self.assertEqual(result.returncode, 0, result.stderr)
        first = snapshot(a)
        self.assertEqual(first, snapshot(b))
        for name in ("wanted.html", "404.html", "2022.html", "feed.xml", "sitemap.xml", "robots.txt",
                     "corpus.jsonl", "llms.txt", "llms-full.txt"):
            self.assertIn(name, first)

    def test_every_internal_link_resolves(self):
        self.build()
        for name in os.listdir(self.out):
            if not name.endswith(".html"):
                continue
            page = self.read(name)
            self.assertNotIn("ns123abc.github.io", page, name)
            for url in re.findall(r'(?:href|src)="([^"]*)"', page):
                parts = urlsplit(html.unescape(url))
                if parts.scheme or url.startswith("#") or url == "/":
                    continue
                self.assertTrue(os.path.isfile(os.path.join(self.out, unquote(parts.path))), f"{name}: {url}")


if __name__ == "__main__":
    unittest.main()
