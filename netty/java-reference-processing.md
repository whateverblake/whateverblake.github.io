---
layout: default
article: true
topic: Netty
lang: en
title: "How Java Processes Soft, Weak, and Phantom References"
description: "Follow OpenJDK 8 reference reachability, the Reference Handler thread, cleaners, and reference queues."
order: 490
series_order: 9
---

# How Java Processes Soft, Weak, and Phantom References

Java has four kinds of reference: **strong, soft, weak and phantom**. Strong references are the everyday kind: in `Object obj = new Object()`, `obj` is a strong reference. The other three are classes, `SoftReference`, `WeakReference` and `PhantomReference`, all extending the abstract `Reference`. This article follows what happens to them after a garbage collection: how the JVM hands them to the **Reference Handler** thread, and how that thread passes them to a `Cleaner` or to your `ReferenceQueue`.

> **Source:** OpenJDK 8u272-b10 (October 2020). This is JDK internals, not Netty, but Netty's direct buffers depend on it. Code excerpts keep the original selection; comments are translated.

## 1. Create references

```java
ReferenceQueue referenceQueue = new ReferenceQueue();
Object obj = new Object();
SoftReference sr = new SoftReference(obj,referenceQueue);
WeakReference wr = new WeakReference(obj,referenceQueue);
PhantomReference pr = new PhantomReference(obj,referenceQueue);
```

All three have similar constructors. A `ReferenceQueue` is optional for soft and weak references; without one, `Reference` uses a **null-queue sentinel**:

```java
Reference(T referent) {
    this(referent, null);
}
Reference(T referent, ReferenceQueue<? super T> queue) {
    this.referent = referent;
    this.queue = (queue == null) ? ReferenceQueue.NULL : queue;
}
```

| Case | Queue |
| --- | --- |
| `new WeakReference(object)` | No application queue; `queue` is `ReferenceQueue.NULL`. |
| `new WeakReference(object, queue)` | The reference will be enqueued on `queue`. |
| `ReferenceQueue.NULL` | Sentinel: "no queue". |
| `ReferenceQueue.ENQUEUED` | Sentinel set after the reference has been enqueued. |

Your code calls `poll()` or `remove()` on the queue and gets the **reference objects** back, never their former referents.

## 2. What each type is for

An object reachable only through these references can be collected once the right reachability condition holds:

| Type | Cleared when | `get()` |
| --- | --- | --- |
| `SoftReference` | at the collector's discretion, and always before an `OutOfMemoryError` | the referent, while it is still there |
| `WeakReference` | as soon as the referent is only weakly reachable | the referent, while it is still there |
| `PhantomReference` | enqueued once the referent is phantom reachable; in JDK 8 it does **not** clear the referent automatically | always `null` |

Being cleared or enqueued does not mean the memory is reclaimed immediately. Registered references are eventually enqueued, so your code can take them from the queue and run its own cleanup. What appears in the queue is the reference object, not the referent.

## 3. How references are processed

### `Reference`

`Reference` is also a node in the JVM's internal linked lists. Its key fields:

```java
private T referent;         /* Treated specially by GC */
volatile ReferenceQueue<? super T> queue;
/* When active:   NULL
 *     pending:   this
 *    Enqueued:   next reference in queue (or this if last)
 *    Inactive:   this
 */
@SuppressWarnings("rawtypes")
volatile Reference next;
/* When active:   next element in a discovered reference list maintained by GC (or this if last)
 *     pending:   next element in the pending list (or null if last)
 *   otherwise:   NULL
 */
transient private Reference<T> discovered;  /* used by VM */
/* Object used to synchronize with the garbage collector.  The collector
 * must acquire this lock at the beginning of each collection cycle.  It is
 * therefore critical that any code holding this lock complete as quickly
 * as possible, allocate no new objects, and avoid calling user code.
 */
static private class Lock { }
private static Lock lock = new Lock();
/* List of References waiting to be enqueued.  The collector adds
 * References to this list, while the Reference-handler thread removes
 * them.  This list is protected by the above lock object. The
 * list uses the discovered field to link its elements.
 */
private static Reference<Object> pending = null;
```

### `ReferenceHandler`

`ReferenceHandler` is an inner class of `Reference` that extends `Thread`.

The static initializer of `Reference` starts it:

```java
 static {
        ThreadGroup tg = Thread.currentThread().getThreadGroup();
        for (ThreadGroup tgn = tg;
             tgn != null;
             tg = tgn, tgn = tg.getParent());
        Thread handler = new ReferenceHandler(tg, "Reference Handler");
        /* If there were a special system-only priority greater than
         * MAX_PRIORITY, it would be used here
         */
        handler.setPriority(Thread.MAX_PRIORITY);
        handler.setDaemon(true);
        handler.start();

        // provide access in SharedSecrets
        SharedSecrets.setJavaLangRefAccess(new JavaLangRefAccess() {
            @Override
            public boolean tryHandlePendingReference() {
                return tryHandlePending(false);
            }
        });
    }
```

Its `run` loops forever:

```java
 public void run() {
            while (true) {
                tryHandlePending(true);
            }
        }
```

So everything happens in `tryHandlePending`:

```java
 static boolean tryHandlePending(boolean waitForNotify) {
        Reference<Object> r;
        Cleaner c;
        try {
            synchronized (lock) {
                if (pending != null) {
                    r = pending;
                    // 'instanceof' might throw OutOfMemoryError sometimes
                    // so do this before un-linking 'r' from the 'pending' chain...
                    c = r instanceof Cleaner ? (Cleaner) r : null;
                    // unlink 'r' from 'pending' chain
                    pending = r.discovered;
                    r.discovered = null;
                } else {
                    // The waiting on the lock may cause an OutOfMemoryError
                    // because it may try to allocate exception objects.
                    if (waitForNotify) {
                        lock.wait();
                    }
                    // retry if waited
                    return waitForNotify;
                }
            }
        } catch (OutOfMemoryError x) {
            // Give other threads CPU time so they hopefully drop some live references
            // and GC reclaims some space.
            // Also prevent CPU intensive spinning in case 'r instanceof Cleaner' above
            // persistently throws OOME for some time...
            Thread.yield();
            // retry
            return true;
        } catch (InterruptedException x) {
            // retry
            return true;
        }

        // Fast path for cleaners
        if (c != null) {
            c.clean();
            return true;
        }

        ReferenceQueue<? super Object> q = r.queue;
        if (q != ReferenceQueue.NULL) q.enqueue(r);
        return true;
    }
```

This is the key method. It shows how references found by the collector reach a `Cleaner` or your queue.

Inside the synchronized block it first checks `pending`. If it is empty, the thread waits. `pending` is declared in `Reference`:

```java
 private static Reference<Object> pending = null;
```

It starts as `null`. Who sets it? **The JVM**, while it processes references discovered during garbage collection. `pending` points to the head of a list, and the other references hang off each other's `discovered` field. Each call to `tryHandlePending` takes one reference off that list:

[![Move pending references to their queues: the GC builds the pending list linked through discovered; the Reference Handler thread takes one reference at a time under the lock; a Cleaner runs clean(); any other reference is enqueued on its ReferenceQueue unless that is NULL; the application polls the queue.](assets/java-reference-processing-04.svg)](assets/java-reference-processing-04.svg)

What happens to each one? First, the handler checks for a `Cleaner`:

```java
if (pending != null) {
    r = pending;
    // 'instanceof' might throw OutOfMemoryError sometimes
    // so do this before un-linking 'r' from the 'pending' chain...
    c = r instanceof Cleaner ? (Cleaner) r : null;
    // unlink 'r' from 'pending' chain
    pending = r.discovered;
    r.discovered = null;
} else {
    // The waiting on the lock may cause an OutOfMemoryError
    // because it may try to allocate exception objects.
    if (waitForNotify) {
        lock.wait();
    }
    // retry if waited
    return waitForNotify;
}
```

A `Cleaner` (a subclass of `PhantomReference`) gets its `clean()` method called. `DirectByteBuffer` uses this to free native memory, a separate topic. Any other reference is enqueued on its `ReferenceQueue`, unless that is the `NULL` sentinel:

```java
ReferenceQueue<? super Object> q = r.queue;
if (q != ReferenceQueue.NULL) q.enqueue(r);
return true;
```

Your code can then take the reference from its queue. That is the whole path. An experiment shows it in action.

## 4. Experiment

```java
        Object obj = new Object();
        ReferenceQueue referenceQueue = new ReferenceQueue();
        WeakReference weakReference = new WeakReference(obj,referenceQueue);
        WeakReference weakReference2 = new WeakReference(obj,referenceQueue);
        WeakReference weakReference3 = new WeakReference(obj,referenceQueue);

        System.out.println(weakReference.get());
        System.out.println(referenceQueue.poll());
        obj = null ;
        System.gc();
        System.out.println("before isEnqueue----"+weakReference.isEnqueued());

        Thread.sleep(1000);
        System.out.println("after isEnqueue----"+weakReference.isEnqueued());

        Reference t = referenceQueue.poll() ;
        System.out.println(t);

        System.out.println(weakReference.get());
```

The program creates an object with the strong reference `obj` and three weak references to it.

1. At first, `weakReference.get()` returns the object and `referenceQueue.poll()` returns nothing.
2. `obj = null` drops the strong reference, and `System.gc()` **requests** a collection.
3. If the object is now only weakly reachable and the JVM does collect, the three weak references are cleared and later enqueued.

Enqueuing happens on the background Reference Handler thread, so the first `before isEnqueue` print can still say `false`. The one-second sleep gives the handler time, and the later print may say `true`. Neither the GC request nor the sleep **guarantees** these results. Once enqueued, up to three `poll()` calls return the three weak reference objects. `isEnqueued()` reports queue membership; it does not mean the referent's memory is already reclaimed.

> **Debugging tip:** to watch these weak references in `tryHandlePending`, set a **conditional breakpoint** there. The JVM and libraries create many references of their own, so filter them out:
>
> | Setting | Value |
> | --- | --- |
> | Breakpoint | `Reference.tryHandlePending`, on the pending-list path |
> | Condition | `pending instanceof WeakReference && !(pending instanceof java.util.WeakHashMap.Entry)` |
>
> Some IDEs evaluate the condition in the declaring source's scope. Timing and values vary from run to run, and a breakpoint plus a GC request still does not guarantee reclamation.

## Notes on the source

- The original article claimed immediate reclamation and a guaranteed full GC. Reachability, clearing, enqueuing and physical reclamation are separate steps, and the text above keeps them apart.
- JDK 8 phantom references are not cleared automatically; later JDKs changed that.
- The code is JDK 8's pending-list implementation. Later JDKs process references differently.

Source references (OpenJDK 8u272-b10, October 2020):

- [Reference.java](https://github.com/openjdk/jdk8u/blob/c3b5603e949d6272d777ef57952833672a97b4e3/jdk/src/share/classes/java/lang/ref/Reference.java)
- [ReferenceQueue.java](https://github.com/openjdk/jdk8u/blob/c3b5603e949d6272d777ef57952833672a97b4e3/jdk/src/share/classes/java/lang/ref/ReferenceQueue.java)
- [SoftReference.java](https://github.com/openjdk/jdk8u/blob/c3b5603e949d6272d777ef57952833672a97b4e3/jdk/src/share/classes/java/lang/ref/SoftReference.java)
- [WeakReference.java](https://github.com/openjdk/jdk8u/blob/c3b5603e949d6272d777ef57952833672a97b4e3/jdk/src/share/classes/java/lang/ref/WeakReference.java)
- [PhantomReference.java](https://github.com/openjdk/jdk8u/blob/c3b5603e949d6272d777ef57952833672a97b4e3/jdk/src/share/classes/java/lang/ref/PhantomReference.java)
- [Cleaner.java](https://github.com/openjdk/jdk8u/blob/c3b5603e949d6272d777ef57952833672a97b4e3/jdk/src/share/classes/sun/misc/Cleaner.java)
