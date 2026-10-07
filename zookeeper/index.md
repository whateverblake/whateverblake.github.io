---
layout: default
series: true
source: "ZooKeeper 3.6.2 · Java"
topic: ZooKeeper
lang: en
title: "Reading ZooKeeper Source Code"
order: 200
description: "Startup, sessions, persistence, leader election, synchronization, and Netty transport in ZooKeeper 3.6.2."
---

# Reading ZooKeeper Source Code

ZooKeeper's source code is well worth studying. It is less complex than many open-source projects, yet there is a great deal to learn from it. The series starts with a standalone server (startup, sessions, request processing, watches, and persistence) and then builds on that to examine an ensemble: leader election and replication.

## Read the series

{% include part-list.html topic="ZooKeeper" descriptions=true %}
