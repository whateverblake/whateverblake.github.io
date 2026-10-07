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

The earlier articles read a standalone server. The next ones follow a ZooKeeper **ensemble**: leader election and replication. This article sets up three peers on one computer so you can debug all of them.

## 1. Prepare three peers

1. **Give each peer its own process.** Either copy the source project twice (for example `zookeeper_2` and `zookeeper_3`), or keep one compiled tree and create three IDE run configurations. Each process still needs its own config file and data directory.

2. **Give each peer an ID.** In each peer's `dataDir`, create a file named `myid` that contains the server ID: `1`, `2` or `3`.

3. **Edit each `zoo.cfg`.** Three settings matter:

| Setting | Why it changes | Example |
| --- | --- | --- |
| `clientPort` | All peers run on one machine, so each needs its own client port. | `2181`, `2182`, `2183` |
| `dataDir` | Each peer needs its own data directory. | `/tmp/zk-debug/peer1`, `peer2`, `peer3` |
| `server.n=ip:quorum_port:election_port` | The membership list. Identical in all three files. | see below |

In `server.n`, the **first port** is the quorum port: a leader accepts follower connections on it. The **second port** is the election port, used to exchange votes. The original test cluster used:

```properties
server.1=127.0.0.1:2888:3888
server.2=127.0.0.1:2777:3777
server.3=127.0.0.1:2666:3666
```

The three files share these membership lines and differ only in `clientPort` and `dataDir`. A complete minimal config for peer 1:

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

For peer 2 use `clientPort=2182` and `dataDir=/tmp/zk-debug/peer2`; for peer 3 use `2183` and `/tmp/zk-debug/peer3`.

- `initLimit` gives followers ten ticks for their first synchronization with the leader.
- `syncLimit` is the tick allowance for synchronization during normal operation.
- The optional AdminServer is turned off so the three processes do not fight over its default HTTP port. Alternatively, give each one a different `admin.serverPort`.

Create the directories and `myid` files before starting anything:

```bash
mkdir -p /tmp/zk-debug/peer1 /tmp/zk-debug/peer2 /tmp/zk-debug/peer3
printf '1\n' > /tmp/zk-debug/peer1/myid
printf '2\n' > /tmp/zk-debug/peer2/myid
printf '3\n' > /tmp/zk-debug/peer3/myid
```

Running all three peers on one computer makes their interaction easy to watch in a debugger. The `myid` and membership parsing is in [`QuorumPeerConfig`](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/quorum/QuorumPeerConfig.java).

## 2. Start the peers

Run `org.apache.zookeeper.server.quorum.QuorumPeerMain` with that peer's `zoo.cfg` path as the program argument. Repeat for each peer. Because each process has its own config path, they never read the same `myid` or bind the same client port.

Two running peers out of three are a majority, which is enough to elect a leader. To follow that, put breakpoints in `FastLeaderElection.lookForLeader` using the [leader election article](leader-election.html), then continue with [leader and follower initialization](leader-follower-initialization.html). Startup code: [`QuorumPeerMain`](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/quorum/QuorumPeerMain.java).
