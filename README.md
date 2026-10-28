# ns123abc.github.io

This is my personal wiki

NEO, published at https://ns123abc.github.io. The rules and the content contract are in [AGENTS.md](AGENTS.md). This file is how to add a page, a log entry, or a list item, and how to build and deploy.

## Add a page

Create `content/<slug>.md`. The slug is the filename without `.md`: lowercase letters, digits, `_` and `-` (`[a-z0-9_-]`). The old page `Dostoevsky.html` is `content/dostoevsky.md`.

`title` is the only required field. The build uses it for the `<h1>` and for `<title>{title} — NEO`, including on the home page. Leave the body without its own `#` heading.

```markdown
---
title: Dostoevsky
parent: reading
created: 2022-08-29
---

Prose, in CommonMark.
```

Front matter is a flat `key: value` block between `---` lines, parsed by the build. The keys are `title`, `parent`, `created`, `date`, `date_approx`, `summary`, and `aliases`. An unknown key or a duplicate key fails the build. An empty value means the key is absent. One pair of matching quotes around a value is stripped.

- `parent` names a page that already exists. Top-level pages omit it. `parent: index` is an error. A cycle is an error.
- `created` is `YYYY-MM-DD` when you set it.
- `summary` is optional. When you set it, it is the description meta tag. You write it yourself. The build never derives one.
- `aliases` is accepted and ignored.
- `date` belongs on log entries only.

`content/index.md` has to exist, because the logo links to `index.html`. The nav is built from `parent`: one column of top-level pages, then a column for each level down to the current page, then a column of that page's children. Within a column, items are sorted by slug and the link text is the title. `index` and log entries are left out. The current page's link carries `aria-current="page"`. Each ancestor on that path carries `class="parent"`.

The build adds an `incoming` line under the prose, from the pages that link here.

An image is a Markdown image whose file is already in the repo, for example `![alt](images/mlogo.jpg)`. A path with a space goes in angle brackets: `![Fyodor Dostoevsky](<images/Fyodor Dostoevsky.jpeg>)`. A missing image fails the build.

## Add a log entry

Create `content/log/YYYY-MM-DD.md`. The filename is the slug and the date. The built page is `YYYY-MM-DD.html`, so `[[2022-08-29]]` links to it the same way as any other slug.

A file with no front matter is enough. The title is then the date.

```markdown
Read [[dostoevsky|Dostoevsky]].
```

`date` defaults to the filename. When you write `date`, it has to match the filename. For an entry about the past, name the file by that date and set `date_approx: true`.

```markdown
---
title: Mirrors
date_approx: true
---

The entry.
```

That file is `content/log/2022-09-01.md`. The slug stays `2022-09-01`; `title` is only the heading. One file per day. A second entry on the same day goes in that day's file, so the slugs stay unique. Log entries stay out of the nav. `parent` is optional and follows the same rules as on a page.

## Add a list item

A list is a page at `content/<slug>.md` that contains a real `## YYYY` heading. The heading text is the four-digit year alone. The page still needs `title`. A file under `content/log/` stays a log entry. A year heading inside a fenced code block leaves the page as an ordinary page.

Under each year heading, write one item per line, in this shape: `- **Title**: Creator. Year`

```markdown
---
title: reading
parent: directory
---

## 2022

- **Meditations**: Marcus Aurelius. 180
```

## Wikilinks

The target is the slug, and it has to match `[a-z0-9_-]`.

| Write | Visible text |
| --- | --- |
| `[[dostoevsky]]` | `dostoevsky` (the slug as typed) |
| `[[dostoevsky\|Dostoevsky]]` | `Dostoevsky` |

Use the `[[slug|text]]` form whenever the visible text differs from the slug. The text after `|` has to be non-empty. Inside a table cell, escape the pipe so the cell stays intact: `[[dostoevsky\|Dostoevsky]]`.

A target that has a page links to `<slug>.html`. A target that has no page links to `wanted.html#<slug>` with class `wanted`. A wikilink inside inline code or a code block stays as text.

## Build locally

Use Python 3.12 (the version CI uses), from the repository root. The one dependency, `markdown-it-py`, is pinned in `requirements.txt`.

```bash
python3 -m pip install -r requirements.txt
python3 build.py
```

`python3 build.py` writes `site/` and exits non-zero on errors. Until the `content/` directory exists, it warns and leaves `site/` alone. `site/` is gitignored. Open `site/index.html`.

## Deploy

Open a pull request. Never push to `main`. The Pages build publishes every commit on `main`.

Keep `.nojekyll` at the repository root. Without it the legacy Pages build runs Jekyll, which fails on Markdown that contains `{{ }}` or `{% %}`, and a failed Jekyll build freezes the live site.

A merge to `main` publishes the repository root, the HTML files at the top of the repo. That is the live site at https://ns123abc.github.io while Pages deploys from the `main` branch.

The generated `site/` directory is deployed by `.github/workflows/deploy.yml`, which starts only when you run it: **Actions → Deploy → Run workflow**, branch `main`. The workflow checks out the full git history, installs `requirements.txt`, runs `python3 build.py`, and deploys `site/`. Visitors receive that output after **Pages → Build and deployment → Source** is set to GitHub Actions.

A pull request runs `.github/workflows/check.yml`: the build, the tests, and a `site-preview` artifact kept for 14 days when `site/` was written. The pull request does not deploy.
