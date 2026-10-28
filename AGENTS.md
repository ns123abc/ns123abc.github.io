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

### Front matter

- `title`
- `parent`
- `created`
- `date` (log entries only)
- `date_approx` (`true` or `false`)
- `summary`
- `aliases` (reserved; unused in M2)

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

### List lines

`- **Title**: Creator. Year` under `## YYYY` headings.

### Build command

`python3 build.py` writes `site/` and exits non-zero on errors. The one dependency, `markdown-it-py`, is pinned in `requirements.txt`.

### Site model

- `pages[slug]`, with fields:
  - `slug`
  - `title`
  - `parent`
  - `kind`: `page`, `log` or `list`
  - `created`: from front matter
  - `date`: from front matter, log entries only
  - `updated`: last edited, from git
  - `summary`
  - `body_md`
  - `html`
  - `links`
  - `backlinks`
- `wanted[slug]`: the set of pages linking to `slug`, for link targets that have no page.
- `BASE_URL`: a single constant, defaulting to `https://ns123abc.github.io`.

### HTML skeleton

What `templates/page.html` emits (W4) and `main.css` styles (W2):

```html
<header><a href="index.html"><img src="images/mlogo.jpg" alt="NEO — home"></a></header>
<nav class="main-nav"><ul><li><a href="x.html" aria-current="page">x</a></li></ul></nav>
<main><h1>Title</h1> ...prose... <a class="wanted" href="wanted.html#slug">text</a>
  <section class="incoming"><b>incoming</b>: <a href="y.html">y</a></section></main>
<footer class="foot-nav"> ...icons... <span>...</span></footer>
```

- The current page's nav link carries `aria-current="page"`.
- A wikilink whose target has no page renders as `a.wanted`, pointing at `wanted.html#slug`.
- `section.incoming` lists the pages that link here.
