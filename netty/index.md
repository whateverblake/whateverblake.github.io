---
layout: default
article: true
topic: Netty
lang: en
title: "Reading Netty Source Code"
description: "A guided series on Netty networking, pooled memory, object recycling, and related Java internals."
order: 400
series_order: 0
---

# Reading Netty Source Code

I recently finished this Netty source-code walkthrough and hope it provides a useful starting point for discussion. These articles follow networking, memory allocation, object reuse, and related Java internals through the source.

## Read the series

| Article | Topic |
| --- | --- |
| [1. Understanding the Netty Thread Model](thread-model.html) | Trace event-loop selection, worker startup, and shared I/O and task scheduling. |
| [2. Following Netty Server Startup](server-startup.html) | Follow channel construction, registration, pipeline initialization, port binding, and connection acceptance. |
| [3. How Netty Pipeline Events Travel Through Handlers](pipeline.html) | Follow inbound and outbound event propagation through handler contexts and channel initializers. |
| [4. How NioSocketChannel Reads Data](socket-read.html) | Trace selector readiness, receive buffers, the read loop, and adaptive buffer sizing. |
| [5. How NioSocketChannel Writes and Flushes Data](socket-write.html) | Follow queued outbound buffers, gathering writes, flush promises, and socket backpressure. |
| [6. Handling Fragmented and Coalesced Messages in Netty](message-framing.html) | Understand TCP stream boundaries and length-field decoding across fragmented and coalesced reads. |
| [7. How Netty Allocates and Reuses Pooled Memory](pooled-memory.html) | Read the legacy arena, chunk, page, and subpage allocator, and compare the redesigned October 2020 implementation. |
| [8. How Netty Recycler Reuses Objects Across Threads](recycler.html) | Explore per-thread object stacks, cross-thread return queues, scavenging, and reuse limits. |
| [9. How Java Processes Soft, Weak, and Phantom References](java-reference-processing.html) | Follow OpenJDK 8 reference reachability, the Reference Handler thread, cleaners, and reference queues. |
| [10. Understanding Java Zero-Copy with sendfile and mmap](java-zero-copy.html) | Compare Java socket copying, FileChannel.transferTo, and memory-mapped file access. |

## Source versions and figures

The networking and Recycler articles use **Netty 4.1.53.Final**, released October 13, 2020. The pooled-memory article preserves the original **Netty 4.1.50.Final legacy allocator** and explains how 4.1.53 differs. The Java reference-processing and zero-copy articles use **OpenJDK 8u272-b10** for their Java implementation references. These are historical source walkthroughs.

All illustrations are local English SVG files. Click a diagram to open it at full size. Diagrams from the original articles are reproduced with English labels. Missing debugger screenshots have been replaced with source excerpts or explanatory diagrams, which are labeled as reconstructions.

- [Netty 4.1.53.Final source tree](https://github.com/netty/netty/tree/d4a0050ef33cab2542a80e11489a4977a63859f8)
- [Netty 4.1.50.Final legacy allocator source](https://github.com/netty/netty/tree/8c5b72aaf02e7f349a9972dd9179b449b5a6067b)
- [OpenJDK 8u272-b10 source tree](https://github.com/openjdk/jdk8u/tree/c3b5603e949d6272d777ef57952833672a97b4e3)
