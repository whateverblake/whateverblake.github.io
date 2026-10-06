---
layout: default
article: true
topic: ZooKeeper
lang: en
title: "Setting Up a Three-Node ZooKeeper Ensemble"
order: 220
series_order: 2
description: "Configure and debug three ZooKeeper peers on one computer using separate data directories and ports."
---

# Setting Up a Three-Node ZooKeeper Ensemble

> **Source version.** This English edition checks the original analysis against ZooKeeper 3.6.2, available in October 2020, pinned at commit `803c7f1a12f85978cb049af5e4ef23bd8b688715`. The annotated excerpts retain the original selection and executable logic; ellipses mark omissions and are not complete compilable methods.

## Introduction
The earlier [ZooKeeper source reading articles](index.html) examined the standalone server. Next, a series of articles follows ZooKeeper's ensemble source code. This opening article explains how to create a distributed debugging environment on one computer.

## Set up an ensemble debugging environment
We will run three ZooKeeper peers. The setup is straightforward.

1. Make two copies of the source project used earlier, giving their root directories distinct names, such as `zookeeper_2` and `zookeeper_3`. Alternatively, use three IDE run configurations against the same compiled source tree; each process still needs its own configuration and data directory.

2. In each peer's `dataDir`, create a file named `myid`, containing that peer's server ID. Use `1`, `2`, and `3` respectively.

3. Edit each project's `zoo.cfg`. Three parts need attention:
### Change clientPort
Since all three instances run on the same computer, give them distinct client ports, for example `2181`, `2182`, and `2183`.
### Change dataDir
Set the location where each peer stores data. Since the peers share a computer, use distinct directories, for example `/tmp/zk-debug/peer1`, `/tmp/zk-debug/peer2`, and `/tmp/zk-debug/peer3`.
### Add server.n = ip:quorum_port:election_port
Add the same ensemble membership list to all three configurations. The first port is the quorum communication port, on which a peer accepts learner connections when acting as leader. The second is the election port used to exchange votes. Here is the original local test environment's membership list:

```properties

server.1=127.0.0.1:2888:3888
server.2=127.0.0.1:2777:3777
server.3=127.0.0.1:2666:3666

```


The three files can share these membership lines while each sets its own `clientPort` and `dataDir`. For example, the first peer's complete minimal debugging configuration is:

```properties

tickTime=2000
initLimit=10
syncLimit=5
clientPort=2181
dataDir=/tmp/zk-debug/peer1
server.1=127.0.0.1:2888:3888
server.2=127.0.0.1:2777:3777
server.3=127.0.0.1:2666:3666
admin.enableServer=false

```


For peer 2, set `clientPort=2182` and `dataDir=/tmp/zk-debug/peer2`; for peer 3, use `2183` and `/tmp/zk-debug/peer3`. Keep the three `server.n` lines identical. `initLimit` allows ten ticks for initial learner synchronization, while `syncLimit` defines the tick allowance for synchronization during normal operation. Disable the optional AdminServer in this local example so all three processes do not compete for its default HTTP port; alternatively, give each process a distinct `admin.serverPort`.

Create the directories and identity files before starting the processes:

```bash

mkdir -p /tmp/zk-debug/peer1 /tmp/zk-debug/peer2 /tmp/zk-debug/peer3
printf '1\n' > /tmp/zk-debug/peer1/myid
printf '2\n' > /tmp/zk-debug/peer2/myid
printf '3\n' > /tmp/zk-debug/peer3/myid

```


The local three-process setup is useful for source debugging; the original article uses one computer to make the interaction easy to inspect. The `myid` and membership parsing behavior comes from the pinned [`QuorumPeerConfig`](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/quorum/QuorumPeerConfig.java).

## Start the peers
Find `org.apache.zookeeper.server.quorum.QuorumPeerMain`, set its program argument to that process's `zoo.cfg` path, and run its `main` method. Repeat for each peer, then begin debugging the ensemble source code. The separate configuration paths prevent all three processes from reading the same `myid` or binding the same client port.

With two of the three voting peers running, the standard majority configuration can elect a leader. Use the [leader election article](leader-election.html) to place breakpoints in `FastLeaderElection.lookForLeader`, then follow [leader/follower initialization](leader-follower-initialization.html). Startup is implemented by the pinned [`QuorumPeerMain`](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/quorum/QuorumPeerMain.java).
