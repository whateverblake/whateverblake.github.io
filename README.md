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
- `topic` groups articles. A new topic appears automatically when used.
- `order` controls the reading order; use different numbers for each article.
  Mooncake uses 10–40. Linux currently uses 100.
- `description` is the short text shown on the article card.
- Optional `nav_title` provides a shorter card title.
- Optional `series_order` labels a numbered chapter. Zero is supported.
- Optional `lang`, such as `zh-CN`, sets the page language.

Keep a visible `# Article title` in the Markdown body. Use `##` for main
sections; pages with three or more main sections receive an expandable
“On this page” navigation. Tables scroll on small screens.

For example, `systems/my-article.md` is published at
`/systems/my-article.html`. Use relative `.html` links between articles.
Place diagrams next to articles, for example in `systems/assets/`.

The Mooncake series has an additional curated introduction at
`mooncake/index.md`. Its reading list is maintained in that file.

## Layout files

- `_layouts/home.html`: article index, grouped by topic.
- `_layouts/default.html`: shared header, full-width article area, and footer.
- `assets/css/site.css`: responsive styles for desktop and mobile.
- `assets/js/site.js`: article section navigation and scrollable tables.

After pushing changes, check **Actions → pages build and deployment** on
GitHub. The homepage lists articles during the Jekyll build; it does not
need a browser-side database or a manually maintained card list.

## Historical Java source series

The `zookeeper/` and `netty/` folders contain the English Jianshu migration:
12 ZooKeeper pages and 11 Netty/Java pages, with 69 local English SVG figures.
The series indexes are `zookeeper/index.md` and `netty/index.md`; both use the
existing layout and appear in the homepage topic list.

The historical baselines are ZooKeeper 3.6.2, Netty 4.1.53.Final, and OpenJDK
8u272-b10. The pooled-memory walkthrough explicitly uses the legacy Netty
4.1.50.Final allocator and describes the 4.1.53 redesign. Source references
use immutable commits. Reconstructed figures are labeled and carry source
links; examples of runtime values are illustrative.

`_migration/` retains the original-to-English article manifest, figure
provenance, translation and review notes, and figure-generation scripts.
Jekyll excludes this internal directory from the published site.
