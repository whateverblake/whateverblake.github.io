---
layout: default
article: true
topic: Netty
lang: en
title: "Understanding the Netty Thread Model"
description: "Trace event-loop selection, worker startup, and shared I/O and task scheduling."
order: 410
series_order: 1
---

# Understanding the Netty Thread Model

Netty is a high-performance networking framework for Java. This article explains its threading: how an event loop group picks a loop for each channel, what a `NioEventLoop` does in its `run` loop, and how that loop gets its thread.

> **Source:** Netty 4.1.53.Final (October 2020) · NIO transport. Code excerpts keep the original selection; comments are translated. Figures are the author's original diagrams with English labels.

## 1. The reactor model

A Netty server follows the **reactor** pattern. An acceptor takes connection requests and creates a `SocketChannel` for each one. Every accepted channel is bound to one event loop, and that loop's thread handles all of the channel's later events.

[![Reactor roles in a Netty NIO server](assets/thread-model-01.svg){: .diagram}](assets/thread-model-01.svg)

## 2. `NioEventLoopGroup`

Think of `NioEventLoopGroup` as a fixed set of worker threads. Its size is configurable and defaults to **twice the number of processors**. (Strictly, the children are `EventExecutor`s, not raw threads, but "one thread each" is the right first model.)

The group uses a **chooser** to spread channels over its children. Netty has two:

### `PowerOfTwoEventExecutorChooser`

Used when the number of children is a power of two:

```java
 private static final class PowerOfTwoEventExecutorChooser implements EventExecutorChooser {
        private final AtomicInteger idx = new AtomicInteger();
        private final EventExecutor[] executors;

        PowerOfTwoEventExecutorChooser(EventExecutor[] executors) {
            this.executors = executors;
        }

        @Override
        public EventExecutor next() {
            return executors[idx.getAndIncrement() & executors.length - 1];
        }
    }
```

### `GenericEventExecutorChooser`

Used for any other size:

```java
 private static final class GenericEventExecutorChooser implements EventExecutorChooser {
        private final AtomicInteger idx = new AtomicInteger();
        private final EventExecutor[] executors;

        GenericEventExecutorChooser(EventExecutor[] executors) {
            this.executors = executors;
        }

        @Override
        public EventExecutor next() {
            return executors[Math.abs(idx.getAndIncrement() % executors.length)];
        }
    }
```

Both rotate through the children. Why have two? With a power-of-two size, a bitwise AND (`idx & (n - 1)`) replaces the remainder (`idx % n`). The saving per call is tiny, but this runs for every channel.

## 3. `NioEventLoop`

A `NioEventLoop` is a single-threaded event loop. Each `NioSocketChannel` is registered with exactly one loop, which handles all of that channel's events. Once started, the loop's thread handles three kinds of work:

[![Three kinds of NioEventLoop work](assets/thread-model-02.svg){: .diagram}](assets/thread-model-02.svg)

| Work | What it is |
| --- | --- |
| **selector** | I/O readiness events. A group has a fixed number of loops, so with more channels than loops, several channels share one loop and register with its selector. |
| **tasks** | Ordinary tasks, submitted from another thread or from the loop itself. Example: registering a channel from the main thread submits a registration task to the chosen loop. |
| **scheduled tasks** | Tasks that run at a deadline. Example: if a client connect does not finish at once, the loop schedules a task that fails the attempt when the connect timeout expires. |

The core of it is `NioEventLoop.run`:

```java
 @Override
    protected void run() {
        int selectCnt = 0;
        for (;;) {
            try {
                int strategy;
                try {
                    strategy = selectStrategy.calculateStrategy(selectNowSupplier, hasTasks());
                    switch (strategy) {
                    case SelectStrategy.CONTINUE:
                        continue;

                    case SelectStrategy.BUSY_WAIT:
                        // fall-through to SELECT since the busy-wait is not supported with NIO

                    case SelectStrategy.SELECT:
                        long curDeadlineNanos = nextScheduledTaskDeadlineNanos();
                        if (curDeadlineNanos == -1L) {
                            curDeadlineNanos = NONE; // nothing on the calendar
                        }
                        // Set nextWakeupNanos to the earliest scheduled-task deadline.
                        nextWakeupNanos.set(curDeadlineNanos);
                        try {
                           // If no ordinary task is queued, perform selector selection.
                           // With no scheduled task this can block; otherwise wait until curDeadlineNanos, unless another thread wakes the selector.
                            if (!hasTasks()) {

                                strategy = select(curDeadlineNanos);
                            }
                        } finally {
                            // This update is just to help block unnecessary selector wakeups
                            // so use of lazySet is ok (no race condition)
                            nextWakeupNanos.lazySet(AWAKE);
                        }
                        // fall through
                    default:
                    }
                } catch (IOException e) {
                    // If we receive an IOException here its because the Selector is messed up. Let's rebuild
                    // the selector and retry. https://github.com/netty/netty/issues/8566
                    rebuildSelector0();
                    selectCnt = 0;
                    handleLoopException(e);
                    continue;
                }

                selectCnt++;
                cancelledKeys = 0;
                needsToSelectAgain = false;
                final int ioRatio = this.ioRatio;
                boolean ranTasks;
                if (ioRatio == 100) {
                    try {
                        if (strategy > 0) {
                           // A positive strategy means I/O events are ready; process the selected keys.
                            processSelectedKeys();
                        }
                    } finally {
                        // Ensure we always run tasks.
                      // Run queued tasks.
                        ranTasks = runAllTasks();
                    }
                } else if (strategy > 0) {
                    final long ioStartTime = System.nanoTime();
                    try {
                        processSelectedKeys();
                    } finally {
                        // Ensure we always run tasks.
                        final long ioTime = System.nanoTime() - ioStartTime;
                        ranTasks = runAllTasks(ioTime * (100 - ioRatio) / ioRatio);
                    }
                } else {
                    ranTasks = runAllTasks(0); // This will run the minimum number of tasks
                }

                if (ranTasks || strategy > 0) {
                    if (selectCnt > MIN_PREMATURE_SELECTOR_RETURNS && logger.isDebugEnabled()) {
                        logger.debug("Selector.select() returned prematurely {} times in a row for Selector {}.",
                                selectCnt - 1, selector);
                    }
                    selectCnt = 0;
                } else if (unexpectedSelectorWakeup(selectCnt)) { // Unexpected wakeup (unusual case)
                    selectCnt = 0;
                }
            } catch (CancelledKeyException e) {
                // Harmless exception - log anyway
                if (logger.isDebugEnabled()) {
                    logger.debug(CancelledKeyException.class.getSimpleName() + " raised by a Selector {} - JDK bug?",
                            selector, e);
                }
            } catch (Throwable t) {
                handleLoopException(t);
            }
            // Always handle shutdown even if the loop processing threw an exception.
            try {
                if (isShuttingDown()) {
                    closeAll();
                    if (confirmShutdown()) {
                        return;
                    }
                }
            } catch (Throwable t) {
                handleLoopException(t);
            }
        }
    }
```

## 4. How a loop gets its thread

When a `NioEventLoopGroup` is created it installs an `Executor`. Unless you pass one, it is `ThreadPerTaskExecutor`:

```java
public final class ThreadPerTaskExecutor implements Executor {
    private final ThreadFactory threadFactory;

    public ThreadPerTaskExecutor(ThreadFactory threadFactory) {
        this.threadFactory = ObjectUtil.checkNotNull(threadFactory, "threadFactory");
    }

    @Override
    public void execute(Runnable command) {
        threadFactory.newThread(command).start();
    }
}
```

Each event loop receives this `ThreadPerTaskExecutor` in its constructor, wraps it with `ThreadExecutorMap.apply`, and stores the wrapper as the `executor` field of its superclass, `SingleThreadEventExecutor`:

```java
this.executor = ThreadExecutorMap.apply(executor, this);
```

That installs the current event loop as context for the thread that will run it. `ThreadExecutorMap.apply`:

```java
 public static Executor apply(final Executor executor, final EventExecutor eventExecutor) {
        ObjectUtil.checkNotNull(executor, "executor");
        ObjectUtil.checkNotNull(eventExecutor, "eventExecutor");
        return new Executor() {
        @Override
        public void execute(final Runnable command) {
            executor.execute(apply(command, eventExecutor));
        }
    };
```

`apply` returns an anonymous `Executor` around `ThreadPerTaskExecutor`. Calling it ends in `ThreadPerTaskExecutor.execute`, which starts a new thread to run the wrapped runnable.

The runnable is wrapped too:

```java
 public static Runnable apply(final Runnable command, final EventExecutor eventExecutor) {
        ObjectUtil.checkNotNull(command, "command");
        ObjectUtil.checkNotNull(eventExecutor, "eventExecutor");
        return new Runnable() {
            @Override
            public void run() {
                setCurrentEventExecutor(eventExecutor);
                try {
                    command.run();
                } finally {
                    setCurrentEventExecutor(null);
                }
            }
        };
    }
```

This anonymous `Runnable` ties the event loop to the thread that runs it: `setCurrentEventExecutor` stores the loop in a `FastThreadLocal`.

## 5. When the thread starts

The thread does not start when the loop is created. It starts with the first task, typically when the main thread registers a channel and submits a registration task through `execute`:

```java
 private void execute(Runnable task, boolean immediate) {
        // Check whether the caller is the event loop's own thread.
        boolean inEventLoop = inEventLoop();
        // Add the submitted task to the event loop's taskQueue.
        addTask(task);
        if (!inEventLoop) {
            // A caller outside the event loop triggers startup of its thread.
            // startThread is idempotent: start only if the event loop has not already started.
            startThread();
            if (isShutdown()) {
                boolean reject = false;
                try {
                    if (removeTask(task)) {
                        reject = true;
                    }
                } catch (UnsupportedOperationException e) {
                    // The task queue does not support removal so the best thing we can do is to just move on and
                    // hope we will be able to pick-up the task before its completely terminated.
                    // In worst case we will log on termination.
                }
                if (reject) {
                    reject();
                }
            }
        }

        if (!addTaskWakesUp && immediate) {
            wakeup(inEventLoop);
        }
    }
```

`startThread`:

```java
 private void startThread() {
        // Test whether the event loop has started.
        if (state == ST_NOT_STARTED) {
            // Atomically transition to the started state.
            if (STATE_UPDATER.compareAndSet(this, ST_NOT_STARTED, ST_STARTED)) {
                boolean success = false;
                try {
                     // Start the thread.
                    doStartThread();
                    success = true;
                } finally {
                    if (!success) {
                        // Restore the not-started state if doStartThread fails.
                        STATE_UPDATER.compareAndSet(this, ST_STARTED, ST_NOT_STARTED);
                    }
                }
            }
        }
    }
```

And `doStartThread`:

```java
private void doStartThread() {
        assert thread == null;
        // This executor is the wrapper around ThreadPerTaskExecutor discussed above.
        // It delegates to ThreadPerTaskExecutor.execute.
        // The thread factory creates a thread to execute the runnable.
        // ThreadExecutorMap.apply also wraps this anonymous runnable to install the current executor mapping.
        executor.execute(new Runnable() {
            @Override
            public void run() {
              // The event loop's execution thread has now started.
              // Store the current Thread to complete the association with this event loop.
                thread = Thread.currentThread();
                if (interrupted) {
                    thread.interrupt();
                }

                boolean success = false;
                updateLastExecutionTime();
                try {
                    // Invoke the overridden NioEventLoop.run implementation described earlier.
                    SingleThreadEventExecutor.this.run();
                    success = true;
                } catch (Throwable t) {
                    logger.warn("Unexpected exception from an event executor: ", t);
                } finally {
                   // The remaining code handles state changes and cleanup when execution ends.
                    for (;;) {
                        // Mark the event loop as shutting down.
                        int oldState = state;
                        if (oldState >= ST_SHUTTING_DOWN || STATE_UPDATER.compareAndSet(
                                SingleThreadEventExecutor.this, oldState, ST_SHUTTING_DOWN)) {
                            break;
                        }
                    }

                    // Check if confirmShutdown() was called at the end of the loop.
                    if (success && gracefulShutdownStartTime == 0) {
                        if (logger.isErrorEnabled()) {
                            logger.error("Buggy " + EventExecutor.class.getSimpleName() + " implementation; " +
                                    SingleThreadEventExecutor.class.getSimpleName() + ".confirmShutdown() must " +
                                    "be called before run() implementation terminates.");
                        }
                    }

                    try {
                        // Run all remaining tasks and shutdown hooks. At this point the event loop
                        // is in ST_SHUTTING_DOWN state still accepting tasks which is needed for
                        // graceful shutdown with quietPeriod.
                        // Check whether shutdown is complete.
                        for (;;) {
                            if (confirmShutdown()) {
                                break;
                            }
                        }

                        // Now we want to make sure no more tasks can be added from this point. This is
                        // achieved by switching the state. Any new tasks beyond this point will be rejected.
                        for (;;) {
                             // Transition to the shutdown state.
                            int oldState = state;
                            if (oldState >= ST_SHUTDOWN || STATE_UPDATER.compareAndSet(
                                    SingleThreadEventExecutor.this, oldState, ST_SHUTDOWN)) {
                                break;
                            }
                        }

                        // We have the final set of tasks in the queue now, no more can be added, run all remaining.
                        // No need to loop here, this is the final pass.
                        confirmShutdown();
                    } finally {
                        try {
                            cleanup();
                        } finally {
                            // Lets remove all FastThreadLocals for the Thread as we are about to terminate and notify
                            // the future. The user may block on the future and once it unblocks the JVM may terminate
                            // and start unloading classes.
                            // See https://github.com/netty/netty/issues/6596.
                            FastThreadLocal.removeAll();
                            // Transition to the terminated state.
                            STATE_UPDATER.set(SingleThreadEventExecutor.this, ST_TERMINATED);
                            threadLock.countDown();
                            int numUserTasks = drainTasks();
                            if (numUserTasks > 0 && logger.isWarnEnabled()) {
                                logger.warn("An event executor terminated with " +
                                        "non-empty task queue (" + numUserTasks + ')');
                            }
                            terminationFuture.setSuccess(null);
                        }
                    }
                }
            }
        });
    }
```

## Notes on the source

- The `run` excerpt uses the `nextWakeupNanos` / `curDeadlineNanos` selector-wakeup code from 4.1.53.Final.
- The loop mixes selected I/O, ordinary tasks and scheduled tasks; `ioRatio` sets how its time is split between I/O and tasks.
- "A channel's handlers run on its event loop" is the default. A handler added with its own executor runs elsewhere.

Source references (Netty 4.1.53.Final, released October 13, 2020):

- [NioEventLoop.java at the baseline](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/nio/NioEventLoop.java)
- [MultithreadEventLoopGroup.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/MultithreadEventLoopGroup.java)
- [SingleThreadEventExecutor.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/common/src/main/java/io/netty/util/concurrent/SingleThreadEventExecutor.java)
- [DefaultEventExecutorChooserFactory.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/common/src/main/java/io/netty/util/concurrent/DefaultEventExecutorChooserFactory.java)
- [ThreadExecutorMap.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/common/src/main/java/io/netty/util/internal/ThreadExecutorMap.java)
