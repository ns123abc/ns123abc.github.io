# Deploy

`https://ns123abc.github.io` is GitHub Pages for this repo. Publishing is still the legacy branch build: the root of `main` goes live on every push. `.github/workflows/deploy.yml` is the Actions publisher. It is manual (`workflow_dispatch` only). It runs `python3 build.py` and deploys the `site/` directory.

Leave every root `*.html` file in git. Rollback serves those files. Deleting them is a later change, after the Actions site has stayed green.

## Flip

Do this in one sitting, as a repo admin. Do not push `main`.

1. On the commit you will publish, `content/index.md` and `extras.py` exist, `python3 build.py` writes `site/index.html`, and a `Check` artifact (`site-preview`) contains that tree plus `main.css`, `fonts/silkscreen-regular.woff2`, and `images/mlogo.jpg`. If `content/` is missing, `build.py` exits 0 and writes nothing: stop.
2. Note `git rev-parse origin/main`.
3. **Settings → Pages → Build and deployment → Source → GitHub Actions.** If GitHub offers to commit a starter workflow, close it. `deploy.yml` is already on `main`.
4. Fetch. If the SHA changed, stop. Do not run Deploy.
5. **Actions → Deploy → Run workflow**, branch **`main`**. Other branches fail the deploy job (the `github-pages` environment allows `main` only).
6. When both jobs are green, request the live URLs with a cache miss (`cache-control: max-age=600`). `index.html`, `about.html`, `main.css`, and `images/mlogo.jpg` return 200. `DataScience.html`, `Descartes.html`, and `Dostoevsky.html` return 404; the generated names are lowercase.

Until a later PR adds a push trigger, run Deploy again after each merge.

## Rollback

1. Cancel queued and in-progress **Deploy** runs (`cancel-in-progress` is false).
2. **Settings → Pages → Source → Deploy from a branch → `main` → `/ (root)` → Save.**
3. Wait until the Pages API shows `build_type` `legacy`, `status` `built`, source branch `main`, path `/`. Then `index.html` and `DataScience.html` return 200.

## Risks

1. Flipping with no `content/` uploads nothing useful and freezes publishing.
2. Deleting root HTML in the same change makes rollback publish an empty site.
3. The settings UI can commit a second workflow straight to `main`.
4. Deploy from any branch other than `main` fails at the environment.
5. An in-flight Deploy can finish after rollback and publish the artifact again.
6. A cached 200 (`max-age=600`) can be the previous site for ten minutes.
7. The artifact is `site/` only (`main.css`, `fonts/`, `images/`). A missing file breaks every page.
8. The three capitalised HTML URLs 404 on purpose after a good flip.
9. `main` has no ruleset, so a merge during the sitting races the legacy publisher.
10. Leaving after the source switch, before a green Deploy, freezes the site. Changing the custom domain in the same sitting writes a `CNAME` commit and does not belong here.
