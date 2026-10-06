---
layout: default
article: true
topic: ZooKeeper
lang: en
title: "Reading ZooKeeper Source Code"
order: 200
series_order: 0
description: "A guided series on ZooKeeper startup, sessions, persistence, leader election, synchronization, and Netty transport."
---

# Reading ZooKeeper Source Code

> **Source version.** This English edition checks the original analysis against ZooKeeper 3.6.2, available in October 2020, pinned at commit `803c7f1a12f85978cb049af5e4ef23bd8b688715`. The annotated excerpts retain the original selection and executable logic; ellipses mark omissions and are not complete compilable methods.

## Introduction
ZooKeeper's source code is well worth studying. Compared with many other open source projects, it is less complex and reasonably approachable. At the same time, it contains a great deal to learn from, and reading it rewards the effort. I recommend taking the time to explore it.
## Articles
The following articles grew out of my reading of the standalone ZooKeeper source code. I hope we can study them together and improve our understanding. This English edition also includes the later ensemble articles, so the list covers the complete series.
- [Setting Up a ZooKeeper Source Debugging Environment](debugging-environment.html)
- [How a Standalone ZooKeeper Server Starts](standalone-server-startup.html)
- [How ExpiryQueue Manages Connection and Session Timeouts](expiry-queue.html)
- [How a ZooKeeper Client Starts and Establishes a Session](client-startup.html)
- [Following a ZooKeeper Node Creation Request](node-creation.html)
- [How ZooKeeper Registers and Delivers Watch Events](watch-processing.html)
- [How ZooKeeper Recovers Data from Snapshots and Transaction Logs](data-recovery.html)
- [How ZooKeeper Uses Netty for Client-Server Communication](netty-transport.html)

The ensemble part continues with:

- [Setting Up a Three-Node ZooKeeper Ensemble](ensemble-setup.html)
- [Following ZooKeeper Fast Leader Election](leader-election.html)
- [How ZooKeeper Leaders and Followers Form an Ensemble](leader-follower-initialization.html)

The [Reading ZooKeeper Source Code overview](index.html) is the series entry point. Together with the eleven detailed articles above, it forms the twelve-page series. The standalone topics explain startup, sessions, request processing, watches, and persistence; the ensemble topics build on those foundations to examine election and replication.

## Source baseline

The series checks the original excerpts against the [ZooKeeper 3.6.2 source tree](https://github.com/apache/zookeeper/tree/803c7f1a12f85978cb049af5e4ef23bd8b688715), pinned to an immutable commit. Each article identifies technical corrections or version differences where necessary. The replacement English figures reconstruct structures and control flow from that source instead of presenting missing original screenshots as recovered captures.
