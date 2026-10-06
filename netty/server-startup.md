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

## Introduction
We will use `EchoServer` from Netty's examples module to follow the startup of a server built on Netty.

## Scope
All of the following analysis uses the NIO transport.

## A typical server startup example

```

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

A Netty server normally contains configuration similar to this example. Here are its important pieces.
- bossGroup
In the classic NIO model, an acceptor handles connection requests. In Netty, `bossGroup` supplies the event loop for this work. A simple server commonly creates the boss group with one thread.
- workerGroup
Each accepted connection becomes a socket channel assigned to an event loop. That event loop handles its subsequent I/O events. `workerGroup` supplies these child-channel event loops. See [Netty's Thread Model](thread-model.html) for a detailed explanation.

- ServerBootstrap
`ServerBootstrap` is the server bootstrap class. Its configuration methods include:
1. `group` sets the acceptor and worker groups.
2. `channel` sets the server channel type. `NioServerSocketChannel` wraps Java NIO's `ServerSocketChannel`.
3. `option` sets options on the listening server channel.
4. `childOption` sets options on accepted socket channels.
5. `handler` installs a handler on the listening channel's pipeline.
6. `childHandler` installs the initializer or handler for accepted channels' pipelines.

## The server startup sequence
The entry point is `serverBootstrap.bind(port)`. Binding contains two main parts:
- initAndRegister
Create, initialize, and register the server channel; we will examine those steps below.

- doBind
Bind the listening channel to the specified address and port.
### initAndRegister

```

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

For a server, `initAndRegister` performs three central steps:
1. Create the `NioServerSocketChannel`.
2. Initialize it.
3. Register it.

Examine these steps individually.
- #### Creating NioServerSocketChannel
The channel factory uses reflection to call the channel class's no-argument constructor.

```

  public NioServerSocketChannel() {
        // DEFAULT_SELECTOR_PROVIDER is the static SelectorProvider used by this channel.
        this(newSocket(DEFAULT_SELECTOR_PROVIDER));
    }

```

`newSocket` creates the underlying Java `ServerSocketChannel`, illustrating how Netty's channel wraps Java NIO.

```

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

Next, initialize the important fields on the channel and its superclasses.

```

public NioServerSocketChannel(ServerSocketChannel channel) {
       // Initialize the superclass.
        super(null, channel, SelectionKey.OP_ACCEPT);
       // Create the configuration associated with this server channel.
       // It includes receive-loop settings and the receive-buffer allocation policy.
        config = new NioServerSocketChannelConfig(this, javaChannel().socket());
    }

```

Here is the initialization performed by the superclass layers.

> **AbstractNioChannel**
> - Store the underlying server channel in `ch`.
> - Set `readInterestOp` to `OP_ACCEPT`, whose bit value is 16.
> - Configure the underlying channel as nonblocking.

```

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


> __AbstractChannel__
> - Create `NioMessageUnsafe`, the implementation that drives the low-level channel operations.
> - Create the channel's `DefaultChannelPipeline`.

```

 protected AbstractChannel(Channel parent) {
        this.parent = parent;
        id = newId();
        unsafe = newUnsafe();
        pipeline = newChannelPipeline();
    }

```

The server channel is now constructed. See [Netty's Event Pipeline](pipeline.html) for the pipeline implementation.


---
## Initializing NioServerSocketChannel: init
Here is `ServerBootstrap.init`:

```

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

The main purpose is to use a `ChannelInitializer` to install two handlers on the server pipeline:
1. The server handler configured by the application.

2. Netty's built-in `ServerBootstrapAcceptor`. This inbound handler configures accepted `NioSocketChannel` instances with the child options and attributes, installs `childHandler`, and registers them with `childGroup`.

```

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


The two handlers are installed differently. `ServerBootstrapAcceptor` is added by a runnable submitted to the listening channel's event loop. During `init`, the channel has not registered yet, so handler-added callbacks are retained as pending callbacks. Registration later invokes those callbacks, and initialization schedules the acceptor insertion.

## Registering NioServerSocketChannel
Registration selects an event loop from `bossGroup` and associates the server channel with it. A simple boss group normally has one event loop. The final operation is `unsafe.register`; its source follows.

```

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

Submitting this registration task starts the event-loop thread if needed. [Netty's Thread Model](thread-model.html) explains thread startup.
- register0
`register0` executes on the listening channel's event-loop thread.
Here is its source:

```

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


The channel is now initialized and registered.

---
Next, examine how it binds to the local address.
## doBind0
`doBind0` submits a task to the channel's event loop that binds the channel to the specified address and port.

```

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

Follow the call chain.
channel.bind --> pipeline.bind --> tail.bind
Here is `tail.bind`:

```

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

The bind operation starts at the tail and travels toward the head through outbound handlers. The final transport handler is `HeadContext`; here is its `bind` method:

```

        @Override
        public void bind(
                ChannelHandlerContext ctx, SocketAddress localAddress, ChannelPromise promise) {
            unsafe.bind(localAddress, promise);
        }

```

This delegates to the familiar `unsafe`. Here is `unsafe.bind`:

```

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

### doBind
Here is the actual `NioServerSocketChannel.doBind` implementation:

```

   protected void doBind(SocketAddress localAddress) throws Exception {
      // Use the appropriate ServerSocketChannel bind API for this Java version.
       if (PlatformDependent.javaVersion() >= 7) {
            javaChannel().bind(localAddress, config.getBacklog());
        } else {
            javaChannel().socket().bind(localAddress, config.getBacklog());
        }
    }

```

### The head handler's channelActive callback
The head first propagates `channelActive` through the inbound pipeline, then calls `readIfIsAutoRead`. With automatic reading enabled, this initiates a read operation and adds `OP_ACCEPT` to the listening channel's selector interests.

```

 @Override
        public void channelActive(ChannelHandlerContext ctx) {
            ctx.fireChannelActive();

            readIfIsAutoRead();
        }

```

Follow the `readIfIsAutoRead` call chain.
readIfIsAutoRead --> channel.read() --> pipeline.read() --> tail.read();
It has the same outbound traversal structure as the earlier bind operation.
Here is `tail.read`:

```

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

Continue through the head context's read invocation.
headContext.invokeRead() --> headHandler.read()  -->unsafe.beginRead() -->channel.doBeginRead()
Here is `channel.doBeginRead`:

```

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

This completes the server startup walkthrough.


## Source version and reconstructed figures

`initAndRegister` returns a future because registration can execute asynchronously on the selected event loop; the initial construction and `init` call execute in the calling thread. The listening channel uses `OP_ACCEPT`, while accepted socket channels use `OP_READ`. Automatic registration of accept/read interest depends on `autoRead`; the default example enables it.

Source baseline: Netty 4.1.53.Final (released October 13, 2020).

- [EchoServer.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/example/src/main/java/io/netty/example/echo/EchoServer.java)
- [AbstractBootstrap.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/bootstrap/AbstractBootstrap.java)
- [ServerBootstrap.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/bootstrap/ServerBootstrap.java)
- [NioServerSocketChannel.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/socket/nio/NioServerSocketChannel.java)
- [AbstractChannel.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/AbstractChannel.java)
- [AbstractNioChannel.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/nio/AbstractNioChannel.java)
