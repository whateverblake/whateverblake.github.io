---
layout: default
series: true
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

## Source baseline

Excerpts are checked against the [ZooKeeper 3.6.2 source tree](https://github.com/apache/zookeeper/tree/803c7f1a12f85978cb049af5e4ef23bd8b688715) (October 2020). They keep the original selection of code; ellipses mark omissions, so they are not complete compilable methods. Articles note technical corrections and version differences where necessary.
