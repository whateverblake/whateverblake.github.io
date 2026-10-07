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

I recently finished this Netty source-code walkthrough and hope it provides a useful starting point for discussion. These articles follow networking, memory allocation, object reuse, and related Java internals through the source.

## Read the series

{% include part-list.html topic="Netty" descriptions=true %}

## Source versions

The networking and Recycler articles use **Netty 4.1.53.Final**, released October 13, 2020. The pooled-memory article preserves the original **Netty 4.1.50.Final legacy allocator** and explains how 4.1.53 differs. The Java reference-processing and zero-copy articles use **OpenJDK 8u272-b10** for their Java implementation references. These are historical source walkthroughs.

- [Netty 4.1.53.Final source tree](https://github.com/netty/netty/tree/d4a0050ef33cab2542a80e11489a4977a63859f8)
- [Netty 4.1.50.Final legacy allocator source](https://github.com/netty/netty/tree/8c5b72aaf02e7f349a9972dd9179b449b5a6067b)
- [OpenJDK 8u272-b10 source tree](https://github.com/openjdk/jdk8u/tree/c3b5603e949d6272d777ef57952833672a97b4e3)
