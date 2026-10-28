"""Wikilink edges that tests/test_build.py does not already lock.

The build tests cover a wikilink hidden in code, an escaped pipe in a table cell,
``[[about|]]`` / ``[[]]``, a self-link left out of backlinks, and ``About.md`` colliding
with ``about.md``. This file covers the surrounding edges: a real link beside code,
labels that are only whitespace, a self-link that still renders, and case collisions
that drop every file involved.
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_build import SiteTest  # noqa: E402

_SLUG_RULE = "the target must be a slug ([a-z0-9_-]) and the text can't be empty"
_CASE_RULE = ("slugs must be unique ignoring case "
              "(macOS treats About.md and about.md as one file)")


def _bad(raw):
    return f"content/about.md: bad wikilink {raw}: {_SLUG_RULE}"


def _skip_if_case_insensitive(test):
    probe = os.path.join(test.tmp, "probe")
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write("")
    if os.path.exists(os.path.join(test.tmp, "PROBE")):
        test.skipTest("case-insensitive filesystem")


class WikilinkEdgeTest(SiteTest):
    def main_of(self, name):
        page = self.html(name)
        return page[page.index("<main>"):page.index("</main>")]

    def test_a_code_span_does_not_swallow_the_wikilink_beside_it(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n"
                           "`[[ghost]]` then [[nikhil_sareen|me]] and ``[[ghost|x]]``.\n"})
        main = self.main_of("about.html")
        self.assertIn("<code>[[ghost]]</code> then <a href=\"nikhil_sareen.html\">me</a> "
                      "and <code>[[ghost|x]]</code>.", main)
        self.assertEqual(site.pages["about"].links, ["nikhil_sareen"])
        self.assertEqual(site.wanted, {})
        self.assertEqual(site.pages["nikhil_sareen"].backlinks, ["about"])

    def test_a_code_block_leaves_the_following_paragraph_linked(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n"
                           "````\n```\n[[ghost]]\n```\n````\n\n"
                           "    [[ghost|x]]\n\n"
                           "[[nikhil_sareen]]\n"})
        main = self.main_of("about.html")
        self.assertIn("<pre><code>```\n[[ghost]]\n```\n</code></pre>", main)
        self.assertIn("<pre><code>[[ghost|x]]\n</code></pre>", main)
        self.assertIn('<p><a href="nikhil_sareen.html">nikhil_sareen</a></p>', main)
        self.assertEqual(site.pages["about"].links, ["nikhil_sareen"])
        self.assertEqual(site.wanted, {})

    def test_code_spans_in_a_list_a_quote_and_a_heading_stay_literal(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n"
                           "- `[[ghost]]`\n"
                           "- [[nikhil_sareen]]\n\n"
                           "> `[[ghost|x]]`\n>\n"
                           "> [[index|home]]\n\n"
                           "# `[[ghost]]`\n\n"
                           "## [[nikhil_sareen|sec]]\n"})
        main = self.main_of("about.html")
        self.assertIn("<li><code>[[ghost]]</code></li>", main)
        self.assertIn('<li><a href="nikhil_sareen.html">nikhil_sareen</a></li>', main)
        self.assertIn("<code>[[ghost|x]]</code>", main)
        self.assertIn('<a href="index.html">home</a>', main)
        self.assertIn("<h1><code>[[ghost]]</code></h1>", main)
        self.assertIn('<h2><a href="nikhil_sareen.html">sec</a></h2>', main)
        self.assertEqual(site.pages["about"].links, ["index", "nikhil_sareen"])
        self.assertEqual(site.pages["about"].kind, "page")
        self.assertEqual(site.wanted, {})

    def test_a_code_span_that_breaks_a_wikilink_is_not_a_link(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n[[nikhil_`sareen`]]\n"}, ok=False)
        self.assertEqual(site.errors, [_bad("[[nikhil_`sareen`]]")])
        self.assertEqual(site.pages["about"].html, "<p>[[nikhil_<code>sareen</code>]]</p>\n")
        self.assertEqual(site.pages["about"].links, [])
        self.assertEqual(site.wanted, {})
        self.assertEqual(site.pages["nikhil_sareen"].backlinks, [])
        self.assertFalse(os.path.exists(self.out))

    def test_strikethrough_is_not_code_and_still_links(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n~~[[ghost]]~~ [[nikhil_sareen]]\n"})
        self.assertIn('<s><a class="wanted" href="wanted.html#ghost">ghost</a></s> '
                      '<a href="nikhil_sareen.html">nikhil_sareen</a>', self.main_of("about.html"))
        self.assertEqual(site.pages["about"].links, ["ghost", "nikhil_sareen"])
        self.assertEqual(site.wanted, {"ghost": ["about"]})

    def test_a_raw_html_code_tag_does_not_hide_a_wikilink(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n"
                           "<code>[[ghost]]</code> and <code>[[nikhil_sareen|me]]</code>\n"})
        self.assertIn('<code><a class="wanted" href="wanted.html#ghost">ghost</a></code> and '
                      '<code><a href="nikhil_sareen.html">me</a></code>', self.main_of("about.html"))
        self.assertEqual(site.pages["about"].links, ["ghost", "nikhil_sareen"])
        self.assertEqual(site.wanted, {"ghost": ["about"]})

    def test_header_cells_and_bare_slugs_link_inside_a_table(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n"
                           "| [[nikhil_sareen\\|who]] | note |\n"
                           "| --- | --- |\n"
                           "| [[nikhil_sareen]] | [[ghost]] [[index\\|home]] |\n"})
        self.assertIn("<th><a href=\"nikhil_sareen.html\">who</a></th>", self.html("about.html"))
        self.assertIn("<td><a href=\"nikhil_sareen.html\">nikhil_sareen</a></td>\n"
                      "<td><a class=\"wanted\" href=\"wanted.html#ghost\">ghost</a> "
                      "<a href=\"index.html\">home</a></td>", self.html("about.html"))
        self.assertEqual(site.pages["about"].links, ["ghost", "index", "nikhil_sareen"])
        self.assertEqual(site.pages["index"].backlinks, ["about"])
        self.assertEqual(site.wanted, {"ghost": ["about"]})

    def test_a_table_cell_keeps_a_code_span_and_links_the_rest(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n"
                           "| cell |\n| --- |\n| `[[ghost]]` [[nikhil_sareen]] |\n"})
        self.assertIn("<td><code>[[ghost]]</code> "
                      "<a href=\"nikhil_sareen.html\">nikhil_sareen</a></td>",
                      self.html("about.html"))
        self.assertEqual(site.pages["about"].links, ["nikhil_sareen"])
        self.assertEqual(site.wanted, {})

    def test_table_labels_escape_html_and_keep_an_embedded_pipe(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n"
                           "| who | note |\n| --- | --- |\n"
                           "| [[ nikhil_sareen \\| A & B <c> ]] | [[ghost\\|x\\|y]] |\n"})
        about = self.html("about.html")
        self.assertIn('<td><a href="nikhil_sareen.html">A &amp; B &lt;c&gt;</a></td>', about)
        self.assertIn('<td><a class="wanted" href="wanted.html#ghost">x|y</a></td>', about)
        self.assertNotIn("&amp;amp;", about)
        self.assertEqual(site.pages["about"].links, ["ghost", "nikhil_sareen"])
        self.assertEqual(site.wanted, {"ghost": ["about"]})

    def test_an_empty_label_in_a_table_is_literal_and_not_a_split(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n"
                           "| a | b |\n| --- | --- |\n"
                           "| [[nikhil_sareen\\|]] | [[index]] |\n"}, ok=False)
        self.assertEqual(site.errors, [_bad("[[nikhil_sareen|]]")])
        self.assertNotIn("split across", "\n".join(site.errors))
        self.assertIn("<td>[[nikhil_sareen|]]</td>", site.pages["about"].html)
        self.assertIn('<td><a href="index.html">index</a></td>', site.pages["about"].html)
        self.assertEqual(site.pages["about"].links, ["index"])
        self.assertEqual(site.pages["index"].backlinks, ["about"])
        self.assertEqual(site.wanted, {})
        self.assertFalse(os.path.exists(self.out))

    def test_one_split_cell_does_not_drop_the_wikilink_in_another(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n"
                           "| see [[ note | x |\n| --- | --- |\n| ok | [[ghost]] |\n"}, ok=False)
        self.assertError(site, "wikilink split across table cells in 'see [[ note'", "[[slug\\|text]]")
        self.assertIn('<td><a class="wanted" href="wanted.html#ghost">ghost</a></td>',
                      site.pages["about"].html)
        self.assertEqual(site.pages["about"].links, ["ghost"])
        self.assertEqual(site.wanted, {"ghost": ["about"]})
        self.assertFalse(os.path.exists(self.out))

    def test_an_unescaped_pipe_in_the_header_never_becomes_a_table(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n"
                           "| [[nikhil_sareen|who]] | note |\n| --- | --- |\n| x | y |\n"})
        html = site.pages["about"].html
        self.assertNotIn("<table>", html)
        self.assertNotIn("split across", "\n".join(site.errors))
        self.assertIn('<a href="nikhil_sareen.html">who</a>', html)
        self.assertEqual(site.pages["about"].links, ["nikhil_sareen"])

    def test_whitespace_only_labels_and_empty_targets_stay_literal(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n"
                           "[[about| ]] [[ |text]] [[ | ]] [[about\\|]] "
                           "[[about|   ]] [[nikhil_sareen| ]] [[about|0]] [[about|-]]\n"},
                          ok=False)
        self.assertEqual(site.errors, [
            _bad("[[ | ]]"),
            _bad("[[ |text]]"),
            _bad("[[about\\|]]"),
            _bad("[[about|   ]]"),
            _bad("[[about| ]]"),
            _bad("[[nikhil_sareen| ]]"),
        ])
        self.assertEqual(site.pages["about"].html,
                         "<p>[[about| ]] [[ |text]] [[ | ]] [[about|]] "
                         "[[about|   ]] [[nikhil_sareen| ]] "
                         "<a href=\"about.html\">0</a> <a href=\"about.html\">-</a></p>\n")
        self.assertEqual(site.pages["about"].links, ["about"])
        self.assertEqual(site.pages["about"].backlinks, [])
        self.assertEqual(site.pages["nikhil_sareen"].backlinks, [])
        self.assertEqual(site.wanted, {})
        self.assertFalse(os.path.exists(self.out))

    def test_a_self_link_renders_and_is_not_incoming(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n[[about]] [[about|this]] [[about]]\n"})
        self.assertEqual(site.pages["about"].html,
                         '<p><a href="about.html">about</a> <a href="about.html">this</a> '
                         '<a href="about.html">about</a></p>\n')
        self.assertEqual(site.pages["about"].links, ["about"])
        self.assertEqual(site.pages["about"].backlinks, [])
        self.assertEqual(site.wanted, {})
        self.assertNotIn("incoming", self.html("about.html"))
        self.assertNotIn('class="wanted"', self.main_of("about.html"))

    def test_a_log_entry_can_link_to_itself(self):
        site = self.build({"content/log/2022-08-29.md":
                           "See [[2022-08-29]] and [[2022-08-29|today]].\n"})
        entry = site.pages["2022-08-29"]
        self.assertEqual(entry.links, ["2022-08-29"])
        self.assertEqual(entry.backlinks, [])
        self.assertEqual(entry.html,
                         '<p>See <a href="2022-08-29.html">2022-08-29</a> and '
                         '<a href="2022-08-29.html">today</a>.</p>\n')
        self.assertEqual(site.wanted, {})
        self.assertNotIn("incoming", self.html("2022-08-29.html"))
        self.assertNotIn("2022-08-29", site.pages["about"].backlinks)

    def test_a_self_link_inside_a_table_is_not_a_backlink(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n| me |\n| --- |\n| [[about\\|here]] |\n"})
        self.assertIn('<td><a href="about.html">here</a></td>', self.html("about.html"))
        self.assertEqual(site.pages["about"].links, ["about"])
        self.assertEqual(site.pages["about"].backlinks, [])
        self.assertEqual(site.wanted, {})
        self.assertNotIn("incoming", self.html("about.html"))

    def test_three_case_variants_are_one_error_and_no_page(self):
        _skip_if_case_insensitive(self)
        site = self.build({
            "content/Foo.md": "---\ntitle: Foo\n---\n",
            "content/foo.md": "---\ntitle: foo\n---\n",
            "content/FOO.md": "---\ntitle: FOO\n---\n",
        }, ok=False)
        self.assertEqual(site.errors, [
            "content/FOO.md: same slug as content/Foo.md, content/foo.md: " + _CASE_RULE,
        ])
        for slug in ("foo", "Foo", "FOO"):
            self.assertNotIn(slug, site.pages)
        self.assertFalse(os.path.exists(self.out))

    def test_a_case_collision_does_not_also_report_a_bad_slug(self):
        _skip_if_case_insensitive(self)
        site = self.build({
            "content/Dostoevsky.md": "---\ntitle: D\n---\n",
            "content/dostoevsky.md": "---\ntitle: d\n---\n\n[[nikhil_sareen]]\n",
        }, ok=False)
        self.assertEqual(site.errors, [
            "content/Dostoevsky.md: same slug as content/dostoevsky.md: " + _CASE_RULE,
        ])
        self.assertNotIn("bad slug", "\n".join(site.errors))
        self.assertNotIn("dostoevsky", site.pages)
        self.assertNotIn("Dostoevsky", site.pages)
        self.assertFalse(os.path.exists(self.out))

    def test_an_index_case_collision_does_not_also_report_missing(self):
        _skip_if_case_insensitive(self)
        site = self.build({"content/INDEX.md": "---\ntitle: INDEX\n---\n"}, ok=False)
        self.assertEqual(site.errors, [
            "content/INDEX.md: same slug as content/index.md: " + _CASE_RULE,
        ])
        self.assertNotIn("index", site.pages)
        self.assertNotIn("missing", "\n".join(site.errors))
        self.assertIn("about", site.pages)
        self.assertFalse(os.path.exists(self.out))

    def test_a_page_and_a_log_that_differ_only_by_case_collide(self):
        _skip_if_case_insensitive(self)
        site = self.build({"content/log/About.md": "x\n"}, ok=False)
        self.assertEqual(site.errors, [
            "content/about.md: same slug as content/log/About.md: " + _CASE_RULE,
        ])
        self.assertNotIn("about", site.pages)
        self.assertNotIn("log entries are named", "\n".join(site.errors))
        self.assertNotIn("parent", "\n".join(site.errors))
        self.assertFalse(os.path.exists(self.out))

    def test_wikilink_targets_are_not_folded_to_another_case(self):
        site = self.build({"content/about.md":
                           "---\ntitle: about\n---\n\n"
                           "[[About]] [[NIKHIL_SAREEN|Nik]] [[Index]] [[about]]\n"}, ok=False)
        self.assertEqual(site.errors, [
            _bad("[[About]]"),
            _bad("[[Index]]"),
            _bad("[[NIKHIL_SAREEN|Nik]]"),
        ])
        self.assertEqual(site.pages["about"].html,
                         "<p>[[About]] [[NIKHIL_SAREEN|Nik]] [[Index]] "
                         "<a href=\"about.html\">about</a></p>\n")
        self.assertEqual(site.pages["about"].links, ["about"])
        self.assertEqual(site.pages["about"].backlinks, [])
        self.assertEqual(site.pages["nikhil_sareen"].backlinks, [])
        self.assertEqual(site.pages["index"].backlinks, [])
        self.assertEqual(site.wanted, {})
        self.assertFalse(os.path.exists(self.out))


if __name__ == "__main__":
    unittest.main()
