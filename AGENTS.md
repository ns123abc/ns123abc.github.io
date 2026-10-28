# AGENTS.md

Rules and the shared contract for every agent (and human) working in this repo. `CLAUDE.md` points here; this file is the source of truth.

This repo is NEO, Nikhil Sareen's personal wiki, published by GitHub Pages at https://ns123abc.github.io. The repo is public and its git history is permanent.

## Rules

1. **Never change the user's words.** No rewording, copy-editing, typo or spelling fixes. Spelling fixes happen only when the user asks, as a separate PR the user reviews line by line. Markup fixes and migrations keep every word: the multiset of visible words on each page stays identical, apart from additions the user approved.
   - **Inherited text** (prose and nav taxonomy that came from XXIIVV, and the Vannevar Bush quote on `about`) isn't the user's writing, but treat it the same way. The user decides what stays, gets rewritten or gets credited; change it only on the user's explicit instruction.
2. **No private data in this repo, ever.** Anything pushed stays in history, forks and archives, even after deletion. No journals, messages, contacts, health or money records, raw data exports, or other people's words without their consent. Strip EXIF from every image you add. The public site makes no third-party requests: no Google Fonts, no analytics.
   - Personal details already on the pages (the email address and age on `nikhil_sareen`) are the user's words. Leave them untouched until the user decides.
3. **One owner per file.** See the ownership list below. If you need a change in someone else's file, write it in your PR description; don't edit the file.
4. **PRs only. Never push to `main`.** The Pages build publishes every commit on `main` instantly. Each PR touches only its owner's files, is rebased on `main` before review, and has one commit per kind of change so any piece can be reverted.
5. **Code against the contract below,** not against someone else's unmerged code; nobody waits on anyone. If the contract looks wrong, say so in your PR description instead of diverging from it.
6. **Image filenames don't change before M2** (the switch to the generated Markdown site). Images are shrunk in place under the same paths, so no HTML or Markdown edits are needed for images.
7. **Never re-serialize HTML.** Parsing a page with BeautifulSoup (or anything else) and writing it back rewrites every line. Edits to the legacy HTML are exact string replacements only.
8. **Keep `.nojekyll`.** Without it the legacy Pages build runs Jekyll, which chokes on `.md` files containing template syntax like `{{ }}` or `{% %}`. A failed Jekyll build silently freezes the live site.

### File ownership

These are the workstreams of the revival sprint.

| Owner | Files |
| --- | --- |
| W0 contract and rules | `AGENTS.md`, `CLAUDE.md`, `.nojekyll`, `.gitignore`, `requirements.txt` |
| W1 assets | `images/`, the zip, root `restore.jpeg`, `tools/add_image.py` |
| W2 look | `main.css`, `fonts/` |
| W3 legacy HTML fixes | root `*.html`, until W3 merges (the "HTML freeze") |
| W4 build core | `build.py`, `templates/`, `tests/test_build.py` |
| W5 CI and deploy | `.github/workflows/` |
| W6 content conversion | `content/` |
| W7 generated pages | `extras.py`, `tests/test_extras.py` |
| W8 flip and cleanup | deleting root `*.html`, and `README.md` |

## Contract

Every workstream codes against this. Change it only through a PR to this file.

### Slugs

A slug is the old filename lowercased (`nikhil_sareen`, `datascience`), from the characters `[a-z0-9_-]`. Renaming nothing means changing nothing.

### Paths

- Pages: `content/<slug>.md`.
- Log entries: `content/log/YYYY-MM-DD.md`.

### Log entries

- The slug is the file name: `content/log/2022-08-29.md` is `pages["2022-08-29"]`, with `kind: log`.
- Each entry gets its own flat page, `2022-08-29.html`, so `[[2022-08-29]]` works like any other link.
- One file per day. A second entry on the same day goes into that day's file, so slugs can't collide.
- The file name is the date, and it has to be a real calendar day (`2022-02-30.md` is an error). `date` defaults to it, and if `date` is written it must match. For an entry about the past, name the file by that date and set `date_approx: true`.
- Log entries never appear in the nav.

### Front matter

- `title`
- `parent`
- `created`
- `date` (log entries only)
- `date_approx` (`true` or `false`)
- `summary`
- `aliases` (reserved; unused in M2)

Required and optional:

- Pages: only `title` is required.
- Log entries: nothing is required, and the front matter block itself is optional. `title` defaults to the date.
- `created`, when present, is a real calendar day in `YYYY-MM-DD`. `2022-02-30` is an error.
- `date` is allowed only on log entries.
- `date_approx` defaults to `false`.
- `parent` must name an existing page, with no cycles. Top-level pages have no `parent`; `parent: index` is an error.
- `aliases` is accepted and ignored.
- `summary` is optional, and only the user writes it. Agents and the build never write or derive one.
- Unknown or duplicate keys are errors. An empty value means the key is absent. One pair of surrounding quotes is stripped.

Front matter is a flat `key: value` subset between `---` lines, parsed by the build itself, so there's no YAML dependency. For example:

```yaml
---
title: Dostoevsky
parent: reading
created: 2022-08-29
---
```

### Wikilinks

`[[slug]]` and `[[slug|text]]`, with the target equal to the slug. Inside tables, write `[[slug\|text]]`.

A bare `[[slug]]` displays the slug as typed, as in Obsidian, so `[[nikhil_sareen]]` shows "nikhil_sareen". Use `[[slug|text]]` unless the text equals the slug exactly. When converting an existing link, the text is the old link text, unchanged.

### List lines

`- **Title**: Creator. Year` under `## YYYY` headings.

### Kinds

The build assigns `kind` from where the file sits and from its headings.

- A `content/<slug>.md` file whose body has a level-2 heading of four digits (`## 2022`) is a `list`. Any other `content/<slug>.md` file is a `page`. A year line inside a code fence, and a `###` heading, leave the file a `page`.
- A `content/log/YYYY-MM-DD.md` file is a `log`. A year heading in the body leaves it a `log`.

### Build command

`python3 build.py` writes `site/` and exits non-zero on errors. The one dependency, `markdown-it-py`, is pinned in `requirements.txt`.

When `content/` is not a directory, the build warns (`content/: missing, so there is nothing to build and site/ is left alone`), writes nothing, leaves an existing `site/` in place, and exits 0. An empty `content/` directory is still loaded. After `extend` (see Hooks), the build requires an `index` page; without one it errors (`content/index.md` missing) and stops before writing `site/`.

### Site model

- `pages[slug]`, with fields:
  - `slug`
  - `title`
  - `parent`
  - `kind`: `page`, `log` or `list`, assigned as in Kinds
  - `created`: from front matter
  - `date`: the log file name; empty on pages and lists
  - `date_approx`: from front matter, default `false`
  - `updated`: the git author date (`YYYY-MM-DD`) of the newest commit that touches the source file. Empty when the file has no commit, when git can't be read, or on a shallow clone. A shallow clone warns (`clone with fetch-depth: 0`) and the build still succeeds.
  - `path`: source path relative to the repo root (`content/about.md`, `content/log/2022-08-29.md`). Empty on a page a hook adds.
  - `summary`
  - `body_md`
  - `html`
  - `links`
  - `backlinks`
- `wanted[slug]`: the set of pages linking to `slug`, for link targets that have no page.
- `BASE_URL`: a single constant, defaulting to `https://ns123abc.github.io`.

### Hooks

`extras.py` at the repo root is optional. Hooks can `import build`. When that module defines them, the build calls:

- `extend(site)`, after pages are loaded and `updated` is filled, before wikilinks are resolved and HTML is rendered. It may add pages to `site.pages` or edit `body_md`. A page it adds keeps the `kind` and `updated` the hook sets; the default `kind` is `page`. Editing `body_md` here leaves `kind` as it was at load.
- `build(site, out)`, after the HTML pages are written and before the broken-link check. `site.render(page)` returns a full HTML page. `site.write(path, data)` adds a file under the output directory. Writing one path twice is an error.

A missing `content/` directory skips both. Load errors skip `extend`. Errors while resolving links (a missing `index`, a bad `parent`, a bad wikilink) come after `extend`; `build` is skipped and `site/` stays unwritten.

### HTML skeleton

What `templates/page.html` emits (W4) and `main.css` styles (W2):

```html
<header><a href="index.html"><img src="images/mlogo.jpg" alt="NEO — home"></a></header>
<nav class="main-nav"><ul><li><a href="x.html" aria-current="page">x</a></li></ul></nav>
<main><h1>Title</h1> ...prose... <a class="wanted" href="wanted.html#slug">text</a>
  <section class="incoming"><b>incoming</b>: <a href="y.html">y</a></section></main>
<footer class="foot-nav"> ...icons... <span>...</span></footer>
```

- A wikilink whose target has no page renders as `a.wanted`, pointing at `wanted.html#slug`.
- `section.incoming` lists the pages that link here.

The `<head>`, in this order (the description meta appears only when `summary` is set):

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — NEO</title>
<meta name="description" content="{summary}">
<link rel="stylesheet" href="main.css">
<link rel="icon" href="images/favicon.png" type="image/png">
</head>
```

- The icon is `images/favicon.png`, a 64 px PNG of about 4 KB. Never point pages at `images/slogo7.png`, which is about 400 KB.

- The title is always `{title} — NEO`, including on the home page.
- No canonical link, no feed link and no `BASE_URL` in pages, so pages stay domain-independent.

The nav uses XXIIVV-style columns:

- One `<ul>` of top-level pages, then one `<ul>` per level down to the current page, then one `<ul>` of the current page's children.
- The current page's link carries `aria-current="page"`. Each ancestor on the path is `<a class="parent" href="x.html">`.
- Items are sorted by slug, and the link text is the page title. `index` and log entries are never listed.
