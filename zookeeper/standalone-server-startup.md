---
layout: default
article: true
topic: ZooKeeper
lang: en
title: "How a Standalone ZooKeeper Server Starts"
order: 230
series_order: 3
description: "Trace configuration, request processors, connection acceptance, and NIO worker dispatch in a standalone ZooKeeper server."
---

# How a Standalone ZooKeeper Server Starts

This article starts a standalone ZooKeeper server and follows it until it accepts client connections: configuration, the server object, and the NIO threads that accept and dispatch I/O.

> **Source:** ZooKeeper 3.6.2 · commit `803c7f1a12f85978cb049af5e4ef23bd8b688715`. Code excerpts keep the original selection; comments are translated. Diagrams from the original article are redrawn with English labels.

## Why read it

I started using ZooKeeper years ago, when I used it to turn a file collector that had no distributed deployment or task dispatch into a distributed system. After reading *From Paxos to ZooKeeper: Principles and Practice of Distributed Consistency*, I debugged the standalone server in several scenarios, but I took no notes and forgot most of it. Reading the source again was worth it; this article records what I found.

## 1. Server startup

### Parse the configuration

The entry point is `org.apache.zookeeper.server.ZooKeeperServerMain`, with `zoo.cfg` as its argument. The config values become fields of `ServerConfig`. Two useful ones are the session timeout bounds. If you do not set them, the server derives them from `tickTime`:

| Setting | Default | With `tickTime=2000` |
| --- | --- | --- |
| `tickTime` | base interval for heartbeats and timeouts | 2000 ms |
| `minSessionTimeout` | 2 × `tickTime` | 4000 ms |
| `maxSessionTimeout` | 20 × `tickTime` | 40000 ms |

The defaults apply only when the value is `-1` (unset). The actual session timeout is negotiated with each client within these bounds.

The main `ServerConfig` fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `clientPortAddress` | `InetSocketAddress` | Address and port for client connections. |
| `secureClientPortAddress` | `InetSocketAddress` | Optional TLS client listener. |
| `dataDir` | `File` | Directory for snapshots. |
| `dataLogDir` | `File` | Directory for transaction logs; falls back to `dataDir`. |
| `tickTime` | `int` | Base timing interval. |
| `minSessionTimeout` / `maxSessionTimeout` | `int` | Session timeout bounds; `-1` selects the defaults above. |
| `maxClientCnxns` | `int` | Maximum connections from one IP address. |
| `listenBacklog` | `int` | Requested size of the socket accept backlog. |

### runFromConfig

`runFromConfig` builds the server from the parsed config in four steps:

1. **Create `FileTxnSnapLog`.** It holds `txnLog` and `snapLog`: the transaction-log and snapshot persistence implementations.

2. **Create `ZooKeeperServer`.** This object is the server itself and coordinates its data and request processing.

3. **Create the admin server.** It runs on Jetty and listens on port 8080 by default; open `http://ip:8080/commands` to list the available commands.

4. **Create `ServerCnxnFactory`.** It manages server-side connections. There are two implementations, `NIOServerCnxnFactory` and `NettyServerCnxnFactory`; NIO is the default.

Now look at `NIOServerCnxnFactory.configure`:

> **Note:** `sessionlessCnxnTimeout` limits connections that have **not** established a session yet, and it is also the bucket interval for connection expiry. It is not the negotiated session timeout. (The original annotation mixed these up.)

```java
 public void configure(InetSocketAddress addr, int maxcc, int backlog, boolean secure) throws IOException {
        if (secure) {
            throw new UnsupportedOperationException("SSL isn't supported in NIOServerCnxn");
        }
        configureSaslLogin();

        maxClientCnxns = maxcc;
        initMaxCnxns();
       // sessionlessCnxnTimeout is the timeout for a connection without a session.
        sessionlessCnxnTimeout = Integer.getInteger(ZOOKEEPER_NIO_SESSIONLESS_CNXN_TIMEOUT, 10000);
        // We also use the sessionlessCnxnTimeout as expiring interval for
        // cnxnExpiryQueue. These don't need to be the same, but the expiring
        // interval passed into the ExpiryQueue() constructor below should be
        // less than or equal to the timeout.
            // Container for connection expiration times.
            cnxnExpiryQueue = new ExpiryQueue<NIOServerCnxn>(sessionlessCnxnTimeout);
          // Thread that handles expired connections.
        expirerThread = new ConnectionExpirerThread();

        int numCores = Runtime.getRuntime().availableProcessors();
        // 32 cores sweet spot seems to be 4 selector threads
        // Derive the number of selector threads from the available processors.
        numSelectorThreads = Integer.getInteger(
            ZOOKEEPER_NIO_NUM_SELECTOR_THREADS,
            Math.max((int) Math.sqrt((float) numCores / 2), 1));
        if (numSelectorThreads < 1) {
            throw new IOException("numSelectorThreads must be at least 1");
        }

       // Obtain the number of worker threads handling I/O events.
        numWorkerThreads = Integer.getInteger(ZOOKEEPER_NIO_NUM_WORKER_THREADS, 2 * numCores);
        workerShutdownTimeoutMS = Long.getLong(ZOOKEEPER_NIO_SHUTDOWN_TIMEOUT, 5000);

        String logMsg = "Configuring NIO connection handler with "
            + (sessionlessCnxnTimeout / 1000) + "s sessionless connection timeout, "
            + numSelectorThreads + " selector thread(s), "
            + (numWorkerThreads > 0 ? numWorkerThreads : "no") + " worker threads, and "
            + (directBufferBytes == 0 ? "gathered writes." : ("" + (directBufferBytes / 1024) + " kB direct buffers."));
        LOG.info(logMsg);
       // Create numSelectorThreads SelectorThread instances.
        for (int i = 0; i < numSelectorThreads; ++i) {
            selectorThreads.add(new SelectorThread(i));
        }

        listenBacklog = backlog;
        // Open the server SocketChannel and bind it to the configured address.
        this.ss = ServerSocketChannel.open();
        ss.socket().setReuseAddress(true);
        LOG.info("binding to port {}", addr);
        if (listenBacklog == -1) {
            ss.socket().bind(addr);
        } else {
            ss.socket().bind(addr, listenBacklog);
        }
        // Make the server SocketChannel nonblocking.
        ss.configureBlocking(false);
        // Create the thread accepting client connections.
        acceptThread = new AcceptThread(ss, addr, selectorThreads);
    }
```

`configure` creates three kinds of thread. The I/O worker pool comes later, when the factory starts.

| Thread | Job |
| --- | --- |
| `ConnectionExpirerThread` | Closes connections whose expiry time has passed. |
| `SelectorThread` | Watches its connections for read/write readiness. |
| `AcceptThread` | Accepts new client connections. |

#### SelectorThread

The `SelectorThread` constructor:

```java
 public SelectorThread(int id) throws IOException {
            super("NIOServerCxnFactory.SelectorThread-" + id);
            this.id = id;
           // Every accepted SocketChannel enters acceptedQueue.
            acceptedQueue = new LinkedBlockingQueue<SocketChannel>();
          // When a connection's interest operations need updating, its SelectionKey enters updateQueue.
            updateQueue = new LinkedBlockingQueue<SelectionKey>();
        }
```

#### AcceptThread

The `AcceptThread` constructor:

```java
public AcceptThread(ServerSocketChannel ss, InetSocketAddress addr, Set<SelectorThread> selectorThreads) throws IOException {
             // The superclass creates the selector associated with AcceptThread.
            super("NIOServerCxnFactory.AcceptThread:" + addr);

            this.acceptSocket = ss;
          // Register OP_ACCEPT on the server channel to receive client connections.
            this.acceptKey = acceptSocket.register(selector, SelectionKey.OP_ACCEPT);
            // Each accepted connection is assigned one of selectorThreads.
            // That selector thread handles readiness events for this connection.
            this.selectorThreads = Collections.unmodifiableList(new ArrayList<SelectorThread>(selectorThreads));
            selectorIterator = this.selectorThreads.iterator();
        }
```

## 2. Start the service

The threads above exist but are not running yet, and some components are still missing. `NIOServerCnxnFactory.startup(ZooKeeperServer)` creates the rest and starts everything.

### NIOServerCnxnFactory.startup

```java
 @Override
    public void startup(ZooKeeperServer zks, boolean startServer) throws IOException, InterruptedException {
        // Start the previously constructed accept and selector threads.
        start();
        setZooKeeperServer(zks);
        if (startServer) {
           // Restore node data and session information from snapshots and transaction logs.
            zks.startdata();
           //
            zks.startup();
        }
    }
```

#### start()

```java
 public void start() {
        stopped = false;
        if (workerPool == null) {
            // Create the pool of I/O worker threads.
            workerPool = new WorkerService("NIOWorker", numWorkerThreads, false);
        }
       // Start SelectorThread instances.
        for (SelectorThread thread : selectorThreads) {
            if (thread.getState() == Thread.State.NEW) {
                thread.start();
            }
        }
        // Start AcceptThread.
        // ensure thread is started once and only once
        if (acceptThread.getState() == Thread.State.NEW) {
            acceptThread.start();
        }
    // Start connection expiration management.
        if (expirerThread.getState() == Thread.State.NEW) {
            expirerThread.start();
        }
    }
```

#### ZooKeeperServer.startup

```java
 public synchronized void startup() {
        if (sessionTracker == null) {
           // Create the session tracker to manage session expiration.
            createSessionTracker();
        }
       // Start the session tracker.
        startSessionTracker();
        // Set up the ZooKeeper request processor chain.
        // The standalone chain contains three processors.
       //PrepRequestProcessor --> SyncRequestProcessor --> FinalRequestProcessor
       // PrepRequestProcessor and SyncRequestProcessor run on separate threads and pass requests through queues.
        setupRequestProcessors();
        // Create and start RequestThrottler to control the number of requests.
       // This provides request throttling.
        startRequestThrottler();
        // Register JMX monitoring.
        registerJMX();
        // Start JVM pause monitoring.
        startJvmPauseMonitor();
        // Register metrics.
        registerMetrics();
        // Mark the server as running.
        setState(State.RUNNING);

        requestPathMetricsCollector.start();

        localSessionEnabled = sessionTracker.isLocalSessionsEnabled();
        notifyAll();
    }
```

### ContainerManager

`ContainerManager` manages **container znodes**: nodes meant to hold other nodes. When the last child of a container is deleted, the manager's periodic check finds the empty container and deletes it. It also handles TTL nodes when that feature is on. Deletion is a best-effort background task, not immediate.

## 3. The accept and selector threads

That is the whole startup. Now look closer at the two threads that handle connections: `AcceptThread` and `SelectorThread`.

### AcceptThread

After startup the server listens for clients on the configured port (2181 by default). `AcceptThread` accepts each connection and hands it to a `SelectorThread`, a reactor-style design. `AcceptThread.run`:

```java
// As discussed above, the AcceptThread constructor registers OP_ACCEPT on the server channel.
 public void run() {
            try {
                while (!stopped && !acceptSocket.socket().isClosed()) {
                    try {
                       // select contains the central acceptance logic.
                        select();
                    } catch (RuntimeException e) {
                        LOG.warn("Ignoring unexpected runtime exception", e);
                    } catch (Exception e) {
                        LOG.warn("Ignoring unexpected exception", e);
                    }
                }
            } finally {
                closeSelector();
                // This will wake up the selector threads, and tell the
                // worker thread pool to begin shutdown.
                if (!reconfiguring) {
                    NIOServerCnxnFactory.this.stop();
                }
                LOG.info("accept thread exitted run method");
            }
        }
```

`AcceptThread.select`:

```java
  private void select() {
            try {
              // Wait for a client connection event.
                selector.select();

                Iterator<SelectionKey> selectedKeys = selector.selectedKeys().iterator();
                while (!stopped && selectedKeys.hasNext()) {
                    SelectionKey key = selectedKeys.next();
                    selectedKeys.remove();

                    if (!key.isValid()) {
                        continue;
                    }
                    // Handle an acceptable key through doAccept.
                    if (key.isAcceptable()) {
                        if (!doAccept()) {
                            // If unable to pull a new connection off the accept
                            // queue, pause accepting to give us time to free
                            // up file descriptors and so the accept thread
                            // doesn't spin in a tight loop.
                            pauseAccept(10);
                        }
                    } else {
                        LOG.warn("Unexpected ops in accept select {}", key.readyOps());
                    }
                }
            } catch (IOException e) {
                LOG.warn("Ignoring IOException while selecting", e);
            }
        }
```

`AcceptThread.doAccept`:

```java
private boolean doAccept() {
            boolean accepted = false;
            SocketChannel sc = null;
            try {
               // Obtain the SocketChannel for the client connection.
                sc = acceptSocket.accept();
                accepted = true;
                if (limitTotalNumberOfCnxns()) {
                    throw new IOException("Too many connections max allowed is " + maxCnxns);
                }
                InetAddress ia = sc.socket().getInetAddress();
               // getClientCnxnCount counts connections created from this IP address.
                int cnxncount = getClientCnxnCount(ia);
                // Reject a connection if the per-client limit has been reached.
                if (maxClientCnxns > 0 && cnxncount >= maxClientCnxns) {
                    throw new IOException("Too many connections from " + ia + " - max is " + maxClientCnxns);
                }

                LOG.debug("Accepted socket connection from {}", sc.socket().getRemoteSocketAddress());

                sc.configureBlocking(false);

                 // Choose a SelectorThread in round-robin order for this connection.
                // Round-robin assign this connection to a selector thread
                if (!selectorIterator.hasNext()) {
                    selectorIterator = selectorThreads.iterator();
                }
                SelectorThread selectorThread = selectorIterator.next();
               // Add the connection to its assigned SelectorThread queue.
                if (!selectorThread.addAcceptedConnection(sc)) {
                    throw new IOException("Unable to add connection to selector queue"
                                          + (stopped ? " (shutdown in progress)" : ""));
                }
                acceptErrorLogger.flush();
            } catch (IOException e) {
                // accept, maxClientCnxns, configureBlocking
                ServerMetrics.getMetrics().CONNECTION_REJECTED.add(1);
                acceptErrorLogger.rateLimitLog("Error accepting new connection: " + e.getMessage());
                fastCloseSock(sc);
            }
            return accepted;
        }

    }
```

### SelectorThread

`SelectorThread.run`:

```java
// The run loop calls three important methods.
// select(), processAcceptedConnections(), processInterestOpsUpdateRequests()
 public void run() {
            try {
                while (!stopped) {
                    try {
                        select();
                        processAcceptedConnections();
                        processInterestOpsUpdateRequests();
                    } catch (RuntimeException e) {
                        LOG.warn("Ignoring unexpected runtime exception", e);
                    } catch (Exception e) {
                        LOG.warn("Ignoring unexpected exception", e);
                    }
                }

                // Close connections still pending on the selector. Any others
                // with in-flight work, let drain out of the work queue.
                for (SelectionKey key : selector.keys()) {
                    NIOServerCnxn cnxn = (NIOServerCnxn) key.attachment();
                    if (cnxn.isSelectable()) {
                        cnxn.close(ServerCnxn.DisconnectReason.SERVER_SHUTDOWN);
                    }
                    cleanupSelectionKey(key);
                }
                SocketChannel accepted;
                while ((accepted = acceptedQueue.poll()) != null) {
                    fastCloseSock(accepted);
                }
                updateQueue.clear();
            } finally {
                closeSelector();
                // This will wake up the accept thread and the other selector
                // threads, and tell the worker thread pool to begin shutdown.
                NIOServerCnxnFactory.this.stop();
                LOG.info("selector thread exitted run method");
            }
        }
```

Its loop calls three methods: `select()`, `processAcceptedConnections()` and `processInterestOpsUpdateRequests()`. Start with `processAcceptedConnections()`, but first look at the `selectorThread.addAcceptedConnection()` call made by `AcceptThread.doAccept`:

```java
 public boolean addAcceptedConnection(SocketChannel accepted) {
            // Add the accepted channel to acceptedQueue and wake the selector from select().
            if (stopped || !acceptedQueue.offer(accepted)) {
                return false;
            }
            wakeupSelector();
            return true;
        }
```

#### processAcceptedConnections

`processAcceptedConnections` takes the SocketChannels waiting in `acceptedQueue` and registers them:

> **Note:** the original annotation called this queue `updateQueue`. `updateQueue` is a different queue: it holds SelectionKeys whose interest set needs refreshing.

```java
private void processAcceptedConnections() {
            SocketChannel accepted;
             // Take a SocketChannel from acceptedQueue.
            while (!stopped && (accepted = acceptedQueue.poll()) != null) {
                SelectionKey key = null;
                try {
                    // Register OP_READ on the selector belonging to this SelectorThread.
                    key = accepted.register(selector, SelectionKey.OP_READ);
                    // Wrap the SocketChannel in a server-side NIOServerCnxn.
                    NIOServerCnxn cnxn = createConnection(accepted, key, this);
                    key.attach(cnxn);
                   // Register the connection with the factory; cnxnExpiry will track its expiration.
                    addCnxn(cnxn);
                } catch (IOException e) {
                    // register, createConnection
                    cleanupSelectionKey(key);
                    fastCloseSock(accepted);
                }
            }
        }
```

After this, the channel's selector watches it for `OP_READ`.

#### select

```java
private void select() {
            try {
               // Obtain readiness events.
                selector.select();

                Set<SelectionKey> selected = selector.selectedKeys();
                ArrayList<SelectionKey> selectedList = new ArrayList<SelectionKey>(selected);
                Collections.shuffle(selectedList);
                Iterator<SelectionKey> selectedKeys = selectedList.iterator();
                while (!stopped && selectedKeys.hasNext()) {
                    SelectionKey key = selectedKeys.next();
                    selected.remove(key);

                    if (!key.isValid()) {
                        cleanupSelectionKey(key);
                        continue;
                    }
                    if (key.isReadable() || key.isWritable()) {
                       // Handle a readiness event through handleIO.
                        handleIO(key);
                    } else {
                        LOG.warn("Unexpected ops in select {}", key.readyOps());
                    }
                }
            } catch (IOException e) {
                LOG.warn("Ignoring IOException while selecting", e);
            }
        }
```

#### handleIO

```java
  private void handleIO(SelectionKey key) {
            // Wrap a channel's readiness event in an IOWorkRequest.
           // Submit the IOWorkRequest to the worker pool.
            IOWorkRequest workRequest = new IOWorkRequest(this, key);
            NIOServerCnxn cnxn = (NIOServerCnxn) key.attachment();

            // Stop selecting this key while processing on its
            // connection
            cnxn.disableSelectable();
            // Temporarily disable all interest operations on the key.
           // ZooKeeper serializes I/O handling for an individual connection.
           // How is overlapping work on one connection prevented?
           // Disable interests when work is submitted so the selector does not dispatch another task for this channel.
          // Re-register interests after the current task completes so subsequent readiness can be handled.
            key.interestOps(0);
            // Update the connection's expiration time.
            touchCnxn(cnxn);
            // Submit the IOWorkRequest to the I/O worker pool.
            workerPool.schedule(workRequest);
        }
```

`handleIO` clears the key's interest set before handing the work to the pool. That way, one channel never has two I/O tasks running at once. (This serializes readiness handling per channel; it does not mean every network event becomes a separately ordered message.)

So how does the channel become selectable again after the task finishes? That is the job of `processInterestOpsUpdateRequests`:

```java
// After handling I/O, IOWorkRequest puts the connection's SelectionKey into updateQueue.
 private void processInterestOpsUpdateRequests() {
            SelectionKey key;
           // Drain the SelectionKeys from updateQueue.
            while (!stopped && (key = updateQueue.poll()) != null) {
                if (!key.isValid()) {
                    cleanupSelectionKey(key);
                }
              // Retrieve NIOServerCnxn from the key's attachment.
                NIOServerCnxn cnxn = (NIOServerCnxn) key.attachment();
                if (cnxn.isSelectable()) {
                    // Re-register interests according to the connection's current read/write state.
                    key.interestOps(cnxn.getInterestOps());
                }
            }
        }
```

The whole accept-and-dispatch path:

[![Accept and dispatch NIO work](assets/standalone-server-startup-03.svg){: .diagram}](assets/standalone-server-startup-03.svg)

The server also starts threads that expire sessions and connections. They are covered in [How ExpiryQueue Manages Connection and Session Timeouts](expiry-queue.html).

## Source references

- [ZooKeeperServerMain.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/ZooKeeperServerMain.java)
- [ServerConfig.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/ServerConfig.java)
- [ZooKeeperServer.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/ZooKeeperServer.java)
- [NIOServerCnxnFactory.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/NIOServerCnxnFactory.java)
- [ContainerManager.java](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/ContainerManager.java)
