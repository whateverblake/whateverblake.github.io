---
layout: default
series: true
source: "Netty 4.1.53 · OpenJDK 8"
topic: Netty
lang: en
title: "Reading Netty Source Code"
order: 400
description: "Netty networking, pooled memory, object recycling, and related Java internals."
---

# Reading Netty Source Code

These articles read Netty's source: its threading model, server startup, the pipeline, how sockets read and write, message framing, the pooled memory allocator and the object recycler, plus two Java internals Netty relies on: reference processing and zero-copy I/O.

## Read the series

{% include part-list.html topic="Netty" descriptions=true %}

## Source versions

| Articles | Source version |
| --- | --- |
| Networking and Recycler | **Netty 4.1.53.Final** (October 13, 2020) |
| Pooled memory | **Netty 4.1.50.Final**, the legacy allocator, with the 4.1.53 differences explained |
| Reference processing and zero-copy | **OpenJDK 8u272-b10** |

- [Netty 4.1.53.Final source tree](https://github.com/netty/netty/tree/d4a0050ef33cab2542a80e11489a4977a63859f8)
- [Netty 4.1.50.Final legacy allocator source](https://github.com/netty/netty/tree/8c5b72aaf02e7f349a9972dd9179b449b5a6067b)
- [OpenJDK 8u272-b10 source tree](https://github.com/openjdk/jdk8u/tree/c3b5603e949d6272d777ef57952833672a97b4e3)
