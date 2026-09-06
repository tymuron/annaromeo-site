# annaromeo.design — static mirror, off Tilda

The site Anna built on Tilda (project 1768115, published at `annaromeo.tilda.ws`)
frozen into plain HTML/CSS/JS/images that any static host can serve. No page
loads code, styles or images from Tilda any more. Two small JSON calls still
go to Tilda on page load and degrade silently if it disappears (see "What
still depends on Tilda"). The other third parties are Google Fonts, Yandex
Metrika, Vimeo (the background video on /main) and two JS libs from
unpkg/jsdelivr that Anna's custom code on /main uses.

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
2. `tools/crawl.py site --localise-file <page>` — re-runs step 1's rewriting on
   a single page; used on the five service pages, whose product data is inline
   JSON with `https:\/\/`-escaped image URLs.
3. `tools/bake_store.py` — the services catalog on `/main` was rendered by
   Tilda's catalog JS from Tilda's store API. The markup that JS produced in a
   real browser was saved (`tools/rendered/store-main.html`) and baked into the
   page; the `t_store_init` call was removed. The five service pages already
   carried their product JSON inline, so they work as-is.
4. `tools/optimize_images.py` — originals over 2000px were scaled down and
   large JPEGs re-encoded (285 MB -> 186 MB). Tilda never served the originals
   either; its lazyloader requested resized variants.
5. Scripts that fetched more code or images from Tilda at runtime were
   pointed at local copies: the cart's icon SVGs and its lazily loaded
   discounts/delivery/fullscreen files (`t_catalog__getStaticHost` now returns
   `/assets/static`), the phone-mask flag sprite, and `tilda-forms-payments`.
   Tilda's statistics beacon (`tilda-stat-1.0.min.js`) is an empty stub.
   `tilda-menusub` is loaded `defer` instead of `async` because its top-level
   code needs `t_throttle` from `tilda-scripts` (a race Tilda's CDN usually
   wins; a fast host loses it and the submenu script dies).
6. `tools/check_site.py site` — every local reference resolves to a file
   (2996 references across 44 pages, including inline-script and JSON-escaped
   paths); the only unresolved links are the ones already dead on Tilda.
7. `tools/verify_all.py --all` — for every page, live Tilda vs local mirror in
   headless Chrome: same block list, same height, no console errors, no failed
   requests, no Tilda hosts contacted, pixel diff of the full-page screenshot.
   Result: 43 of 44 pages match, desktop and mobile. The pixel differences that
   remain are all animations caught mid-cycle in the two captures, verified by
   eye: the Vimeo background video on `/main` and the auto-advancing galleries
   on `page21808464.html` and `page21808644.html`. The 44th is
   `page65586091.html` (see "Leftover template pages").
   The checker also matches accepted Tilda calls on the full URL and the host,
   so an analytics beacon carrying "tilda" in a query parameter is not
   mistaken for a Tilda dependency.
   Two known non-differences the checker ignores: Tilda's invisible skip-link
   label (its language races on `window.browserLang`, so it flips both ways
   between runs) and console errors that the live site produces too.

## What still depends on Tilda (decide before cancelling the Tilda plan)

* **Forms** post into the Tilda project's lead inbox (XHR to
  `forms.tildaapi.one`, with `forms2.tildacdn.com` as a fallback), so they keep
  working only while the Tilda project exists. Replace with an own endpoint
  (Telegram bot, Formspree, a tiny Render web service) before the subscription
  ends. The full list, which is wider than it looks:
  - static `<form data-formactiontype="2">`: `/` (3), `/uslugi_vastu` (3),
    `/offer` (3, both popups redirect to a Telegram post on success), `/main`
    (3), `/anketa` (1), the five `/main/tproduct/*` pages, `/fs`,
    `/page79481866.html`;
  - a contact form that only exists after JS runs, so no grep finds it, on
    `404.html`, `/error-page` and `/page68596975.html` — and Render serves
    `404.html` for every unmatched path, so this one is live on the whole site.
* **"Записаться" on the service cards** opens Tilda's cart, whose checkout also
  posts to Tilda. Same caveat; easiest fix is pointing those buttons at the
  /anketa form or a Telegram link.
* Two harmless runtime calls still go to Tilda and fail gracefully if Tilda
  disappears: the phone mask asks `geo.tildaapi.one` for the visitor's country
  (falls back to the form's default country) and the cart asks
  `store.tildaapi.one` for active discounts (logs an error, continues). Both
  are listed as accepted in `tools/verify_page.py`, which matches them on the
  full URL rather than the hostname so nothing else can hide behind them.
* The cart's translations for visitors whose browser is not English or Russian
  (Spanish, in Anna's case) are served from `/assets/static`; eleven language
  dictionaries were downloaded. Verified with a Spanish-locale browser: the
  mirror loads its own copy where the live site fetches Tilda's.
* Tilda hostnames still appear as strings inside the library JS, but every one
  is an unreachable path on this site: error fallbacks, and features no page
  uses (file uploads, delivery services, saved payment fields). The audit
  inventory is in `crawl-report.json`.
* Yandex Metrika counter keeps working from any domain.

## Leftover template pages

`page21808464.html` ("Copy of Bora Headquarters"), `page21808644.html`
("Copy of House Z") and `page65586091.html` ("Flowers") are Tilda template demo
pages that were left published, and all three are in `sitemap.xml`
(`page8023976.html` is the real Diputacio project page and stays).

**`page65586091.html` is the one page that still renders from Tilda at
runtime**: its catalog block queries `store.tildaapi.one/api/getproductslist`
and `getfilters` for a product list that is not Anna's. It already fails on
Tilda itself (the API answers with an error, so the block stays empty there
too). Deleting the three pages and their `sitemap.xml` entries removes the
last runtime call and three junk pages from search results, but they are
Anna's content, so that is her call. They were mirrored as-is; delete them from `site/` and `sitemap.xml`
if Anna confirms they are junk.

## Dead links that were already dead on Tilda

`/uslugi`, `/uslugi/en`, `/uslugi/contacts`, `/policy`, `/oferta`, `/data`,
`/projects`, `/page8861076.html` return 404 on the live site too (pages were
deleted in Tilda). Wayback has copies of some of them (2025) if they should
come back.

## Deploy

Live at **https://annaromeo-design.onrender.com** — Render static site
`annaromeo-design` (service `srv-daepvs0n74is73evrmn0`), auto-deploying from
`main` of this repo. `render.yaml` holds the same settings for anyone
recreating it as a Blueprint. Verified after deploy: all 1318 files serve,
`404.html` is served for unmatched paths with a real 404 status, clean URLs
work with and without a trailing slash, and asset caching is a year.

**Check every deploy.** Render's upload silently dropped seven files on the
first deploy here, including `404.html` and `tilda-animation-2.0.min.css`,
which every page loads. The build log still said the site was live and the
dashboard showed nothing wrong. So after each deploy run:

```
python3 tools/check_deploy.py https://annaromeo-design.onrender.com
```

If it reports missing files, redeploy with the build cache cleared. That fixed
it here, and the second deploy served all 1318 files.

After a custom domain is attached, regenerate canonical, og:url, og:image and
the sitemap for it, then push:

```
python3 tools/set_origin.py site https://<new-domain>
```
