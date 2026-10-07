---
layout: default
article: true
topic: Netty
lang: en
title: "Following Netty Server Startup"
description: "Follow channel construction, registration, pipeline initialization, port binding, and connection acceptance."
order: 420
series_order: 2
---

# Following Netty Server Startup

This article follows a Netty server from `bind(port)` to the moment it accepts connections, using `EchoServer` from Netty's examples module.

> **Source:** Netty 4.1.53.Final (October 2020) · NIO transport. Code excerpts keep the original selection; comments are translated.

## 1. A typical server

```java
        EventLoopGroup bossGroup = new NioEventLoopGroup(1);
        EventLoopGroup workerGroup = new NioEventLoopGroup();
        final EchoServerHandler serverHandler = new EchoServerHandler();
        try {
            ServerBootstrap b = new ServerBootstrap();
            b.group(bossGroup, workerGroup)
             .channel(NioServerSocketChannel.class)
             .option(ChannelOption.SO_BACKLOG, 100)
             .handler(new LoggingHandler(LogLevel.INFO))
             .childHandler(new ChannelInitializer<SocketChannel>() {
                 @Override
                 public void initChannel(SocketChannel ch) throws Exception {
                     ChannelPipeline p = ch.pipeline();
                     p.addLast(new DelimiterBasedFrameDecoder(Integer.MAX_VALUE, Unpooled.copiedBuffer("$".getBytes())));
                     p.addLast(serverHandler);
                 }
             });

            // Start the server.
            ChannelFuture f = b.bind(PORT).sync();

            // Wait until the server socket is closed.
            f.channel().closeFuture().sync();
        } finally {
            // Shut down all event loops to terminate all threads.
            bossGroup.shutdownGracefully();
            workerGroup.shutdownGracefully();
        }
```

Almost every Netty server looks like this. The pieces:

| Piece | Job |
| --- | --- |
| `bossGroup` | Event loops that accept connections (the classic NIO **acceptor**). One thread is usually enough. |
| `workerGroup` | Event loops for accepted channels. Each accepted channel is bound to one of them for its whole life. See [the thread model](thread-model.html). |

`ServerBootstrap` is the server's builder:

| Method | Sets |
| --- | --- |
| `group` | The boss and worker groups. |
| `channel` | The server channel type. `NioServerSocketChannel` wraps Java NIO's `ServerSocketChannel`. |
| `option` | Options on the listening channel. |
| `childOption` | Options on accepted channels. |
| `handler` | A handler on the listening channel's pipeline. |
| `childHandler` | The initializer or handler for accepted channels' pipelines. |

## 2. The startup sequence

Everything starts with `serverBootstrap.bind(port)`, which has two parts:

1. **`initAndRegister`**: create, initialize and register the server channel.
2. **`doBind`**: bind that channel to the address and port.

[![Netty server startup: bind() runs initAndRegister on the main thread (create the NioServerSocketChannel, init its pipeline), registers it on the boss event loop, then doBind0 runs bind through the pipeline to HeadContext and unsafe.bind; channelActive triggers doBeginRead, which adds OP_ACCEPT.](assets/server-startup-01.svg)](assets/server-startup-01.svg)

### `initAndRegister`

```java
// The future return value allows registration to complete asynchronously.
final ChannelFuture initAndRegister() {
        Channel channel = null;
        try {
         // channelFactory was configured from the selected NioServerSocketChannel class.
         // Create the listening channel through channelFactory.newChannel.
            channel = channelFactory.newChannel();
           // Initialize the newly created channel.
            init(channel);
        } catch (Throwable t) {
            if (channel != null) {
                // channel can be null if newChannel crashed (eg SocketException("too many open files"))
                channel.unsafe().closeForcibly();
                // as the Channel is not registered yet we need to force the usage of the GlobalEventExecutor
                return new DefaultChannelPromise(channel, GlobalEventExecutor.INSTANCE).setFailure(t);
            }
            // as the Channel is not registered yet we need to force the usage of the GlobalEventExecutor
            return new DefaultChannelPromise(new FailedChannel(), GlobalEventExecutor.INSTANCE).setFailure(t);
        }

       // Initialization is complete; now register the channel.
        ChannelFuture regFuture = config().group().register(channel);
        if (regFuture.cause() != null) {
            if (channel.isRegistered()) {
                channel.close();
            } else {
                channel.unsafe().closeForcibly();
            }
        }

        // If we are here and the promise is not failed, it's one of the following cases:
        // 1) If we attempted registration from the event loop, the registration has been completed at this point.
        //    i.e. It's safe to attempt bind() or connect() now because the channel has been registered.
        // 2) If we attempted registration from the other thread, the registration request has been successfully
        //    added to the event loop's task queue for later execution.
        //    i.e. It's safe to attempt bind() or connect() now:
        //         because bind() or connect() will be executed *after* the scheduled registration task is executed
        //         because register(), bind(), and connect() are all bound to the same thread.

        return regFuture;
    }
```

For a server it does three things:

1. Create the `NioServerSocketChannel`.
2. Initialize it.
3. Register it with an event loop.

## 3. Create the channel

The channel factory calls the channel class's no-argument constructor by reflection:

```java
  public NioServerSocketChannel() {
        // DEFAULT_SELECTOR_PROVIDER is the static SelectorProvider used by this channel.
        this(newSocket(DEFAULT_SELECTOR_PROVIDER));
    }
```

`newSocket` opens the underlying Java `ServerSocketChannel`. This is where Netty's channel wraps Java NIO:

```java
private static ServerSocketChannel newSocket(SelectorProvider provider) {
        try {
            /**
             *  Use the {@link SelectorProvider} to open {@link SocketChannel} and so remove condition in
             *  {@link SelectorProvider#provider()} which is called by each ServerSocketChannel.open() otherwise.
             *
             *  See <a href="https://github.com/netty/netty/issues/2308">#2308</a>.
             */
            // Create the underlying server channel through SelectorProvider.
            // In ordinary Java NIO code this is commonly written as ServerSocketChannel.open().
           // That static method itself delegates to provider.openServerSocketChannel().
            return provider.openServerSocketChannel();
        } catch (IOException e) {
            throw new ChannelException(
                    "Failed to open a server socket.", e);
        }
    }
```

Then the constructor fills in the fields of the channel and its superclasses:

```java
public NioServerSocketChannel(ServerSocketChannel channel) {
       // Initialize the superclass.
        super(null, channel, SelectionKey.OP_ACCEPT);
       // Create the configuration associated with this server channel.
       // It includes receive-loop settings and the receive-buffer allocation policy.
        config = new NioServerSocketChannelConfig(this, javaChannel().socket());
    }
```

Each superclass layer adds its part:

**`AbstractNioChannel`** stores the Java channel in `ch`, sets `readInterestOp` to `OP_ACCEPT` (bit value 16) and makes the channel non-blocking:

```java
protected AbstractNioChannel(Channel parent, SelectableChannel ch, int readInterestOp) {
        super(parent);
        this.ch = ch;
        this.readInterestOp = readInterestOp;
        try {
            ch.configureBlocking(false);
        } catch (IOException e) {
            try {
                ch.close();
            } catch (IOException e2) {
                logger.warn(
                            "Failed to close a partially initialized socket.", e2);
            }

            throw new ChannelException("Failed to enter non-blocking mode.", e);
        }
    }
```

**`AbstractChannel`** creates the `NioMessageUnsafe` that performs the low-level operations, and the channel's `DefaultChannelPipeline`:

```java
 protected AbstractChannel(Channel parent) {
        this.parent = parent;
        id = newId();
        unsafe = newUnsafe();
        pipeline = newChannelPipeline();
    }
```

The server channel now exists. See [the pipeline article](pipeline.html) for how its pipeline works.

## 4. Initialize it: `init`

`ServerBootstrap.init`:

```java
void init(Channel channel) {
        setChannelOptions(channel, newOptionsArray(), logger);
        setAttributes(channel, attrs0().entrySet().toArray(EMPTY_ATTRIBUTE_ARRAY));

        ChannelPipeline p = channel.pipeline();

        final EventLoopGroup currentChildGroup = childGroup;
        final ChannelHandler currentChildHandler = childHandler;
        final Entry<ChannelOption<?>, Object>[] currentChildOptions;
        synchronized (childOptions) {
            currentChildOptions = childOptions.entrySet().toArray(EMPTY_OPTION_ARRAY);
        }
        final Entry<AttributeKey<?>, Object>[] currentChildAttrs = childAttrs.entrySet().toArray(EMPTY_ATTRIBUTE_ARRAY);

        p.addLast(new ChannelInitializer<Channel>() {
            @Override
            public void initChannel(final Channel ch) {
                final ChannelPipeline pipeline = ch.pipeline();
                ChannelHandler handler = config.handler();
                if (handler != null) {
                    pipeline.addLast(handler);
                }

                ch.eventLoop().execute(new Runnable() {
                    @Override
                    public void run() {
                        pipeline.addLast(new ServerBootstrapAcceptor(
                                ch, currentChildGroup, currentChildHandler, currentChildOptions, currentChildAttrs));
                    }
                });
            }
        });
    }
```

Its main job is to install, through a `ChannelInitializer`, two handlers on the server pipeline:

1. the server handler your application configured, and

2. Netty's own **`ServerBootstrapAcceptor`**. This inbound handler takes every accepted `NioSocketChannel`, applies the child options and attributes, adds `childHandler`, and registers the channel with the worker group:

```java
public void channelRead(ChannelHandlerContext ctx, Object msg) {
            // For this server, msg is an accepted NioSocketChannel.

            final Channel child = (Channel) msg;

            child.pipeline().addLast(childHandler);

            setChannelOptions(child, childOptions, logger);
            setAttributes(child, childAttrs);
            try {
                // Register the accepted channel with the child event-loop group.

                childGroup.register(child).addListener(new ChannelFutureListener() {
                    @Override
                    public void operationComplete(ChannelFuture future) throws Exception {
                        if (!future.isSuccess()) {
                            forceClose(child, future.cause());
                        }
                    }
                });
            } catch (Throwable t) {
                forceClose(child, t);
            }
        }
```

The two are added at different times. `ServerBootstrapAcceptor` is added by a task submitted to the listening channel's event loop. During `init` the channel is not registered yet, so the handler-added callbacks wait as pending callbacks. Registration runs them later, and only then is the acceptor added.

## 5. Register it

Registration picks an event loop from `bossGroup` (usually the only one) and binds the server channel to it. It ends in `unsafe.register`:

```java
 public final void register(EventLoop eventLoop, final ChannelPromise promise) {
            ObjectUtil.checkNotNull(eventLoop, "eventLoop");
            if (isRegistered()) {
                promise.setFailure(new IllegalStateException("registered to an event loop already"));
                return;
            }
            if (!isCompatible(eventLoop)) {
                promise.setFailure(
                        new IllegalStateException("incompatible event loop type: " + eventLoop.getClass().getName()));
                return;
            }
          // Associate the channel with the event loop selected from bossGroup.
            AbstractChannel.this.eventLoop = eventLoop;
           // Check whether the caller is already on that event-loop thread.
            if (eventLoop.inEventLoop()) {
                register0(promise);
            } else {
                try {
                  // Submit register0 as an event-loop task.
                    eventLoop.execute(new Runnable() {
                        @Override
                        public void run() {
                            register0(promise);
                        }
                    });
                } catch (Throwable t) {
                    logger.warn(
                            "Force-closing a channel whose registration task was not accepted by an event loop: {}",
                            AbstractChannel.this, t);
                    closeForcibly();
                    closeFuture.setClosed();
                    safeSetFailure(promise, t);
                }
            }
        }
```

Submitting the registration task starts the event loop's thread if it is not running yet ([thread model](thread-model.html) explains how).

### `register0`

`register0` runs on the listening channel's event loop:

```java
 private void register0(ChannelPromise promise) {
            try {
                // check if the channel is still open as it could be closed in the mean time when the register
                // call was outside of the eventLoop
                if (!promise.setUncancellable() || !ensureOpen(promise)) {
                    return;
                }
                boolean firstRegistration = neverRegistered;
               // Register the underlying Java channel with the selector.
                doRegister();
                neverRegistered = false;
                registered = true;

                // Ensure we call handlerAdded(...) before we actually notify the promise. This is needed as the
                // user may already fire events through the pipeline in the ChannelFutureListener.
                 // Invoke the handler-added callbacks that were pending before registration.
                // This allows the initializer to arrange installation of ServerBootstrapAcceptor.
                pipeline.invokeHandlerAddedIfNeeded();
                // Complete the registration promise successfully.
                safeSetSuccess(promise);
                 // Fire channelRegistered through the inbound pipeline.
                pipeline.fireChannelRegistered();
                // Only fire a channelActive if the channel has never been registered. This prevents firing
                // multiple channel actives if the channel is deregistered and re-registered.
                // Check whether the listening channel is already active.
                if (isActive()) {
                    if (firstRegistration) {
                        pipeline.fireChannelActive();
                    } else if (config().isAutoRead()) {
                        // This channel was registered before and autoRead() is set. This means we need to begin read
                        // again so that we process inbound data.
                        //
                        // See https://github.com/netty/netty/issues/4805
                        beginRead();
                    }
                }
            } catch (Throwable t) {
                // Close the channel directly to avoid FD leak.
                closeForcibly();
                closeFuture.setClosed();
                safeSetFailure(promise, t);
            }
        }

// doRegister associates the underlying server channel with the selector.
protected void doRegister() throws Exception {
        boolean selected = false;
        for (;;) {
            try {
   // Initial selector interest is zero. Why?
// The channel has not bound yet; once it becomes active, beginning a read adds OP_ACCEPT interest.
                selectionKey = javaChannel().register(eventLoop().unwrappedSelector(), 0, this);
                return;
            } catch (CancelledKeyException e) {
                if (!selected) {
                    // Force the Selector to select now as the "canceled" SelectionKey may still be
                    // cached and not removed because no Select.select(..) operation was called yet.
                    eventLoop().selectNow();
                    selected = true;
                } else {
                    // We forced a select operation on the selector before but the SelectionKey is still cached
                    // for whatever reason. JDK bug ?
                    throw e;
                }
            }
        }
    }
```

The channel is now created, initialized and registered.

## 6. Bind the address: `doBind0`

`doBind0` submits a task to the channel's event loop that binds it to the address and port:

```java
 private static void doBind0(
            final ChannelFuture regFuture, final Channel channel,
            final SocketAddress localAddress, final ChannelPromise promise) {

        // This method is invoked before channelRegistered() is triggered.  Give user handlers a chance to set up
        // the pipeline in its channelRegistered() implementation.
        channel.eventLoop().execute(new Runnable() {
            @Override
            public void run() {
                if (regFuture.isSuccess()) {
                    channel.bind(localAddress, promise).addListener(ChannelFutureListener.CLOSE_ON_FAILURE);
                } else {
                    promise.setFailure(regFuture.cause());
                }
            }
        });
    }
```

The call chain:

```text
channel.bind → pipeline.bind → tail.bind
```

`tail.bind`:

```java
 public ChannelFuture bind(final SocketAddress localAddress, final ChannelPromise promise) {
        ObjectUtil.checkNotNull(localAddress, "localAddress");
        if (isNotValidPromise(promise, false)) {
            // cancelled
            return promise;
        }
      // Find the next context capable of handling the outbound bind operation.
        final AbstractChannelHandlerContext next = findContextOutbound(MASK_BIND);
        EventExecutor executor = next.executor();
        if (executor.inEventLoop()) {
            next.invokeBind(localAddress, promise);
        } else {
            safeExecute(executor, new Runnable() {
                @Override
                public void run() {
                    next.invokeBind(localAddress, promise);
                }
            }, promise, null, false);
        }
        return promise;
    }
```

`bind` is an **outbound** operation, so it travels from the tail toward the head through outbound handlers. It ends at `HeadContext`:

```java
        @Override
        public void bind(
                ChannelHandlerContext ctx, SocketAddress localAddress, ChannelPromise promise) {
            unsafe.bind(localAddress, promise);
        }
```

That delegates to `unsafe.bind`:

```java
 public final void bind(final SocketAddress localAddress, final ChannelPromise promise) {
            assertEventLoop();

            if (!promise.setUncancellable() || !ensureOpen(promise)) {
                return;
            }

            // See: https://github.com/netty/netty/issues/576
            if (Boolean.TRUE.equals(config().getOption(ChannelOption.SO_BROADCAST)) &&
                localAddress instanceof InetSocketAddress &&
                !((InetSocketAddress) localAddress).getAddress().isAnyLocalAddress() &&
                !PlatformDependent.isWindows() && !PlatformDependent.maybeSuperUser()) {
                // Warn a user about the fact that a non-root user can't receive a
                // broadcast packet on *nix if the socket is bound on non-wildcard address.
                logger.warn(
                        "A non-root user can't receive a broadcast packet if the socket " +
                        "is not bound to a wildcard address; binding to a non-wildcard " +
                        "address (" + localAddress + ") anyway as requested.");
            }

            boolean wasActive = isActive();
            try {
               // Perform the underlying transport bind operation.
                doBind(localAddress);
            } catch (Throwable t) {
                safeSetFailure(promise, t);
                closeIfClosed();
                return;
            }
            // After a successful bind, a previously inactive channel becomes active.
          // Submit a task to fire channelActive from the pipeline head.
         // The head's channelActive callback is examined below.
            if (!wasActive && isActive()) {
                invokeLater(new Runnable() {
                    @Override
                    public void run() {
                        pipeline.fireChannelActive();
                    }
                });
            }

            safeSetSuccess(promise);
        }
```

### `doBind`

The real bind, in `NioServerSocketChannel.doBind`:

```java
   protected void doBind(SocketAddress localAddress) throws Exception {
      // Use the appropriate ServerSocketChannel bind API for this Java version.
       if (PlatformDependent.javaVersion() >= 7) {
            javaChannel().bind(localAddress, config.getBacklog());
        } else {
            javaChannel().socket().bind(localAddress, config.getBacklog());
        }
    }
```

## 7. Start accepting

After binding, `HeadContext.channelActive` first passes `channelActive` down the inbound pipeline, then calls `readIfIsAutoRead`. With auto-read on (the default), that starts a read, which adds `OP_ACCEPT` to the channel's selector interests:

```java
 @Override
        public void channelActive(ChannelHandlerContext ctx) {
            ctx.fireChannelActive();

            readIfIsAutoRead();
        }
```

The call chain is another outbound trip, like `bind`:

```text
readIfIsAutoRead → channel.read() → pipeline.read() → tail.read()
```

`tail.read`:

```java
    public ChannelHandlerContext read() {
      // Find outbound contexts matching MASK_READ; eventually reach HeadContext.
        final AbstractChannelHandlerContext next = findContextOutbound(MASK_READ);
        EventExecutor executor = next.executor();
        if (executor.inEventLoop()) {
            next.invokeRead();
        } else {
            Tasks tasks = next.invokeTasks;
            if (tasks == null) {
                next.invokeTasks = tasks = new Tasks(next);
            }
            executor.execute(tasks.invokeReadTask);
        }

        return this;
    }
```

It reaches the head and continues:

```text
headContext.invokeRead() → headHandler.read() → unsafe.beginRead() → channel.doBeginRead()
```

`channel.doBeginRead`:

```java
protected void doBeginRead() throws Exception {
        // Channel.read() or ChannelHandlerContext.read() was called
        final SelectionKey selectionKey = this.selectionKey;
        if (!selectionKey.isValid()) {
            return;
        }

        readPending = true;
        // Before beginning the first read, interestOps is zero.
        final int interestOps = selectionKey.interestOps();
        if ((interestOps & readInterestOp) == 0) {
             // Add readInterestOp, which is OP_ACCEPT for a NioServerSocketChannel.
            selectionKey.interestOps(interestOps | readInterestOp);
        }
    }
```

From here the boss event loop's selector reports new connections, and `ServerBootstrapAcceptor` hands each one to the worker group. Startup is complete.

## Notes on the source

- `initAndRegister` returns a future because registration may finish later on the chosen event loop. Creating the channel and calling `init` happen on the calling thread.
- The listening channel registers for `OP_ACCEPT`; accepted channels register for `OP_READ`.
- Interest registration happens automatically only with `autoRead`, which the example leaves on.

Source references (Netty 4.1.53.Final, released October 13, 2020):

- [EchoServer.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/example/src/main/java/io/netty/example/echo/EchoServer.java)
- [AbstractBootstrap.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/bootstrap/AbstractBootstrap.java)
- [ServerBootstrap.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/bootstrap/ServerBootstrap.java)
- [NioServerSocketChannel.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/socket/nio/NioServerSocketChannel.java)
- [AbstractChannel.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/AbstractChannel.java)
- [AbstractNioChannel.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/nio/AbstractNioChannel.java)
