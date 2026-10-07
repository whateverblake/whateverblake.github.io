---
layout: default
article: true
topic: ZooKeeper
lang: en
title: "How ExpiryQueue Manages Connection and Session Timeouts"
order: 250
series_order: 5
description: "Read the bucketed expiration queue used to manage ZooKeeper connections and sessions."
---

# How ExpiryQueue Manages Connection and Session Timeouts

The server has two kinds of objects that can time out: **connections** and **sessions**. Both use the same small container, `ExpiryQueue`. This article explains its trick: it rounds every deadline up into a time bucket, so expiring objects means handling a whole bucket at once instead of checking each object.

## 1. Round deadlines into buckets

Every connection has its own deadline, and the deadlines are all different:

[![Connections and their timeout points](assets/expiry-queue-01.svg){: .diagram}](assets/expiry-queue-01.svg)

Checking each deadline separately would be expensive. Instead, `ExpiryQueue` has an `expirationInterval` and rounds every deadline **up** to the next multiple of it:

```java
normalizeTimeout = (timeoutPoint / expirationInterval + 1) * expirationInterval
```

Deadlines that fall into the same interval end up in the same bucket. With `expirationInterval = 10000`:

| Object | Deadline | Bucket |
| --- | --- | --- |
| connection 1 | `1599715479084` | `1599715480000` |
| connection 2 | `1599715479184` | `1599715480000` |
| connection 3 | `1599715479384` | `1599715480000` |

> **Note:** the numbers are illustrative. The real code reads time from `Time.currentElapsedTime()`, an elapsed-time clock, not the Unix wall clock, so don't compare them with calendar time.

`ExpiryQueue` keeps two maps, one in each direction:

```java
  // Each object maps to its rounded expiration deadline.
  private final ConcurrentHashMap<E, Long> elemMap = new ConcurrentHashMap<E, Long>();

   // Each expiration deadline maps to the set of objects expiring in that bucket.
  private final ConcurrentHashMap<Long, Set<E>> expiryMap = new ConcurrentHashMap<Long, Set<E>>();
```

## 2. The consumer

Something has to watch for expired buckets. The consumer works in steps of `expirationInterval`, and its next boundary is `nextExpirationTime`. It starts at:

```java
nextExpirationTime = (now / expirationInterval + 1) * expirationInterval
```

where `now` is the elapsed-time clock when the queue is created. Each step then adds one interval:

```java
nextExpirationTime = nextExpirationTime + expirationInterval
```

So both `nextExpirationTime` and every bucket are multiples of `expirationInterval`. Note that the rounding always moves to the **next** boundary, even when a time already sits exactly on one.

### Get expired objects

The consumer takes an expired bucket with `ExpiryQueue.poll`:

```java
 public Set<E> poll() {
        long now = Time.currentElapsedTime();
        long expirationTime = nextExpirationTime.get();
        if (now < expirationTime) {
            return Collections.emptySet();
        }

        Set<E> set = null;
        // Advance nextExpirationTime by expirationInterval.
        long newExpirationTime = expirationTime + expirationInterval;
        if (nextExpirationTime.compareAndSet(expirationTime, newExpirationTime)) {
            // Remove and return the set at the expirationTime boundary.
            set = expiryMap.remove(expirationTime);
        }
        if (set == null) {
            return Collections.emptySet();
        }
       // Return the objects expiring at this boundary.
        return set;
    }
```

Then it does whatever fits the object: close a connection, expire a session. The scheduling belongs to that consumer; `ExpiryQueue` itself starts no thread.

## 3. Move a deadline

Activity pushes deadlines forward. For a connection, any I/O event refreshes its expiry time. `ExpiryQueue.update` moves the object from its old bucket to the new one:

```java
 // timeout is the object's allowed lifetime from the current time.
 public Long update(E elem, int timeout) {
      // Retrieve the previous expiration deadline from elemMap.
        Long prevExpiryTime = elemMap.get(elem);
        long now = Time.currentElapsedTime();
      // Compute the new rounded deadline.
        Long newExpiryTime = roundToNextInterval(now + timeout);

        // Do nothing if the old and new buckets are identical.
        if (newExpiryTime.equals(prevExpiryTime)) {
            // No change, so nothing to update
            return null;
        }

        // First add the elem to the new expiry time bucket in expiryMap.
        // Find the set of objects at the new expiration deadline.
        Set<E> set = expiryMap.get(newExpiryTime);
        if (set == null) {
            // Construct a ConcurrentHashSet using a ConcurrentHashMap
            // Create a set if the bucket does not yet exist.
            set = Collections.newSetFromMap(new ConcurrentHashMap<E, Boolean>());
            // Put the new set in the map, but only if another thread
            // hasn't beaten us to it
             // Concurrent threads may create the same bucket, so install it with putIfAbsent.
            Set<E> existingSet = expiryMap.putIfAbsent(newExpiryTime, set);
            if (existingSet != null) {
                set = existingSet;
            }
        }
       // Add this object to the new bucket.
        set.add(elem);

        // Map the elem to the new expiry time. If a different previous
        // mapping was present, clean up the previous expiry bucket.
        // Record its new deadline in elemMap.
        prevExpiryTime = elemMap.put(elem, newExpiryTime);
        if (prevExpiryTime != null && !newExpiryTime.equals(prevExpiryTime)) {
            // Remove it from the bucket for its previous deadline.
            Set<E> prevSet = expiryMap.get(prevExpiryTime);
            if (prevSet != null) {
                prevSet.remove(elem);
            }
        }
        return newExpiryTime;
    }
```

That is all of ZooKeeper's expiry management. For more background I recommend *From Paxos to ZooKeeper: Principles and Practice of Distributed Consistency*, which helped me understand this design.

## Source references

- [ExpiryQueue.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/ExpiryQueue.java)
- [SessionTrackerImpl.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/SessionTrackerImpl.java)
- [NIOServerCnxnFactory.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/NIOServerCnxnFactory.java)
- [Time.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/common/Time.java)
