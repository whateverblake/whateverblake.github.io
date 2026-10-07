---
layout: default
series: true
source: "Mooncake v0.3.13.post1 · C++"
title: Understanding Mooncake from the source
topic: Mooncake
order: 0
description: "How Mooncake's master and clients store objects in each other's memory, traced through the C++ source."
---

# Understanding Mooncake from the source

Mooncake Store keeps objects in the memory of client processes. This series
reads its C++ source to answer three questions:

- How does memory in one process become storage for another?
- Where does a Put send its bytes?
- What does the master do while clients exchange data?

Each article connects a diagram to real classes, functions and breakpoints.

[![One master manages locations. A caller writes bytes directly to an owner.](assets/cluster.svg)](assets/cluster.svg)

## Read the series

{% include part-list.html topic="Mooncake" descriptions=true %}

## The example cluster

All articles use the same three Linux processes in one container:

| Process | Role |
| --- | --- |
| **Master** | Keeps object locations and manages free storage. |
| **Owner** | A Mooncake client that contributes a 64 MiB memory segment. |
| **Caller** | A second Mooncake client that calls Put and Get. |

"Owner" and "caller" are roles, not different client types. Any client can
both contribute storage and make requests. Our caller contributes no storage,
which keeps the data path easy to follow.

> **Setup used throughout:** CPU memory · TCP · one memory replica ·
> `P2PHANDSHAKE` · classic Transfer Engine (`USE_TENT=OFF`). High
> availability, disk offload and GPU paths are left out; the articles point
> out where those branches appear in the source.

All processes use `127.0.0.1` because they share one network namespace. On
separate machines, each client must advertise an address the others can
reach. A container's loopback address is not your Mac's loopback address.

## Control messages and data messages

Mooncake sends two kinds of messages:

- **Control messages** answer questions like "where can I put this object?"
  and "which owner has it?" These are master RPCs and peer metadata
  handshakes. (RPC, *remote procedure call*: one process asks another to run
  a function.)
- **Data messages** carry the object bytes. In this example the caller sends
  them straight to the owner's TCP data port. They never pass through the
  master.

The master still uses memory, but only for its own records. The object
payload always lives in an owner.

## Glossary

| Term | Meaning in this series |
| --- | --- |
| Object | A key and its value, such as `blog/example` and 4096 bytes. |
| Replica | One stored copy of an object. |
| Store segment | A region of client memory registered with the master as storage. |
| Mount | Tell the master a segment is available. Not a filesystem mount. |
| Transfer Engine | The layer that moves bytes between registered memory regions. |
| P2P handshake | Peers exchange Transfer Engine descriptions directly (peer to peer). |
| Endpoint | A network address and port for one service. |
| Lease | A time window in which the Store protects a replica that is being read. It cannot survive an owner crash. |
| Asio | The asynchronous I/O library used by the TCP transport. |
