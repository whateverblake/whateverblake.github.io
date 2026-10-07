# Blake’s engineering notes

GitHub Pages builds this site from the `main` branch. Articles use Markdown.
The shared layouts and CSS control their appearance.

## Add an article

Create a Markdown file in the root folder or a topic folder. Add this header:

```yaml
---
layout: default
title: How my system works
article: true
topic: Systems
order: 200
description: A short explanation of what readers will learn.
---

# How my system works

Write the article here.
```

- `article: true` adds the page to the homepage automatically.
- `topic` names the series. Articles whose topic has a series overview are
  listed under that series; others appear under “Other notes”.
- `order` controls the reading order; use different numbers for each article.
  Mooncake uses 10–40, Linux 100, ZooKeeper 210–310, Netty 410–500.
- `description` is shown in the series overview's part list.
- Optional `nav_title` provides a shorter title for lists and links.
- Optional `series_order` is the part number. Zero is supported.
- Optional `lang`, such as `zh-CN`, sets the page language.

To start a new series, add `<topic>/index.md` with `series: true`, the same
`topic`, an `order`, and a one-line `description`. It then appears in the
header navigation and on the homepage. Put
`{% include part-list.html topic="<topic>" descriptions=true %}`
where the overview should list its parts.

Keep a visible `# Article title` in the Markdown body. Use `##` for main
sections; pages with three or more main sections receive an expandable
“On this page” navigation. Tables scroll on small screens.

For example, `systems/my-article.md` is published at
`/systems/my-article.html`. Use relative `.html` links between articles.
Place diagrams next to articles, for example in `systems/assets/`.

## Layout files

- `_layouts/home.html`: homepage: a short intro and one block per series.
- `_layouts/default.html`: header with series navigation, article area,
  previous/next links within a series, and footer.
- `_includes/part-list.html`: numbered list of a series' articles.
- `assets/css/site.css`: responsive styles for desktop and mobile.
- `assets/js/site.js`: article section navigation and scrollable tables.

After pushing changes, check **Actions → pages build and deployment** on
GitHub. The homepage lists articles during the Jekyll build; it does not
need a browser-side database or a manually maintained card list.

## Historical Java source series

The `zookeeper/` and `netty/` folders contain the English Jianshu migration:
12 ZooKeeper pages and 11 Netty/Java pages, with 69 local English SVG figures.
The series overviews are `zookeeper/index.md`, `netty/index.md` and
`mooncake/index.md` (front matter `series: true`). The homepage, the header
navigation, each overview's part list and the previous/next links on articles
are all generated from front matter (`article: true`, `topic`, `order`,
`series_order`), so a new article only needs those fields.

The historical baselines are ZooKeeper 3.6.2, Netty 4.1.53.Final, and OpenJDK
8u272-b10. The pooled-memory walkthrough explicitly uses the legacy Netty
4.1.50.Final allocator and describes the 4.1.53 redesign. Source references
use immutable commits. 39 figures are the author's original draw.io diagrams
with English labels; the other 30 replace screenshots that could not be
recovered, are labeled as reconstructions, and carry source links. Examples
of runtime values are illustrative.

`_migration/` retains the original-to-English article manifest, figure
provenance, translation and review notes, and figure-generation scripts.
The translated draw.io sources are in `_migration/drawio/`; rebuild their SVGs
with `python3 _migration/drawio_tools/build_figures.py` (needs the draw.io
desktop app). Jekyll excludes this internal directory from the published site.
