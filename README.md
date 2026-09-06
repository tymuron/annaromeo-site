# annaromeo.design — static mirror, off Tilda

The site Anna built on Tilda (project 1768115, published at `annaromeo.tilda.ws`)
frozen into plain HTML/CSS/JS/images that any static host can serve. Nothing on
these pages is fetched from Tilda at runtime any more; the only third parties
left are Google Fonts, Yandex Metrika, Vimeo (one embedded video on /main) and
two small JS libs from unpkg/jsdelivr that Anna's custom code on /main used.

```
site/          the deployable site (Render publishes this folder)
  index.html   home
  <slug>/index.html   every other page  (/strelna -> strelna/index.html)
  main/tproduct/<id>-<slug>/index.html  the five service pages
  404.html     Tilda's error page
  assets/static/...  everything that lived on static.tildacdn.*
  assets/thb/...     resized thumbnails that lived on thb/optim.tildacdn.*
render.yaml    Render blueprint: static site, publish path `site`
tools/         how the mirror was made (see below)
crawl-report.json  page list, asset count, dead links found on the live site
```

## How it was built (September 2026)

1. `tools/crawl.py site` — fetched every page from the sitemap, the store
   sitemap and the hidden Tilda pages (header/footer/404), downloaded every
   `*.tildacdn.*` asset (also the ones referenced inside CSS, per-page JS and
   JSON-escaped inline data), rewrote all references to `/assets/...`, rewrote
   `annaromeo.design` links to root-relative paths, dropped Tilda's CDN
   fallback loader and dns-prefetch hints, wrote robots.txt + sitemap.xml.
2. `tools/bake_store.py` — the services catalog on `/main` was rendered by
   Tilda's catalog JS from Tilda's store API. The markup that JS produced in a
   real browser was saved (`tools/rendered/store-main.html`) and baked into the
   page; the `t_store_init` call was removed. The five service pages already
   carried their product JSON inline, so they work as-is.
3. `tools/optimize_images.py` — originals over 2000px were scaled down and
   large JPEGs re-encoded (285 MB -> 186 MB). Tilda never served the originals
   either; its lazyloader requested resized variants.
4. Scripts that fetched more code or images from Tilda at runtime were
   pointed at local copies: the cart's icon SVGs and its lazily loaded
   discounts/delivery/fullscreen files (`t_catalog__getStaticHost` now returns
   `/assets/static`), the phone-mask flag sprite, and `tilda-forms-payments`.
   Tilda's statistics beacon (`tilda-stat-1.0.min.js`) is an empty stub.
   `tilda-menusub` is loaded `defer` instead of `async` because its top-level
   code needs `t_throttle` from `tilda-scripts` (a race Tilda's CDN usually
   wins; a fast host loses it and the submenu script dies).
5. `tools/check_site.py site` — every local reference resolves to a file.
6. `tools/verify_all.py --all` — for every page, live Tilda vs local mirror in
   headless Chrome: same block list, same height, no console errors, no failed
   requests, no Tilda hosts contacted, pixel diff of the full-page screenshot.

## What still depends on Tilda (decide before cancelling the Tilda plan)

* **Forms** (`data-formactiontype="2"` on the home, /uslugi_vastu, /anketa and
  the service pages) post to `forms.tildacdn.com`, i.e. into the Tilda
  project's lead inbox and its connected services. They keep working only
  while the Tilda project exists. Replace with an own endpoint (Telegram bot,
  Formspree, a tiny Render web service) before the Tilda subscription ends.
* **"Записаться" on the service cards** opens Tilda's cart, whose checkout also
  posts to Tilda. Same caveat; easiest fix is pointing those buttons at the
  /anketa form or a Telegram link.
* Two harmless runtime calls still go to Tilda and fail gracefully if Tilda
  disappears: the phone mask asks `geo.tildaapi.one` for the visitor's
  country (falls back to the form's default country) and the cart asks
  `store.tildaapi.one` for active discounts (logs an error, continues).
* Yandex Metrika counter keeps working from any domain.

## Leftover template pages

`page21808464.html` ("Copy of Bora Headquarters"), `page21808644.html`
("Copy of House Z") and `page65586091.html` ("Flowers", whose catalog block
errors on Tilda too) look like Tilda template demo pages that were left
published and are in the sitemap (`page8023976.html` is the real Diputacio
project page and stays). They were mirrored as-is; delete them from `site/` and `sitemap.xml`
if Anna confirms they are junk.

## Dead links that were already dead on Tilda

`/uslugi`, `/uslugi/en`, `/uslugi/contacts`, `/policy`, `/oferta`, `/data`,
`/projects`, `/page8861076.html` return 404 on the live site too (pages were
deleted in Tilda). Wayback has copies of some of them (2025) if they should
come back.

## Deploy

Render Blueprint from this repo (`render.yaml`, static site, publish path
`site`). After a custom domain is attached, regenerate canonical/og:url and
sitemap for it:

```
python3 tools/set_origin.py site https://<new-domain>
```
