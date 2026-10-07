---
layout: default
article: true
topic: ZooKeeper
lang: en
title: "How ZooKeeper Recovers Data from Snapshots and Transaction Logs"
order: 280
series_order: 8
description: "Understand snapshot and transaction log formats and trace ZooKeeper startup recovery."
---

# How ZooKeeper Recovers Data from Snapshots and Transaction Logs

ZooKeeper writes every state change to a **transaction log** before completing it, and now and then saves its whole in-memory state as a **snapshot**. On startup it rebuilds its data from those two files. This article explains both formats and then follows the recovery code.

"State changes" here means writes: create, set-data, delete, session changes and similar. Reads are never logged.

## 1. Why both a snapshot and a log

Recovery has two steps:

1. Restore a snapshot.
2. Replay the transaction logs written after it.

Each file covers what the other can't:

- A **snapshot** is a checkpoint taken under configured conditions. It misses everything that happened after it started, so if the server crashes before the next snapshot, those changes must come from the logs.
- The **log** has every change, but rebuilding from the log alone would mean keeping the whole history forever and replaying all of it, which is slow.

So normal recovery loads a snapshot to skip most of the history, then replays only the logs that cover what came after.

> **Note:** the original text said log-only recovery is impossible. It is possible in principle, given a starting state and the complete history; snapshots just keep the replay short.

## 2. File names

| File | Suffix (hexadecimal zxid) |
| --- | --- |
| `log.<zxid>` | The **first** zxid in that log. All its records have that zxid or higher. |
| `snapshot.<zxid>` | The last processed zxid when the snapshot **started**. |

Every state change gets a server-assigned **zxid**. On a standalone server zxids only go up; in an ensemble a zxid combines an epoch and a counter. If transaction B comes after A, B's zxid is larger, but not necessarily A's plus one.

Two details matter for recovery:

- **Logs grow in steps.** The original text said every log is a fixed 64 MiB file. In fact 64 MiB is the default **preallocation** step (`zookeeper.preAllocSize`), and a log can grow by several steps. Preallocation saves allocation work while appending; it does not guarantee contiguous disk placement.
- **Snapshots are fuzzy.** Changes keep happening while a snapshot is written, so some nodes in it may already include changes made after `<zxid>`. The file is not an exact copy of the state at one zxid. Replaying the overlapping transactions on top is safe.

## 3. What a log entry holds

[![Transaction log recovery: TxnLogEntry with TxnHeader, Record and TxnDigest](assets/data-recovery-02.svg){: .diagram}](assets/data-recovery-02.svg)

Each log entry is a `TxnLogEntry` with three parts: a `TxnHeader`, an operation-specific `Record` and an optional `TxnDigest`. Read with a log viewer, one entry shows:

| Part | Example from the original article |
| --- | --- |
| Timestamp | when the transaction ran |
| Session ID | the client session |
| `cxid` | the client's request ID |
| `zxid` | the server's transaction ID |
| Operation type | `create2` |
| Node path | `/test/hsbxxxxxxx` |
| Node data | `#xxxxxx` |
| ACL | `v{s{31,s{'world,'anyone}}}` (world/anyone) |
| Digest version | `2` |
| Digest value | `10546528799` |

The values are illustrative, not constants found in every log.

## 4. What a snapshot holds

[![Snapshot file format: DataTree with aclCache and DataNode records, then checksums and digest](assets/data-recovery-03.svg){: .diagram}](assets/data-recovery-03.svg)

[![Snapshot file format: FileHeader, session count and sessionWithTimeOut entries](assets/data-recovery-04.svg){: .diagram}](assets/data-recovery-04.svg)

A snapshot has two parts: the header and session table, and the `DataTree` with its ACL cache and every `DataNode`.

- **Znodes:** each node's state, data and ACL reference. The snapshot is fuzzy, not an atomic point-in-time copy.
- **Sessions:** each session ID with its timeout.

### Znode state

Each node's state, as a viewer shows it:

| Field | Meaning |
| --- | --- |
| `czxid` | Transaction that created the node. |
| `ctime` | Creation time. |
| `mzxid` | Transaction that last changed the node's data. |
| `mtime` | Time of the last data change. |
| `pzxid` | Transaction that last changed the node's child list. |
| `cversion` | Child-list version (not a creation version). |
| `dataVersion` | Data version; `version` in `Stat`. |
| `aclVersion` | ACL version; `aversion` in `Stat`. |
| `ephemeralOwner` | Owning session of an ephemeral node; container and TTL nodes use special values. |
| `dataLength` | Length of the node's data. |

`dataLength` and the child count are computed for the public `Stat`; they are not stored in the serialized `StatPersisted` record.

### Sessions

A session entry shows:

- the session ID,
- its timeout,
- the number of ephemeral nodes it owns.

> **Note:** only the session-ID → timeout map is stored in the snapshot. Which ephemeral nodes a session owns is rebuilt from the nodes' `ephemeralOwner` field, not stored per session.

## 5. The recovery code

The plan: find the newest valid snapshot, then replay the log that contains the next needed zxid and every later log.

> **Watch out:** a log whose name is **below** the snapshot zxid can still hold needed entries, because its name is only its first zxid. With `snapshot.30` and `log.27`, those two files can be enough: recovery replays `log.27` from zxid `0x31` on, if that log contains the later transactions. Picking only logs named above the snapshot would lose data. What counts is the records inside, not the file names.

### `ZooKeeperServer.startdata`

Recovery starts in `ZooKeeperServer.startdata` (lowercase `d` in this version):

```java
  public void startdata() throws IOException, InterruptedException {
        //check to see if zkDb is not null
        // ZKDatabase represents the server's data store.
        if (zkDb == null) {
            zkDb = new ZKDatabase(this.txnLogFactory);
        }
        if (!zkDb.isInitialized()) {
           // Recover the database if it has not been initialized.
            loadData();
        }
    }
```

### `loadData`

```java
  public void loadData() throws IOException, InterruptedException {

        if (zkDb.isInitialized()) {
            setZxid(zkDb.getDataTreeLastProcessedZxid());
        } else {
            // Load data through zkDb.loadDataBase().
            setZxid(zkDb.loadDataBase());
        }

        // Clean up dead sessions
       // Remove sessions no longer present in the recovered timeout map.
        List<Long> deadSessions = new ArrayList<>();
        for (Long session : zkDb.getSessions()) {
            if (zkDb.getSessionWithTimeOuts().get(session) == null) {
                deadSessions.add(session);
            }
        }

        for (long session : deadSessions) {
            // TODO: Is lastProcessedZxid really the best thing to use?
            killSession(session, zkDb.getDataTreeLastProcessedZxid());
        }

       // Take a fresh snapshot after recovery.
        // Make a clean snapshot
        takeSnapshot();
    }
```

### `ZKDatabase.loadDataBase()`

Recovery fills in the fields of `ZKDatabase`:

```java
public long loadDataBase() throws IOException {
        long startTime = Time.currentElapsedTime();
         // Restore dataTree and sessionsWithTimeouts and return the highest recovered zxid.
        // dataTree holds nodes; sessionsWithTimeouts holds session timeout values.
        long zxid = snapLog.restore(dataTree, sessionsWithTimeouts, commitProposalPlaybackListener);
        initialized = true;
        long loadTime = Time.currentElapsedTime() - startTime;
        ServerMetrics.getMetrics().DB_INIT_TIME.add(loadTime);
        LOG.info("Snapshot loaded in {} ms, highest zxid is 0x{}, digest is {}",
                loadTime, Long.toHexString(zxid), dataTree.getTreeDigest());
        return zxid;
    }
```

The data ends up in `DataTree`.

### `DataTree`

`DataTree` is ZooKeeper's in-memory data store. Its key members:

| Member | Type | Holds |
| --- | --- | --- |
| `nodes` | `NodeHashMap` | Full path → `DataNode`. |
| `dataWatches` / `childWatches` | `IWatchManager` | Watch registrations. |
| `ephemerals` | `Map<Long, HashSet<String>>` | Session → its ephemeral paths. |
| `aclCache` | `ReferenceCountedACLCache` | Shared ACL records. |
| `lastProcessedZxid` | `long` | Latest applied transaction. |

`nodes` is a `NodeHashMapImpl`:

| Member | Type | Job |
| --- | --- | --- |
| `nodes` | `ConcurrentHashMap<String, DataNode>` | The node storage. |
| `digestEnabled` | `boolean` | Whether to track a digest of the whole tree. |
| `digestCalculator` | `DigestCalculator` | Computes each node's contribution. |
| `hash` | `AdHash` | The aggregate digest. |
| `put` / `remove` / `preChange` / `postChange` | methods | Keep storage and digest in step. |

> **Note:** the map key is the **full path**, not just the node's own name.

Each value is a `DataNode`:

| Member | Type | Holds |
| --- | --- | --- |
| `data` | `byte[]` | The node's payload. |
| `acl` | `Long` | Key into the ACL cache. |
| `stat` | `StatPersisted` | Persistent metadata (zxids, times, versions, owner). |
| `children` | `Set<String>` | Child **names**, not full paths. |
| `digest` / `digestCached` | | Cached node digest and its validity flag. |

### `snapLog.restore`

Back on the call chain, `FileTxnSnapLog.restore`:

```java
 public long restore(DataTree dt, Map<Long, Integer> sessions, PlayBackListener listener) throws IOException {
        long snapLoadingStartTime = Time.currentElapsedTime();
       // Deserialize snapshot data through snapLog.
        long deserializeResult = snapLog.deserialize(dt, sessions);
        ServerMetrics.getMetrics().STARTUP_SNAP_LOAD_TIME.add(Time.currentElapsedTime() - snapLoadingStartTime);
        // Create the transaction log implementation.
        FileTxnLog txnLog = new FileTxnLog(dataDir);
        boolean trustEmptyDB;
        File initFile = new File(dataDir.getParent(), "initialize");
        if (Files.deleteIfExists(initFile.toPath())) {
            LOG.info("Initialize file found, an empty database will not block voting participation");
            trustEmptyDB = true;
        } else {
            trustEmptyDB = autoCreateDB;
        }
        // RestoreFinalizer.run replays the transaction logs.
        RestoreFinalizer finalizer = () -> {
            long highestZxid = fastForwardFromEdits(dt, sessions, listener);
            // The snapshotZxidDigest will reset after replaying the txn of the
            // zxid in the snapshotZxidDigest, if it's not reset to null after
            // restoring, it means either there are not enough txns to cover that
            // zxid or that txn is missing
            DataTree.ZxidDigest snapshotZxidDigest = dt.getDigestFromLoadedSnapshot();
            if (snapshotZxidDigest != null) {
                LOG.warn(
                        "Highest txn zxid 0x{} is not covering the snapshot digest zxid 0x{}, "
                                + "which might lead to inconsistent state",
                        Long.toHexString(highestZxid),
                        Long.toHexString(snapshotZxidDigest.getZxid()));
            }
            return highestZxid;
        };

        if (-1L == deserializeResult) {
            /* this means that we couldn't find any snapshot, so we need to
             * initialize an empty database (reported in ZOOKEEPER-2325) */
            if (txnLog.getLastLoggedZxid() != -1) {
                // ZOOKEEPER-3056: provides an escape hatch for users upgrading
                // from old versions of zookeeper (3.4.x, pre 3.5.3).
                if (!trustEmptySnapshot) {
                    throw new IOException(EMPTY_SNAPSHOT_WARNING + "Something is broken!");
                } else {
                    LOG.warn("{}This should only be allowed during upgrading.", EMPTY_SNAPSHOT_WARNING);
                    return finalizer.run();
                }
            }

            if (trustEmptyDB) {
                /* TODO: (br33d) we should either put a ConcurrentHashMap on restore()
                 *       or use Map on save() */
                save(dt, (ConcurrentHashMap<Long, Integer>) sessions, false);

                /* return a zxid of 0, since we know the database is empty */
                return 0L;
            } else {
                /* return a zxid of -1, since we are possibly missing data */
                LOG.warn("Unexpected empty data tree, setting zxid to -1");
                dt.lastProcessedZxid = -1L;
                return -1L;
            }
        }

        return finalizer.run();
    }
```

### `FileSnap.deserialize`

First the snapshot:

```java
public long deserialize(DataTree dt, Map<Long, Integer> sessions) throws IOException {
        // we run through 100 snapshots (not all of them)
        // if we cannot get it running within 100 snapshots
        // we should  give up
      // Find up to 100 candidate valid snapshots, ordered by decreasing zxid suffix.
        List<File> snapList = findNValidSnapshots(100);
        if (snapList.size() == 0) {
            return -1L;
        }
        File snap = null;
        long snapZxid = -1;
        boolean foundValid = false;
        // Try snapshots in order; stop after one is successfully restored.
        for (int i = 0, snapListSize = snapList.size(); i < snapListSize; i++) {
            // Select the current snapshot file.
            snap = snapList.get(i);
            LOG.info("Reading snapshot {}", snap);
            // Read its filename zxid, the checkpoint at snapshot start.
            snapZxid = Util.getZxidFromName(snap.getName(), SNAPSHOT_FILE_PREFIX);
            try (CheckedInputStream snapIS = SnapStream.getInputStream(snap)) {
              // Open the snapshot input stream.
                InputArchive ia = BinaryInputArchive.getArchive(snapIS);
               // Deserialize node and session data.
                deserialize(dt, sessions, ia);
               // Verify the snapshot integrity seal.
                SnapStream.checkSealIntegrity(snapIS, ia);

                // Digest feature was added after the CRC to make it backward
                // compatible, the older code can still read snapshots which
                // includes digest.
                //
                // To check the intact, after adding digest we added another
                // CRC check.
                // Deserialize optional digest information.
                if (dt.deserializeZxidDigest(ia, snapZxid)) {
               // Verify the corresponding integrity seal.

                    SnapStream.checkSealIntegrity(snapIS, ia);
                }
                // Stop after successful parsing.
                foundValid = true;
                break;
            } catch (IOException e) {
                LOG.warn("problem reading snap file {}", snap, e);
            }
        }
        if (!foundValid) {
            throw new IOException("Not able to find valid snapshots in " + snapDir);
        }
         // Record snapZxid as the checkpoint in DataTree.
        dt.lastProcessedZxid = snapZxid;
        lastSnapshotInfo = new SnapshotInfo(dt.lastProcessedZxid, snap.lastModified() / 1000);

        // compare the digest if this is not a fuzzy snapshot, we want to compare
        // and find inconsistent asap.
        if (dt.getDigestFromLoadedSnapshot() != null) {
            dt.compareSnapshotDigests(dt.lastProcessedZxid);
        }
        return dt.lastProcessedZxid;
    }
```

### `deserialize`

The snapshot `deserialize` chain:

```java
public void deserialize(DataTree dt, Map<Long, Integer> sessions, InputArchive ia) throws IOException {

        FileHeader header = new FileHeader();
       // Deserialize FileHeader first.
        header.deserialize(ia, "fileheader");
        if (header.getMagic() != SNAP_MAGIC) {
            throw new IOException("mismatching magic headers " + header.getMagic() + " !=  " + FileSnap.SNAP_MAGIC);
        }
         //
        SerializeUtils.deserializeSnapshot(dt, ia, sessions);
    }
```

### `SerializeUtils.deserializeSnapshot`

```java
public static void deserializeSnapshot(DataTree dt, InputArchive ia, Map<Long, Integer> sessions) throws IOException {
        // Restore session timeout information first.
        int count = ia.readInt("count");
        while (count > 0) {
            // Read each session ID and timeout from the snapshot.
            long id = ia.readLong("id");
            int to = ia.readInt("timeout");
            sessions.put(id, to);
            if (LOG.isTraceEnabled()) {
                ZooTrace.logTraceMessage(
                    LOG,
                    ZooTrace.SESSION_TRACE_MASK,
                    "loadData --- session in archive: " + id + " with timeout: " + to);
            }
            count--;
        }
       // Deserialize the DataTree.
        dt.deserialize(ia, "tree");
    }
```

### `DataTree.deserialize()`

```java
public void deserialize(InputArchive ia, String tag) throws IOException {
        // Read ACL cache information first.
        aclCache.deserialize(ia);
        nodes.clear();
        pTrie.clear();
        nodeDataSize.set(0);
        // Read node paths and data.
        String path = ia.readString("path");
        while (!"/".equals(path)) {
            DataNode node = new DataNode();
          // Deserialize a DataNode.
            ia.readRecord(node, "node");
            nodes.put(path, node);
            synchronized (node) {
                aclCache.addUsage(node.acl);
            }
            int lastSlash = path.lastIndexOf('/');
            if (lastSlash == -1) {
                root = node;
            } else {
                String parentPath = path.substring(0, lastSlash);
                DataNode parent = nodes.get(parentPath);
                if (parent == null) {
                    throw new IOException("Invalid Datatree, unable to find "
                                          + "parent "
                                          + parentPath
                                          + " of path "
                                          + path);
                }
               // Link this node into its parent's child set.
                parent.addChild(path.substring(lastSlash + 1));
                long eowner = node.stat.getEphemeralOwner();
                EphemeralType ephemeralType = EphemeralType.get(eowner);
                if (ephemeralType == EphemeralType.CONTAINER) {
                    containers.add(path);
                } else if (ephemeralType == EphemeralType.TTL) {
                    ttls.add(path);
                } else if (eowner != 0) {
                    HashSet<String> list = ephemerals.get(eowner);
                    if (list == null) {
                        list = new HashSet<String>();
                        ephemerals.put(eowner, list);
                    }
                    list.add(path);
                }
            }
            path = ia.readString("path");
        }
        // have counted digest for root node with "", ignore here to avoid
        // counting twice for root node
        nodes.putWithoutDigest("/", root);

        nodeDataSize.set(approximateDataSize());

        // we are done with deserializing the
        // the datatree
        // update the quotas - create path trie
        // and also update the stat nodes
       // Rebuild quota information.
        setupQuota();
       // Purge unused ACL entries.
        aclCache.purgeUnused();
    }
```

That restores the snapshot. Now the log replay.

### `RestoreFinalizer.run`

```java
long highestZxid = fastForwardFromEdits(dt, sessions, listener);
            // The snapshotZxidDigest will reset after replaying the txn of the
            // zxid in the snapshotZxidDigest, if it's not reset to null after
            // restoring, it means either there are not enough txns to cover that
            // zxid or that txn is missing
            DataTree.ZxidDigest snapshotZxidDigest = dt.getDigestFromLoadedSnapshot();
            if (snapshotZxidDigest != null) {
                LOG.warn(
                        "Highest txn zxid 0x{} is not covering the snapshot digest zxid 0x{}, "
                                + "which might lead to inconsistent state",
                        Long.toHexString(highestZxid),
                        Long.toHexString(snapshotZxidDigest.getZxid()));
            }
            return highestZxid;
```

### `fastForwardFromEdits`

```java
 public long fastForwardFromEdits(
        DataTree dt,
        Map<Long, Integer> sessions,
        PlayBackListener listener) throws IOException {
       // Read logs covering dt.lastProcessedZxid + 1, including the latest log starting at or below that zxid.
        TxnIterator itr = txnLog.read(dt.lastProcessedZxid + 1);
        long highestZxid = dt.lastProcessedZxid;
        TxnHeader hdr;
        int txnLoaded = 0;
        long startTime = Time.currentElapsedTime();
        try {
            while (true) {
                // iterator points to
                // the first valid txn when initialized
                hdr = itr.getHeader();
                if (hdr == null) {
                    //empty logs
                    return dt.lastProcessedZxid;
                }
                if (hdr.getZxid() < highestZxid && highestZxid != 0) {
                     // Report a transaction zxid lower than highestZxid.
                    LOG.error("{}(highestZxid) > {}(next log) for type {}", highestZxid, hdr.getZxid(), hdr.getType());
                } else {
                    // Advance highestZxid to the current log record's zxid.
                    highestZxid = hdr.getZxid();
                }
                try {
                    // Apply the transaction to DataTree; the node-creation article explains this path.
                    processTransaction(hdr, dt, sessions, itr.getTxn());
                    dt.compareDigest(hdr, itr.getTxn(), itr.getDigest());
                    txnLoaded++;
                } catch (KeeperException.NoNodeException e) {
                    throw new IOException("Failed to process transaction type: "
                                          + hdr.getType()
                                          + " error: "
                                          + e.getMessage(),
                                          e);
                }
                listener.onTxnLoaded(hdr, itr.getTxn(), itr.getDigest());

                if (!itr.next()) {
                    break;
                }
            }
        } finally {
            if (itr != null) {
                itr.close();
            }
        }

        long loadTime = Time.currentElapsedTime() - startTime;
        LOG.info("{} txns loaded in {} ms", txnLoaded, loadTime);
        ServerMetrics.getMetrics().STARTUP_TXNS_LOADED.add(txnLoaded);
        ServerMetrics.getMetrics().STARTUP_TXNS_LOAD_TIME.add(loadTime);
         // Return the highest processed zxid.
        return highestZxid;
    }
```

### `TxnIterator.next()`

`next()` reads the next record from the logs:

```java
public boolean next() throws IOException {
            if (ia == null) {
                return false;
            }
            try {
                // Read the stored checksum.
                long crcValue = ia.readLong("crcvalue");
                // Read the serialized transaction entry.
                byte[] bytes = Util.readTxnBytes(ia);
                // Since we preallocate, we define EOF to be an
                if (bytes == null || bytes.length == 0) {
                    throw new EOFException("Failed to read " + logFile);
                }
                // EOF or corrupted record
                // validate CRC
                Checksum crc = makeChecksumAlgorithm();
                crc.update(bytes, 0, bytes.length);
                if (crcValue != crc.getValue()) {
                    throw new IOException(CRC_ERROR);
                }
                // Deserialize the binary record into TxnLogEntry.
                TxnLogEntry logEntry = SerializeUtils.deserializeTxn(bytes);
                hdr = logEntry.getHeader();
               // record holds the operation-specific transaction body.
                record = logEntry.getTxn();
              // digest holds optional transaction digest information.
                digest = logEntry.getDigest();
            } catch (EOFException e) {
                LOG.debug("EOF exception", e);
                inputStream.close();
                inputStream = null;
                ia = null;
                hdr = null;
                // this means that the file has ended
                // we should go to the next file
                // At the end of this log, open the next file.
                if (!goToNextLog()) {
                    return false;
                }
                // if we went to the next log file, we should call next() again
                // Read the first record of the next log.
                return next();
            } catch (IOException e) {
                inputStream.close();
                throw e;
            }
            return true;
        }
```

## Summary

ZooKeeper recovers by restoring a snapshot and replaying the logs after it. For how each replayed transaction is applied, see [node creation](node-creation.html).

## Source references

- [ZooKeeperServer.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/ZooKeeperServer.java)
- [ZKDatabase.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/ZKDatabase.java)
- [DataTree.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/DataTree.java)
- [DataNode.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/DataNode.java)
- [FileTxnSnapLog.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/persistence/FileTxnSnapLog.java)
- [FileSnap.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/persistence/FileSnap.java)
- [FileTxnLog.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/persistence/FileTxnLog.java)
- [SerializeUtils.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/util/SerializeUtils.java)
- [Protocol and persisted-record Jute definitions](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-jute/src/main/resources/zookeeper.jute)
- [Historical configuration reference](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-docs/src/main/resources/markdown/zookeeperAdmin.md)
