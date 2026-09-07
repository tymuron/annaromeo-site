#!/usr/bin/env python3
"""
Build the standalone Vastu site from the full annaromeo.design mirror.

The Vastu offering lives at /main on the big mirror. On its own domain it has
to be the home page, so this script lifts /main and everything it links to
into a separate, self-contained site whose root IS that page.

  page in the mirror                                   becomes
  ---------------------------------------------------  --------------------
  /main                                                /
  /main/tproduct/<recid>-<uid>-<slug>   (5 services)   /<slug>
  /mk-vastudesign                                      /mk-vastudesign
  /classpaper                                          /classpaper
  404.html                                             404.html

Only the assets these pages actually use are copied, so the result is about
15 MB rather than the 187 MB of the full mirror. Stylesheets and scripts are
copied whole (they are small) because several are fetched lazily by name at
runtime and would not be found by scanning the HTML.

The flagship course is a separate project (~/vastu-course-site). With
--course it is folded in at /course: its asset paths are all relative, so the
files drop straight in with no collision, and only its metadata and the links
to the dead annaromeo.design domain are rewritten.

Usage:
  python3 tools/build_vastu.py <out_dir> --origin https://annaromeovastu.com \
      [--course ~/vastu-course-site]
"""
import html
import os
import re
import shutil
import sys

SRC = "site"

# The Tilda page shipped no og:image and an empty og:description, so a shared
# link showed a bare URL. Both are filled in here. The description is Anna's
# own wording from the page, not invented copy.
OG_IMAGE = "/assets/og-preview.jpg"
OG_DESCRIPTION = ("Создаю интерьеры, которые наполняют энергией. "
                  "Профессиональный дизайнер-архитектор с 15-летним опытом, "
                  "проекты в Лондоне, Дубае и по всей Европе.")
# whole directories to copy: small, and their contents are loaded by name at
# runtime (lazy cart/catalog/forms helpers, fonts, per-page css+js).
BULK_DIRS = ["assets/static/css", "assets/static/js", "assets/static/lib", "assets/static/ws"]

PATH_RE = re.compile(r"/assets/[^\"'\s)\\<>]+")
ESC_PATH_RE = re.compile(r"\\/assets(?:\\/[^\"\\\s]+)+")
CSS_URL_RE = re.compile(r"url\(\s*['\"]?(/assets/[^)'\"\s]+)['\"]?\s*\)")


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def product_pages():
    base = os.path.join(SRC, "main", "tproduct")
    out = {}
    for d in sorted(os.listdir(base)):
        if not os.path.isdir(os.path.join(base, d)):
            continue
        # <recid>-<uid>-<slug>  ->  <slug>
        m = re.match(r"^\d+-\d+-(.+)$", d)
        out[d] = m.group(1) if m else d
    return out


def main():
    out_root = sys.argv[1]
    origin = (arg("--origin", "https://annaromeovastu.com")).rstrip("/")
    site_out = os.path.join(out_root, "site")
    if os.path.exists(site_out):
        shutil.rmtree(site_out)
    os.makedirs(site_out)

    prods = product_pages()
    pages = [(os.path.join(SRC, "main", "index.html"), "index.html", "/")]
    for src_dir, slug in prods.items():
        pages.append((os.path.join(SRC, "main", "tproduct", src_dir, "index.html"),
                      os.path.join(slug, "index.html"), "/" + slug))
    for name in ("mk-vastudesign", "classpaper"):
        pages.append((os.path.join(SRC, name, "index.html"),
                      os.path.join(name, "index.html"), "/" + name))
    pages.append((os.path.join(SRC, "404.html"), "404.html", None))

    def rewrite_links(doc):
        # product pages first, so the plain /main rule cannot eat their prefix
        for src_dir, slug in prods.items():
            doc = doc.replace(f"/main/tproduct/{src_dir}", f"/{slug}")
            doc = doc.replace(f"\\/main\\/tproduct\\/{src_dir}", f"\\/{slug}")
        doc = re.sub(r'href="/main(?=["#?])', 'href="/', doc)
        doc = doc.replace('href="/main"', 'href="/"')
        doc = re.sub(r'(?<![\w/])/main(?=["\'#?])', "/", doc)
        return doc

    def add_link_preview(doc, path):
        """Give the home page a preview image and description; make sure every
        page advertises a large summary card."""
        img = origin + OG_IMAGE
        if path == "/":
            if '<meta property="og:image"' not in doc:
                doc = doc.replace('<meta property="og:type"',
                                  f'<meta property="og:image" content="{img}" />\n'
                                  '<meta property="og:image:width" content="1200" />\n'
                                  '<meta property="og:image:height" content="630" />\n'
                                  '<meta property="og:type"', 1)
            doc = re.sub(r'<meta property="og:description" content="\s*"',
                         f'<meta property="og:description" content="{OG_DESCRIPTION}"', doc)
            if '<meta name="description"' not in doc:
                doc = doc.replace("<title>", f'<meta name="description" content="{OG_DESCRIPTION}" />\n<title>', 1)
            else:
                doc = re.sub(r'<meta name="description" content="\s*"',
                             f'<meta name="description" content="{OG_DESCRIPTION}"', doc)
        if "twitter:card" not in doc:
            doc = doc.replace('<meta property="og:type"',
                              '<meta name="twitter:card" content="summary_large_image" />\n'
                              '<meta property="og:type"', 1)
        return doc

    def set_origin(doc, path):
        if path is None:
            # a 404 page should not canonicalise anywhere, least of all at the
            # other site it was mirrored from
            doc = re.sub(r'<link rel="canonical" href="[^"]*">\s*', "", doc)
            doc = re.sub(r'(<meta property="og:url" content=")[^"]*(")', r"\g<1>" + origin + r"\g<2>", doc)
        if path is not None:
            canon = origin + ("" if path == "/" else path)
            doc = re.sub(r'(<link rel="canonical" href=")[^"]*(")', r"\g<1>" + canon + r"\g<2>", doc)
            doc = re.sub(r'(<meta property="og:url" content=")[^"]*(")', r"\g<1>" + canon + r"\g<2>", doc)
        doc = re.sub(r'(<meta property="og:image" content=")(?:https?://[^"/]+)?(/[^"]*)(")',
                     lambda m: m.group(1) + origin + m.group(2) + m.group(3), doc)
        return doc

    wanted = set()

    def clean(ref):
        # a CSS url() inside an HTML attribute arrives as
        # url(&quot;/assets/...jpg&quot;), so unescape first, then trim the
        # quote the entity leaves behind. Missing this silently skipped five
        # product thumbnails on the first build.
        return html.unescape(ref).split("?")[0].strip().strip("\"')")

    def note_assets(text):
        for r in PATH_RE.findall(text):
            wanted.add(clean(r))
        for m in ESC_PATH_RE.findall(text):
            wanted.add(clean(m.replace("\\/", "/")))

    written = []
    for src, rel, path in pages:
        doc = open(src, encoding="utf-8").read()
        doc = set_origin(add_link_preview(rewrite_links(doc), path), path)
        note_assets(doc)
        dest = os.path.join(site_out, rel)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        open(dest, "w", encoding="utf-8").write(doc)
        written.append((rel, path))

    # bulk directories (css/js/lib/ws), then the images the pages and those
    # stylesheets reference
    for d in BULK_DIRS:
        s, t = os.path.join(SRC, d), os.path.join(site_out, d)
        if os.path.isdir(s):
            shutil.copytree(s, t)
            for dd, _, fs in os.walk(t):
                for f in fs:
                    if f.endswith((".css", ".js")):
                        note_assets(open(os.path.join(dd, f), encoding="utf-8", errors="replace").read())

    copied = missing = 0
    total = 0
    for ref in sorted(wanted):
        if any(ref.startswith("/" + d) for d in BULK_DIRS):
            continue
        s = os.path.join(SRC, ref.lstrip("/"))
        t = os.path.join(site_out, ref.lstrip("/"))
        if not os.path.isfile(s):
            missing += 1
            continue
        if os.path.exists(t):
            continue
        os.makedirs(os.path.dirname(t), exist_ok=True)
        shutil.copy2(s, t)
        total += os.path.getsize(t)
        copied += 1

    # the flagship course, served at /course
    course_src = arg("--course")
    if course_src:
        course_src = os.path.expanduser(course_src)
        cdest = os.path.join(site_out, "course")
        os.makedirs(cdest, exist_ok=True)
        shutil.copytree(os.path.join(course_src, "assets"), os.path.join(cdest, "assets"))
        cdoc = open(os.path.join(course_src, "index.html"), encoding="utf-8").read()
        curl = origin + "/course"
        # its own domain metadata -> this domain
        cdoc = re.sub(r'(<meta property="og:url" content=")[^"]*(")', r"\g<1>" + curl + r"\g<2>", cdoc)
        cdoc = re.sub(r'(<link rel="canonical" href=")[^"]*(")', r"\g<1>" + curl + r"\g<2>", cdoc)
        cdoc = cdoc.replace("https://annaromeo-vastu-course.onrender.com/assets", curl + "/assets")
        cdoc = re.sub(r'(<meta property="og:image" content=")https?://[^"]*?/assets',
                      r"\g<1>" + curl + "/assets", cdoc)
        if '<link rel="canonical"' not in cdoc:
            cdoc = cdoc.replace("<title>", f'<link rel="canonical" href="{curl}">\n<title>', 1)
        # annaromeo.design expired; its Vastu content is this site now
        cdoc = cdoc.replace('href="https://annaromeo.design/main#oferta"', f'href="{origin}/#oferta"')
        cdoc = cdoc.replace('href="https://annaromeo.design"', f'href="{origin}"')
        cdoc = cdoc.replace(">annaromeo.design<", ">annaromeovastu.com<")
        open(os.path.join(cdest, "index.html"), "w", encoding="utf-8").write(cdoc)
        n = sum(1 for d, _, fs in os.walk(cdest) for _ in fs)
        mb = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(cdest) for f in fs) / 1e6
        written.append(("course/index.html", "/course"))
        print(f"course  : /course  ({n} files, {mb:.0f} MB) from {course_src}")

    # the preview card itself
    og_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "og-preview.jpg")
    if os.path.isfile(og_src):
        shutil.copy2(og_src, os.path.join(site_out, OG_IMAGE.lstrip("/")))
        print(f"link preview: {OG_IMAGE} ({os.path.getsize(og_src)/1024:.0f} KB)")
    else:
        print(f"WARNING: {og_src} missing, pages will reference an absent og:image")

    # robots + sitemap
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for rel, path in written:
        if path is None:
            continue
        loc = origin + ("" if path == "/" else path)
        sitemap.append(f"  <url><loc>{html.escape(loc)}</loc></url>")
    sitemap.append("</urlset>\n")
    open(os.path.join(site_out, "sitemap.xml"), "w").write("\n".join(sitemap))
    open(os.path.join(site_out, "robots.txt"), "w").write(
        "User-agent: *\nDisallow: /404.html\n\nSitemap: %s/sitemap.xml\n" % origin)

    print(f"pages   : {len(written)}")
    for rel, path in written:
        print(f"  {str(path):40} <- {rel}")
    print(f"images  : {copied} copied ({total/1e6:.1f} MB), {missing} referenced but absent")
    print(f"total   : {sum(os.path.getsize(os.path.join(d,f)) for d,_,fs in os.walk(site_out) for f in fs)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
