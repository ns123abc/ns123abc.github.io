"""Tests for build.py. Run with `python3 -m unittest discover -s tests` (or pytest)."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import build  # noqa: E402

BASE = {
    "content/index.md": "---\ntitle: home\n---\n\nWelcome.\n",
    "content/about.md": "---\ntitle: about\n---\n\nAbout [[nikhil_sareen]].\n",
    "content/nikhil_sareen.md": "---\ntitle: Nikhil Sareen\nparent: about\n---\n\nHello.\n",
    "main.css": "body { color: black }\n",
    "images/mlogo.jpg": b"\xff\xd8logo",
    "images/slogo1.png": b"\x89PNG1",
    "images/slogo2.png": b"\x89PNG2",
    "images/slogo3.png": b"\x89PNG3",
    "images/slogo4.png": b"\x89PNG4",
    "images/slogo7.png": b"\x89PNG7",
}

HEADER = '<header><a href="index.html"><img src="images/mlogo.jpg" alt="NEO — home"></a></header>'


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


class SiteTest(unittest.TestCase):
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
        os.makedirs(os.path.join(self.root, "templates"), exist_ok=True)
        shutil.copyfile(os.path.join(REPO, "templates", "page.html"),
                        os.path.join(self.root, "templates", "page.html"))

    def build(self, files=None, drop=(), ok=True):
        self.make(files, drop)
        site = build.build(self.root, self.out)
        if ok:
            self.assertEqual(site.errors, [])
        return site

    def html(self, name):
        with open(os.path.join(self.out, name), encoding="utf-8") as fh:
            return fh.read()

    def assertError(self, site, *fragments):
        text = "\n".join(site.errors)
        for fragment in fragments:
            self.assertIn(fragment, text)


class SkeletonTest(SiteTest):
    def test_page_emits_the_w0_skeleton(self):
        self.build()
        page = self.html("nikhil_sareen.html")
        self.assertIn("\n" + HEADER + "\n", page)
        self.assertRegex(page, r'\n<nav class="main-nav"><ul><li>.*</li></ul></nav>\n')
        self.assertIn('<li><a href="nikhil_sareen.html" aria-current="page">Nikhil Sareen</a></li>', page)
        self.assertIn("\n<main><h1>Nikhil Sareen</h1>\n<p>Hello.</p>\n"
                      '<section class="incoming"><b>incoming</b>: <a href="about.html">about</a></section></main>\n',
                      page)
        self.assertRegex(page, r'\n<footer class="foot-nav">\n(<a href="https://[^"]+"><img src="images/slogo\d.png" '
                               r'alt="\w+"></a>\n){4}<span>.*</span>\n</footer>\n')
        self.assertIn('<a rel="license" href="https://creativecommons.org/licenses/by-nc-sa/4.0/">'
                      "CC BY-NC-SA 4.0</a>", page)
        self.assertIn('<a href="about.html">BY-NS-123 A.B.C</a>', page)
        self.assertNotIn("incoming", self.html("about.html"))

    def test_head(self):
        self.build({"content/about.md": "---\ntitle: about\nsummary: Who & \"why\".\n---\n\nx\n"})
        about = self.html("about.html")
        self.assertTrue(about.startswith('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                                         '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                                         "<title>about — NEO</title>\n"
                                         '<meta name="description" content="Who &amp; &quot;why&quot;.">\n'
                                         '<link rel="stylesheet" href="main.css">\n'
                                         '<link rel="icon" href="images/slogo7.png" type="image/png">\n'
                                         "</head>\n<body>\n"))
        self.assertNotIn('name="description"', self.html("nikhil_sareen.html"))

    def test_summary_is_never_generated(self):
        site = self.build({"content/about.md": "---\ntitle: about\n---\n\nA long first paragraph.\n"})
        self.assertIsNone(site.pages["about"].summary)
        self.assertNotIn("description", self.html("about.html"))

    def test_titles_are_html_escaped(self):
        self.build({"content/about.md": '---\ntitle: R&D <b>"x"</b>\n---\n\n[[about]]\n'})
        about = self.html("about.html")
        escaped = "R&amp;D &lt;b&gt;&quot;x&quot;&lt;/b&gt;"
        self.assertIn(f"<title>{escaped} — NEO</title>", about)
        self.assertIn(f"<h1>{escaped}</h1>", about)
        self.assertIn(f'aria-current="page">{escaped}</a>', about)
        self.assertNotIn("<b>", about)


class WikilinkTest(SiteTest):
    def test_existing_and_wanted_links(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n[[nikhil_sareen]] [[nikhil_sareen|me]] [[ghost]] [[ghost|boo]]\n"})
        self.assertIn('<p><a href="nikhil_sareen.html">nikhil_sareen</a> <a href="nikhil_sareen.html">me</a> '
                      '<a class="wanted" href="wanted.html#ghost">ghost</a> '
                      '<a class="wanted" href="wanted.html#ghost">boo</a></p>', self.html("about.html"))
        self.assertEqual(site.pages["about"].links, ["ghost", "nikhil_sareen"])
        self.assertEqual(site.wanted, {"ghost": ["about"]})

    def test_bare_link_text_is_the_slug_as_typed(self):
        self.build()
        self.assertIn('About <a href="nikhil_sareen.html">nikhil_sareen</a>.', self.html("about.html"))

    def test_wikilinks_inside_code_are_ignored(self):
        body = ("Inline `[[ghost]]` and ``[[ghost|x]]``.\n\n"
                "```\n[[ghost]]\n```\n\n"
                "~~~md\n[[nikhil_sareen|y]]\n~~~\n\n"
                "    [[ghost]] indented\n\n"
                "| a | b |\n| --- | --- |\n| `[[ghost]]` | c |\n")
        site = self.build({"content/about.md": f"---\ntitle: about\n---\n\n{body}"})
        about = self.html("about.html")
        main = about[about.index("<main>"):about.index("</main>")]
        self.assertNotIn("<a ", main)
        self.assertEqual(site.pages["about"].links, [])
        self.assertEqual(site.wanted, {})
        self.assertNotIn("about", site.pages["nikhil_sareen"].backlinks)
        self.assertIn("<code>[[ghost]]</code>", main)
        self.assertIn("<pre><code>[[ghost]]\n</code></pre>", main)
        self.assertIn('<code class="language-md">[[nikhil_sareen|y]]\n</code>', main)
        self.assertIn("<pre><code>[[ghost]] indented\n</code></pre>", main)

    def test_escaped_brackets_stay_literal(self):
        site = self.build({"content/about.md": "---\ntitle: about\n---\n\n\\[[ghost]]\n"})
        self.assertIn("<p>[[ghost]]</p>", self.html("about.html"))
        self.assertEqual(site.wanted, {})

    def test_escaped_pipe_inside_tables(self):
        self.build({"content/about.md": "---\ntitle: about\n---\n\n"
                                        "| who | note |\n| --- | --- |\n| [[nikhil_sareen\\|Nik]] | [[ghost\\|g]] |\n"})
        about = self.html("about.html")
        self.assertIn('<tr>\n<td><a href="nikhil_sareen.html">Nik</a></td>\n'
                      '<td><a class="wanted" href="wanted.html#ghost">g</a></td>\n</tr>', about)

    def test_escaped_pipe_outside_tables(self):
        self.build({"content/about.md": "---\ntitle: about\n---\n\n[[nikhil_sareen\\|Nik]]\n"})
        self.assertIn('<a href="nikhil_sareen.html">Nik</a>', self.html("about.html"))

    def test_unescaped_pipe_inside_a_table_is_an_error(self):
        site = self.build({"content/about.md": "---\ntitle: about\n---\n\n"
                                               "| who | note |\n| --- | --- |\n| [[nikhil_sareen|Nik]] | x |\n"}, ok=False)
        self.assertError(site, "content/about.md: wikilink split across table cells", "[[slug\\|text]]")

    def test_bad_targets_are_errors(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n[[Nikhil_Sareen]] [[foo bar]] [[about|]] [[]]\n"}, ok=False)
        self.assertError(site, "bad wikilink [[Nikhil_Sareen]]", "bad wikilink [[foo bar]]",
                         "bad wikilink [[about|]]", "bad wikilink [[]]")


class ModelTest(SiteTest):
    def test_backlinks_and_wanted_are_sorted_and_skip_self_links(self):
        site = self.build({
            "content/zeta.md": "---\ntitle: zeta\n---\n\n[[about]] [[zeta]] [[ghost]]\n",
            "content/alpha.md": "---\ntitle: alpha\n---\n\n[[about]] [[ghost]] [[ghost]] [[about]]\n",
            "content/about.md": "---\ntitle: about\n---\n\n[[about]] [[nikhil_sareen]]\n",
        })
        self.assertEqual(site.pages["about"].backlinks, ["alpha", "zeta"])
        self.assertEqual(site.pages["alpha"].links, ["about", "ghost"])
        self.assertEqual(site.wanted, {"ghost": ["alpha", "zeta"]})
        self.assertIn('<b>incoming</b>: <a href="alpha.html">alpha</a> <a href="zeta.html">zeta</a></section>',
                      self.html("about.html"))
        self.assertEqual(list(site.pages), sorted(site.pages))

    def test_page_fields(self):
        site = self.build({"content/about.md": "---\ntitle: about\ncreated: 2022-09-01\n"
                                               "summary: Mine.\naliases: [About.html]\n---\n\nHi *there*.\n"})
        about = site.pages["about"]
        self.assertEqual((about.slug, about.title, about.parent, about.kind, about.created, about.date),
                         ("about", "about", None, "page", "2022-09-01", None))
        self.assertEqual(about.summary, "Mine.")
        self.assertEqual(about.body_md, "\nHi *there*.\n")
        self.assertEqual(about.html, "<p>Hi <em>there</em>.</p>\n")
        self.assertIsNone(about.updated)
        self.assertEqual(about["title"], "about")
        self.assertEqual(build.BASE_URL, "https://ns123abc.github.io")

    def test_kinds(self):
        site = self.build({
            "content/reading.md": "---\ntitle: reading\n---\n\n## 2022\n\n- **Meditations**: Marcus Aurelius. 180\n",
            "content/code.md": "---\ntitle: code\n---\n\n```\n## 2022\n```\n\n### 2021\n",
            "content/log/2022-08-29.md": "Short entry.\n",
        })
        kinds = {slug: page.kind for slug, page in site.pages.items()}
        self.assertEqual(kinds, {"2022-08-29": "log", "about": "page", "code": "page", "index": "page",
                                 "nikhil_sareen": "page", "reading": "list"})


class LogTest(SiteTest):
    def test_log_entry_gets_its_own_page(self):
        site = self.build({"content/log/2022-08-29.md": "Read [[about]].\n",
                           "content/log/2022-09-01.md": "---\ntitle: Mirrors\ndate: 2022-09-01\n"
                                                        "date_approx: true\n---\n\nx\n"})
        entry = site.pages["2022-08-29"]
        self.assertEqual((entry.kind, entry.title, entry.date, entry.date_approx), ("log", "2022-08-29", "2022-08-29", False))
        self.assertEqual(entry.path, "content/log/2022-08-29.md")
        self.assertTrue(site.pages["2022-09-01"].date_approx)
        self.assertIn("<h1>2022-08-29</h1>", self.html("2022-08-29.html"))
        self.assertIn("<h1>Mirrors</h1>", self.html("2022-09-01.html"))
        self.assertEqual(site.pages["about"].backlinks, ["2022-08-29"])
        self.assertNotIn("2022-", self.html("about.html").split("<main>")[0])

    def test_log_date_must_match_the_file_name(self):
        site = self.build({"content/log/2022-08-29.md": "---\ndate: 2023-01-01\n---\n\nx\n"}, ok=False)
        self.assertError(site, "content/log/2022-08-29.md: date '2023-01-01' doesn't match the file name")

    def test_log_file_names_are_dates(self):
        site = self.build({"content/log/2022-02-30.md": "x\n", "content/log/notes.md": "x\n"}, ok=False)
        self.assertError(site, "content/log/2022-02-30.md: log entries are named YYYY-MM-DD.md",
                         "content/log/notes.md: log entries are named YYYY-MM-DD.md")


class NavTest(SiteTest):
    FILES = {
        "content/now.md": "---\ntitle: now\n---\n\nx\n",
        "content/goals.md": "---\ntitle: goals\nparent: nikhil_sareen\n---\n\nx\n",
        "content/directory.md": "---\ntitle: directory\nparent: nikhil_sareen\n---\n\nx\n",
        "content/reading.md": "---\ntitle: reading\nparent: directory\n---\n\nx\n",
        "content/log/2022-08-29.md": "---\nparent: now\n---\n\nx\n",
    }

    def nav(self, name):
        return re.search(r'<nav class="main-nav">(.*)</nav>', self.html(name)).group(1)

    def test_columns_follow_parents(self):
        self.build(self.FILES)
        self.assertEqual(self.nav("nikhil_sareen.html"),
                         '<ul><li><a class="parent" href="about.html">about</a></li><li><a href="now.html">now</a></li></ul>'
                         '<ul><li><a href="nikhil_sareen.html" aria-current="page">Nikhil Sareen</a></li></ul>'
                         '<ul><li><a href="directory.html">directory</a></li><li><a href="goals.html">goals</a></li></ul>')
        self.assertEqual(self.nav("reading.html"),
                         '<ul><li><a class="parent" href="about.html">about</a></li><li><a href="now.html">now</a></li></ul>'
                         '<ul><li><a class="parent" href="nikhil_sareen.html">Nikhil Sareen</a></li></ul>'
                         '<ul><li><a class="parent" href="directory.html">directory</a></li><li><a href="goals.html">goals</a></li></ul>'
                         '<ul><li><a href="reading.html" aria-current="page">reading</a></li></ul>')

    def test_index_and_log_entries_are_not_listed(self):
        self.build(self.FILES)
        top = '<ul><li><a href="about.html">about</a></li><li><a href="now.html">now</a></li></ul>'
        self.assertEqual(self.nav("index.html"), top)
        self.assertEqual(self.nav("now.html"),
                         '<ul><li><a href="about.html">about</a></li><li><a href="now.html" aria-current="page">now</a></li></ul>')
        self.assertEqual(self.nav("2022-08-29.html"),
                         '<ul><li><a href="about.html">about</a></li><li><a class="parent" href="now.html">now</a></li></ul>')

    def test_parent_errors(self):
        site = self.build({
            "content/a.md": "---\ntitle: a\nparent: index\n---\n",
            "content/b.md": "---\ntitle: b\nparent: nowhere\n---\n",
            "content/c.md": "---\ntitle: c\nparent: d\n---\n",
            "content/d.md": "---\ntitle: d\nparent: c\n---\n",
            "content/e.md": "---\ntitle: e\nparent: e\n---\n",
        }, ok=False)
        self.assertError(site, "content/a.md: top-level pages have no parent; remove 'parent: index'",
                         "content/b.md: parent 'nowhere' has no page",
                         "content/c.md: parent cycle: c -> d -> c", "content/e.md: parent cycle: e -> e")
        self.assertEqual(sum("cycle" in e for e in site.errors), 2)


class FrontMatterTest(SiteTest):
    def test_bad_front_matter(self):
        site = self.build({
            "content/a.md": "---\ntitle: a\ntags: x\n---\n",
            "content/b.md": "---\ntitle: b\ntitle: again\n---\n",
            "content/c.md": "---\nparent: about\n---\n",
            "content/d.md": "---\ntitle: d\ncreated: 29/08/2022\n---\n",
            "content/e.md": "---\ntitle: e\ndate: 2022-08-29\n---\n",
            "content/f.md": "---\ntitle: f\ndate_approx: yes\n---\n",
            "content/g.md": "---\ntitle: g\naliases:\n  - G.html\n---\n",
            "content/h.md": "---\ntitle: h\n",
            "content/i.md": "No front matter.\n",
        }, ok=False)
        self.assertError(site, "content/a.md: line 3: unknown key 'tags'",
                         "content/b.md: line 3: duplicate key 'title'",
                         "content/c.md: missing title",
                         "content/d.md: created must be a YYYY-MM-DD date, got '29/08/2022'",
                         "content/e.md: date is for log entries only",
                         "content/f.md: date_approx must be true or false, got 'yes'",
                         "content/g.md: line 4: not a flat 'key: value' line: '- G.html'",
                         "content/h.md: front matter has no closing ---",
                         "content/i.md: missing title")

    def test_quotes_crlf_and_bom(self):
        site = self.build({"content/about.md": '\ufeff---\r\ntitle: "About: me"\r\nparent: \r\n---\r\n\r\nHi.\r\n'})
        self.assertEqual(site.pages["about"].title, "About: me")
        self.assertIsNone(site.pages["about"].parent)
        self.assertEqual(site.pages["about"].html, "<p>Hi.</p>\n")


class CheckTest(SiteTest):
    def test_case_colliding_slugs_fail(self):
        _put(self.tmp, "probe", "")
        if os.path.exists(os.path.join(self.tmp, "PROBE")):
            self.skipTest("case-insensitive filesystem")
        site = self.build({"content/About.md": "---\ntitle: About\n---\n"}, ok=False)
        self.assertError(site, "content/About.md: same slug as content/about.md")

    def test_uppercase_and_odd_slugs_fail(self):
        site = self.build({"content/Dostoevsky.md": "---\ntitle: D\n---\n",
                           "content/two words.md": "---\ntitle: t\n---\n"}, ok=False)
        self.assertError(site, "content/Dostoevsky.md: bad slug 'Dostoevsky'", "content/two words.md: bad slug")

    def test_page_and_log_entry_cannot_share_a_slug(self):
        site = self.build({"content/2022-08-29.md": "---\ntitle: x\n---\n",
                           "content/log/2022-08-29.md": "x\n"}, ok=False)
        self.assertError(site, "content/2022-08-29.md: same slug as content/log/2022-08-29.md")

    def test_unexpected_files_and_folders(self):
        site = self.build({"content/photo.jpg": b"x", "content/drafts/a.md": "x", "content/.DS_Store": b"x"}, ok=False)
        self.assertError(site, "content/photo.jpg: unexpected file", "content/drafts: unexpected directory")
        self.assertNotIn(".DS_Store", "\n".join(site.errors))

    def test_missing_index(self):
        site = self.build(drop=("content/index.md",), ok=False)
        self.assertError(site, "content/index.md: missing")

    def test_broken_internal_links(self):
        body = ("[a](nope.html) [b](Nikhil_sareen.html) [c](nikhil_sareenhtml) ![d](../media/refs/x.png) "
                '![e]() <img src="images/gone.png" alt="f"> <a href="missing.html">g</a>\n')
        site = self.build({"content/about.md": f"---\ntitle: about\n---\n\n{body}"}, ok=False)
        self.assertError(site, "content/about.md: broken link 'nope.html'",
                         "broken link 'Nikhil_sareen.html' (did you mean [[nikhil_sareen]]?)",
                         "broken link 'nikhil_sareenhtml'", "broken link '../media/refs/x.png'",
                         "broken link ''", "broken link 'images/gone.png'", "broken link 'missing.html'")
        self.assertEqual(len(site.errors), 7)

    def test_working_links_pass(self):
        body = ("[a](about.html) [b](about.html#top) [c](https://example.com/x.html) [d](mailto:a@b.c) "
                "[e](#here) ![f](images/mlogo.jpg) ![g](<images/Fyodor Dostoevsky.jpeg>) [h](main.css) "
                '<a href="nikhil_sareen.html">i</a> [[ghost]]\n')
        self.build({"content/about.md": f"---\ntitle: about\n---\n\n{body}",
                    "images/Fyodor Dostoevsky.jpeg": b"jpg"})

    def test_template_chrome_links_are_checked(self):
        site = self.build(drop=("images/slogo3.png", "content/nikhil_sareen.md"), ok=False)
        self.assertError(site, "templates/page.html: broken link 'images/slogo3.png'",
                         "templates/page.html: broken link 'nikhil_sareen.html'")

    def test_missing_alt_text_warns(self):
        site = self.build({"content/about.md": '---\ntitle: about\n---\n\n![](images/mlogo.jpg) '
                                               '![ok](images/mlogo.jpg) <img src="images/slogo1.png">\n'})
        self.assertEqual([w for w in site.warnings if "alt" in w],
                         ["content/about.md: image without alt text: images/mlogo.jpg",
                          "content/about.md: image without alt text: images/slogo1.png"])

    def test_own_h1_warns(self):
        site = self.build({"content/about.md": "---\ntitle: about\n---\n\n# One\n\n# Two\n"})
        self.assertEqual(site.warnings, ["content/about.md: has its own '# ' heading; "
                                         "the template already adds <h1> from the title"])


class OutputTest(SiteTest):
    FILES = {
        "content/about.md": "---\ntitle: about\nsummary: s\n---\n\n[[ghost]] [[nikhil_sareen]] `[[x]]`\n\n"
                            "| a | b |\n| - | - |\n| [[index\\|home]] | ok |\n",
        "content/reading.md": "---\ntitle: reading\nparent: about\n---\n\n## 2022\n\n- **A**: B. 2000\n",
        "content/log/2022-08-29.md": "[[reading]]\n",
        "fonts/silkscreen.woff2": b"woff2",
        "fonts/OFL.txt": "license\n",
    }

    def run_cli(self, out, seed):
        env = dict(os.environ, PYTHONHASHSEED=str(seed))
        return subprocess.run([sys.executable, os.path.join(REPO, "build.py"), "--root", self.root, "--out", out],
                              capture_output=True, text=True, env=env)

    def test_two_builds_are_byte_identical(self):
        self.make(self.FILES)
        a, b = os.path.join(self.tmp, "a", "site"), os.path.join(self.tmp, "b", "site")
        for out, seed in ((a, 1), (b, 2)):
            result = self.run_cli(out, seed)
            self.assertEqual(result.returncode, 0, result.stderr)
        first = snapshot(a)
        self.assertEqual(first, snapshot(b))
        self.assertIn("about.html", first)
        self.assertIn("fonts/OFL.txt", first)

    def test_rebuild_in_place_is_identical_and_drops_stale_files(self):
        self.make(self.FILES)
        self.assertEqual(build.build(self.root, self.out).errors, [])
        first = snapshot(self.out)
        _put(self.out, "stale.html", "old")
        self.assertEqual(build.build(self.root, self.out).errors, [])
        self.assertEqual(snapshot(self.out), first)

    def test_static_files_are_copied(self):
        self.build({**self.FILES, "images/.DS_Store": b"x", "images/sub/a.png": b"a", "README.md": "x"})
        files = snapshot(self.out)
        self.assertEqual(files["main.css"], b"body { color: black }\n")
        self.assertEqual(files["fonts/silkscreen.woff2"], b"woff2")
        self.assertEqual(files["images/sub/a.png"], b"a")
        self.assertNotIn("images/.DS_Store", files)
        self.assertNotIn("README.md", files)
        self.assertNotIn("templates/page.html", files)

    def test_internal_hrefs_are_relative(self):
        self.build(self.FILES)
        for name, data in snapshot(self.out).items():
            if name.endswith(".html"):
                for url in re.findall(r'(?:href|src)="([^"]*)"', data.decode("utf-8")):
                    self.assertFalse(url.startswith("/"), f"{name}: {url}")
                    if not url.startswith(("https://", "#")):
                        self.assertNotIn(":", url, f"{name}: {url}")

    def test_cli_exit_codes(self):
        self.make(self.FILES)
        ok = self.run_cli(self.out, 0)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("built 3 pages, 1 lists, 1 log entries, 1 wanted", ok.stdout)
        _put(self.root, "content/bad.md", "---\ntitle: bad\n---\n\n[x](nope.html)\n")
        bad = self.run_cli(self.out, 0)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("error: content/bad.md: broken link 'nope.html'", bad.stderr)

    def test_no_content_folder_is_a_no_op(self):
        self.make(drop=[k for k in BASE if k.startswith("content/")])
        self.assertFalse(os.path.exists(os.path.join(self.root, "content")))
        result = self.run_cli(self.out, 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("warning: content/: missing, so there is nothing to build", result.stderr)
        self.assertFalse(os.path.exists(self.out))

    def test_refuses_to_clear_a_folder_not_named_site(self):
        self.make()
        other = os.path.join(self.tmp, "precious")
        _put(other, "keep.txt", "x")
        site = build.build(self.root, other)
        self.assertError(site, "refusing to clear")
        self.assertTrue(os.path.exists(os.path.join(other, "keep.txt")))
        self.assertError(build.build(self.root, self.tmp), "refusing to build into")


@unittest.skipIf(shutil.which("git") is None, "git not installed")
class GitTest(SiteTest):
    def git(self, *args, date=None):
        env = dict(os.environ, **({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}))
        subprocess.run(["git", "-C", self.root, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       check=True, capture_output=True, env=env)

    def test_updated_comes_from_one_git_log(self):
        self.make({f"content/p{i}.md": f"---\ntitle: p{i}\n---\n" for i in range(20)})
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "one", date="2022-08-29T10:00:00+08:00")
        _put(self.root, "content/about.md", "---\ntitle: about\n---\n\nEdited [[nikhil_sareen]].\n")
        self.git("commit", "-qam", "two", date="2026-10-28T09:00:00+00:00")
        _put(self.root, "content/new.md", "---\ntitle: new\n---\n")
        real_run, calls = subprocess.run, []

        def counting_run(cmd, *args, **kwargs):
            calls.append(cmd)
            return real_run(cmd, *args, **kwargs)

        with mock.patch.object(build.subprocess, "run", counting_run):
            site = build.build(self.root, self.out)
        self.assertEqual(site.errors, [])
        self.assertEqual(site.pages["about"].updated, "2026-10-28")
        self.assertEqual(site.pages["p7"].updated, "2022-08-29")
        self.assertIsNone(site.pages["new"].updated)
        self.assertEqual(len(calls), 2)


class ExtrasTest(SiteTest):
    EXTRAS = '''
import build as neo

def extend(site):
    site.pages["2022"] = neo.Page(slug="2022", title="2022", body_md="[[2022-08-29]]")

def build(site, out):
    page = neo.Page(slug="wanted", title="wanted", html="<ul>%s</ul>" % "".join(
        "<li id=%s>%s</li>" % (slug, ", ".join(sources)) for slug, sources in site.wanted.items()))
    site.write("wanted.html", site.render(page))
    site.write("feed.xml", "<feed/>")
'''

    def test_hooks(self):
        site = self.build({"extras.py": self.EXTRAS, "content/log/2022-08-29.md": "x\n",
                           "content/about.md": "---\ntitle: about\n---\n\n[[2022]] [[ghost]] [feed](feed.xml)\n"})
        self.assertEqual(site.pages["about"].links, ["2022", "ghost"])
        self.assertEqual(site.wanted, {"ghost": ["about"]})
        self.assertEqual(site.pages["2022-08-29"].backlinks, ["2022"])
        self.assertIn('<a href="2022.html">2022</a>', self.html("about.html"))
        self.assertIn("<h1>2022</h1>", self.html("2022.html"))
        wanted = self.html("wanted.html")
        self.assertIn("<title>wanted — NEO</title>", wanted)
        self.assertIn("<ul><li id=ghost>about</li></ul>", wanted)
        self.assertEqual(self.html("feed.xml"), "<feed/>")

    def test_writing_a_file_twice_is_an_error(self):
        site = self.build({"extras.py": "def build(site, out):\n    site.write('about.html', 'x')\n"}, ok=False)
        self.assertError(site, "about.html is written twice")


if __name__ == "__main__":
    unittest.main()
