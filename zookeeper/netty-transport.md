---
layout: default
article: true
topic: ZooKeeper
lang: en
title: "How ZooKeeper Uses Netty for Client-Server Communication"
order: 310
series_order: 11
description: "Trace ZooKeeper client and server Netty channels, session negotiation, framing, and response delivery."
---

# How ZooKeeper Uses Netty for Client-Server Communication

> **Source version.** This English edition checks the original analysis against ZooKeeper 3.6.2, available in October 2020, pinned at commit `803c7f1a12f85978cb049af5e4ef23bd8b688715`. The annotated excerpts retain the original selection and executable logic; ellipses mark omissions and are not complete compilable methods. ZooKeeper 3.6.2 uses Netty **4.1.50.Final**, as declared in its [pinned POM](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/pom.xml); the independent [Netty series](../netty/index.html) uses 4.1.53.Final. 

## Introduction
The [ZooKeeper source reading series](index.html) has so far examined the network layer implemented with Java NIO. ZooKeeper also supports Netty. To use Netty as the client/server network transport, configure the client and server separately.
- Set this JVM startup property on the client:

```text

-Dzookeeper.clientCnxnSocket=org.apache.zookeeper.ClientCnxnSocketNetty

```

      
- Set this JVM startup property on the server:

```text

-Dzookeeper.serverCnxnFactory=org.apache.zookeeper.server.NettyServerCnxnFactory

```


## Netty in the ZooKeeper client
If you have read the earlier articles, this method may look familiar. It is called when the client creates its connection transport.

```java

 private ClientCnxnSocket getClientCnxnSocket() throws IOException {
        // Read the configured client transport implementation; here we select org.apache.zookeeper.ClientCnxnSocketNetty.
        String clientCnxnSocketName = getClientConfig().getProperty(ZKClientConfig.ZOOKEEPER_CLIENT_CNXN_SOCKET);
        if (clientCnxnSocketName == null) {
            clientCnxnSocketName = ClientCnxnSocketNIO.class.getName();
        }
        try {
           // Instantiate the connection transport through reflection.
            Constructor<?> clientCxnConstructor = Class.forName(clientCnxnSocketName)
                                                       .getDeclaredConstructor(ZKClientConfig.class);
            ClientCnxnSocket clientCxnSocket = (ClientCnxnSocket) clientCxnConstructor.newInstance(getClientConfig());
            return clientCxnSocket;
        } catch (Exception e) {
            throw new IOException("Couldn't instantiate " + clientCnxnSocketName, e);
        }
    }

```


##### ClientCnxnSocketNetty
`ClientCnxnSocketNetty` is ZooKeeper's Netty-based client connection transport, carrying the session protocol over a Netty channel.
Let us inspect its construction.

```java

 ClientCnxnSocketNetty(ZKClientConfig clientConfig) throws IOException {
        this.clientConfig = clientConfig;
        // Client only has 1 outgoing socket, so the event loop group only needs
        // a single thread.
        // Create an event loop group with one thread for the client's single outgoing socket.
        eventLoopGroup = NettyUtils.newNioOrEpollEventLoopGroup(1 /* nThreads */);

        initProperties();
    }

```

`ClientCnxn.SendThread.run` calls `startConnect` to establish the client's server socket connection. The transport-specific operation is `ClientCnxnSocket.connect`. In `ClientCnxnSocketNIO`, this creates a `SocketChannel` and connects it to the configured address, as the earlier article described. Now let us examine `ClientCnxnSocketNetty.connect`.
##### ClientCnxnSocketNetty.connect

```java

void connect(InetSocketAddress addr) throws IOException {
        
        firstConnect = new CountDownLatch(1);
        // Initialize the client Bootstrap and install ZKClientPipelineFactory as its channel initializer.
        // ZKClientPipelineFactory extends ChannelInitializer; we will examine initChannel below.
        Bootstrap bootstrap = new Bootstrap().group(eventLoopGroup)
                                             .channel(NettyUtils.nioOrEpollSocketChannel())
                                             .option(ChannelOption.SO_LINGER, -1)
                                             .option(ChannelOption.TCP_NODELAY, true)
                                             .handler(new ZKClientPipelineFactory(addr.getHostString(), addr.getPort()));
       // Configure the ByteBufAllocator.
        bootstrap = configureBootstrapAllocator(bootstrap);
        bootstrap.validate();
        // Lock the connection state; the completion callback uses this same lock.
        connectLock.lock();
        try {
            // Initiate the asynchronous server connection.
            connectFuture = bootstrap.connect(addr);
           // Add a listener for the connection result.
            connectFuture.addListener(new ChannelFutureListener() {
                @Override
                public void operationComplete(ChannelFuture channelFuture) throws Exception {
                    // this lock guarantees that channel won't be assigned after cleanup().
                    boolean connected = false;
                    connectLock.lock();
                    try {
                        
                        if (!channelFuture.isSuccess()) {
                            // If connection failed, return without assigning the channel.
                            LOG.warn("future isn't success.", channelFuture.cause());
                            return;
                        } else if (connectFuture == null) {
                            LOG.info("connect attempt cancelled");
                            // If the connect attempt was cancelled but succeeded
                            // anyway, make sure to close the channel, otherwise
                            // we may leak a file descriptor.
                            channelFuture.channel().close();
                            return;
                        }
                        // setup channel, variables, connection, etc.
                        // Obtain the channel of the established socket connection.
                        channel = channelFuture.channel();
                         // Set disconnected to false: the socket channel is connected.
                        disconnected.set(false);
                        // Set initialized to false: the ZooKeeper session handshake has not completed yet.
                        initialized = false;
                        // Reset lenBuffer and incomingBuffer to read the server's length-prefixed responses.
                        lenBuffer.clear();
                        incomingBuffer = lenBuffer;
                        // primeConnection queues the session connect request described in the NIO article; below we examine how it is transmitted.
                        sendThread.primeConnection();
                        updateNow();
                        updateLastSendAndHeard();

                        if (sendThread.tunnelAuthInProgress()) {
                            waitSasl.drainPermits();
                            needSasl.set(true);
                            sendPrimePacket();
                        } else {
                            needSasl.set(false);
                        }
                        connected = true;
                    } finally {
                        connectFuture = null;
                        // Release the connection-state lock.
                        connectLock.unlock();
                        if (connected) {
                            LOG.info("channel is connected: {}", channelFuture.channel());
                        }
                        // need to wake on connect success or failure to avoid
                        // timing out ClientCnxn.SendThread which may be
                        // blocked waiting for first connect in doTransport().
                        wakeupCnxn();
                        // Release firstConnect so the transport thread can continue after connection completion.
                        firstConnect.countDown();
                    }
                }
            });
        } finally {
            // Release the connection-state lock.
            connectLock.unlock();
        }
    }

```

`connect` configures Netty's client `Bootstrap`, initiates the TCP connection, and prepares the ZooKeeper session request when that connection succeeds. Since the operation is asynchronous, `SendThread.run` continues to `ClientCnxnSocketNetty.doTransport`. We previously inspected `ClientCnxnSocketNIO.doTransport`; now let us follow the Netty implementation.
##### ClientCnxnSocketNetty.doTransport

```java

void doTransport(
        int waitTimeOut,
        Queue<Packet> pendingQueue,
        ClientCnxn cnxn) throws IOException, InterruptedException {
        try {
           // Wait for the initial connection attempt to finish.
            if (!firstConnect.await(waitTimeOut, TimeUnit.MILLISECONDS)) {
                return;
            }
            Packet head = null;
            if (needSasl.get()) {
                if (!waitSasl.tryAcquire(waitTimeOut, TimeUnit.MILLISECONDS)) {
                    return;
                }
            } else {
               // Poll outgoingQueue for a request Packet.
                head = outgoingQueue.poll(waitTimeOut, TimeUnit.MILLISECONDS);
            }
            // check if being waken up on closing.
         
            if (!sendThread.getZkState().isAlive()) {
                // adding back the packet to notify of failure in conLossPacket().
               // If the client state is no longer alive, put the polled packet back at the head of outgoingQueue so connection-loss handling can notify its caller.
                addBack(head);
                return;
            }
            // channel disconnection happened
            if (disconnected.get()) {
                addBack(head);
                throw new EndOfStreamException("channel for sessionid 0x" + Long.toHexString(sessionId) + " is lost");
            }
            if (head != null) {
                // Write the request packets to the server.
                doWrite(pendingQueue, head, cnxn);
            }
        } finally {
            updateNow();
        }
    }

```


Unlike `ClientCnxnSocketNIO.doTransport`, this method directly handles the outgoing request path. Incoming data is handled asynchronously by Netty's channel handler.
##### ClientCnxnSocketNetty.doWrite

```java

 private void doWrite(Queue<Packet> pendingQueue, Packet p, ClientCnxn cnxn) {
        updateNow();
        boolean anyPacketsSent = false;
        while (true) {
            
            if (p != WakeupPacket.getInstance()) {
               // Skip the special wakeup packet.
                if ((p.requestHeader != null)
                    && (p.requestHeader.getType() != ZooDefs.OpCode.ping)
                    && (p.requestHeader.getType() != ZooDefs.OpCode.auth)) {
                   // Assign the request xid used to match responses and maintain the pending request sequence.
                    p.requestHeader.setXid(cnxn.getXid());
                    synchronized (pendingQueue) {
                        pendingQueue.add(p);
                    }
                }
               // Pass the packet to Netty's write path.
                sendPktOnly(p);
                anyPacketsSent = true;
            }
           // Continue writing while outgoingQueue has more packets.
            if (outgoingQueue.isEmpty()) {
               // When the outgoing queue is empty, leave the write loop.
                break;
            }
            p = outgoingQueue.remove();
        }
        // TODO: maybe we should flush in the loop above every N packets/bytes?
        // But, how do we determine the right value for N ...
        if (anyPacketsSent) {
          // If any packet was written, flush the channel to move queued writes toward the network.
            channel.flush();
        }
    }

```

`sendPktOnly` enters the Netty packet-write path and ultimately calls `ClientCnxnSocketNetty.sendPkt`.
##### ClientCnxnSocketNetty.sendPkt

```java

private ChannelFuture sendPkt(Packet p, boolean doFlush) {
        // Assuming the packet will be sent out successfully. Because if it fails,
        // the channel will close and clean up queues.
         // Serialize the packet into its ByteBuffer.
        p.createBB();
        updateLastSend();
        final ByteBuf writeBuffer = Unpooled.wrappedBuffer(p.bb);
        // Use channel.writeAndFlush or channel.write to enqueue the bytes for transmission.
        final ChannelFuture result = doFlush ? channel.writeAndFlush(writeBuffer) : channel.write(writeBuffer);
        result.addListener(onSendPktDoneListener);
        return result;
    }

```

We now know how the client sends requests through Netty. Next, how does it read the server's responses? Begin with `ZKClientPipelineFactory.initChannel`.
##### ZKClientPipelineFactory.initChannel

```java

 protected void initChannel(SocketChannel ch) throws Exception {
            ChannelPipeline pipeline = ch.pipeline();
            if (clientConfig.getBoolean(ZKClientConfig.SECURE_CLIENT)) {
                initSSL(pipeline);
            }
           // Register ZKClientHandler, an inbound handler, in the client pipeline.
           // This plaintext application path has no custom outbound encoder; sendPkt already supplies serialized bytes. SSL setup can also add an SslHandler in the complete initializer.

            pipeline.addLast("handler", new ZKClientHandler());
        }

```

Here is the definition of `ZKClientHandler`.
##### ZKClientHandler

```java

private class ZKClientHandler extends SimpleChannelInboundHandler<ByteBuf> {

        AtomicBoolean channelClosed = new AtomicBoolean(false);

        @Override
        public void channelInactive(ChannelHandlerContext ctx) throws Exception {
           // Handle a disconnected channel.
            LOG.info("channel is disconnected: {}", ctx.channel());
            cleanup();
        }

        /**
         * netty handler has encountered problems. We are cleaning it up and tell outside to close
         * the channel/connection.
         */
        private void cleanup() {
           // Mark the channel as closed.
            if (!channelClosed.compareAndSet(false, true)) {
                return;
            }
            disconnected.set(true);
            onClosing();
        }
 
         // channelRead0 receives response bytes from the server.
        @Override
        protected void channelRead0(ChannelHandlerContext ctx, ByteBuf buf) throws Exception {
            updateNow();
           // The frame-assembly logic resembles the NIO implementation.
            while (buf.isReadable()) {
                if (incomingBuffer.remaining() > buf.readableBytes()) {
                    int newLimit = incomingBuffer.position() + buf.readableBytes();
                    incomingBuffer.limit(newLimit);
                }
                // Copy response bytes into incomingBuffer.
                buf.readBytes(incomingBuffer);
                incomingBuffer.limit(incomingBuffer.capacity());

                if (!incomingBuffer.hasRemaining()) {
                    incomingBuffer.flip();
                    if (incomingBuffer == lenBuffer) {
                        // When incomingBuffer equals lenBuffer, these four bytes are the response frame length.
                        recvCount.getAndIncrement();
                        readLength();
                    } else if (!initialized) {
                        // If initialized is false, this frame is the response to the ZooKeeper session connect request.
                        // readConnectResult was explained in the NIO client startup article.
                        readConnectResult();
                        lenBuffer.clear();
                        incomingBuffer = lenBuffer;
                        initialized = true;
                        updateLastHeard();
                    } else {
                       // Otherwise incomingBuffer contains a normal request response.
                       // sendThread.readResponse was explained in the NIO request-processing article.
                        sendThread.readResponse(incomingBuffer);
                        lenBuffer.clear();
                        incomingBuffer = lenBuffer;
                        updateLastHeard();
                    }
                }
            }
   
            wakeupCnxn();
            // Note: SimpleChannelInboundHandler releases the ByteBuf for us
            // so we don't need to do it.
        }

        @Override
        public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) {
            LOG.error("Unexpected throwable", cause);
            cleanup();
        }

    }

```


This handler shows how ZooKeeper reads server responses through Netty: assemble the length-prefixed frame, then dispatch the session handshake response or a normal request response.

----

That completes the client side of ZooKeeper's Netty communication. Now let us examine Netty on the server.


## Netty in the ZooKeeper server
At startup, the server creates a `ServerCnxnFactory`. Its default implementation is `NIOServerCnxnFactory`; here we examine `NettyServerCnxnFactory` instead.

### Initialize NettyServerCnxnFactory

```java

 NettyServerCnxnFactory() {
        x509Util = new ClientX509Util();

        boolean usePortUnification = Boolean.getBoolean(PORT_UNIFICATION_KEY);
        LOG.info("{}={}", PORT_UNIFICATION_KEY, usePortUnification);
        if (usePortUnification) {
            try {
                QuorumPeerConfig.configureSSLAuth();
            } catch (QuorumPeerConfig.ConfigException e) {
                LOG.error("unable to set up SslAuthProvider, turning off client port unification", e);
                usePortUnification = false;
            }
        }
        this.shouldUsePortUnification = usePortUnification;

        this.advancedFlowControlEnabled = Boolean.getBoolean(NETTY_ADVANCED_FLOW_CONTROL);
        LOG.info("{} = {}", NETTY_ADVANCED_FLOW_CONTROL, this.advancedFlowControlEnabled);

        setOutstandingHandshakeLimit(Integer.getInteger(OUTSTANDING_HANDSHAKE_LIMIT, -1));
        // bossGroup accepts client connections; workerGroup handles I/O on established channels: the usual Netty reactor arrangement.
        EventLoopGroup bossGroup = NettyUtils.newNioOrEpollEventLoopGroup(NettyUtils.getClientReachableLocalInetAddressCount());
        EventLoopGroup workerGroup = NettyUtils.newNioOrEpollEventLoopGroup();
       // Create ServerBootstrap and configure the server's channel handlers.
        ServerBootstrap bootstrap = new ServerBootstrap().group(bossGroup, workerGroup)
                                                         .channel(NettyUtils.nioOrEpollServerSocketChannel())
                                                         // parent channel options
                                                         .option(ChannelOption.SO_REUSEADDR, true)
                                                         // child channels options
                                                         .childOption(ChannelOption.TCP_NODELAY, true)
                                                         .childOption(ChannelOption.SO_LINGER, -1)
                                                         .childHandler(new ChannelInitializer<SocketChannel>() {
                                                             @Override
                                                             protected void initChannel(SocketChannel ch) throws Exception {
                                                                 ChannelPipeline pipeline = ch.pipeline();
                                                                 if (advancedFlowControlEnabled) {
                                                                     pipeline.addLast(readIssuedTrackingHandler);
                                                                 }
                                                                 if (secure) {
                                                                     initSSL(pipeline, false);
                                                                 } else if (shouldUsePortUnification) {
                                                                     initSSL(pipeline, true);
                                                                 }
                                                                 pipeline.addLast("servercnxnfactory", channelHandler);
                                                             }
                                                         });
        this.bootstrap = configureBootstrapAllocator(bootstrap);
        this.bootstrap.validate();
    }

```

For the plaintext application path, this `ServerBootstrap` installs one ZooKeeper business handler, `CnxnChannelHandler`, which extends `ChannelDuplexHandler`. The complete initializer can also install transport/security handlers, including SSL. Let us analyze its implementation.
### CnxnChannelHandler

```java

class CnxnChannelHandler extends ChannelDuplexHandler {

        // channelActive runs after the server accepts and activates a client's socket channel.
       // Normally it creates the server-side ZooKeeper connection object for this channel; session negotiation follows later.
        @Override
        public void channelActive(ChannelHandlerContext ctx) throws Exception {
            if (LOG.isTraceEnabled()) {
                LOG.trace("Channel active {}", ctx.channel());
            }

            final Channel channel = ctx.channel();
            // If the total connection limit has been reached, close the socket and reject this new connection.
            if (limitTotalNumberOfCnxns()) {
                ServerMetrics.getMetrics().CONNECTION_REJECTED.add(1);
                channel.close();
                return;
            }
            InetAddress addr = ((InetSocketAddress) channel.remoteAddress()).getAddress();
            // If the per-client-IP connection limit has been reached, reject the new connection.
            if (maxClientCnxns > 0 && getClientCnxnCount(addr) >= maxClientCnxns) {
                ServerMetrics.getMetrics().CONNECTION_REJECTED.add(1);
                LOG.warn("Too many connections from {} - max is {}", addr, maxClientCnxns);
                channel.close();
                return;
            }
            // Create NettyServerCnxn, the ZooKeeper server-side connection object.
            NettyServerCnxn cnxn = new NettyServerCnxn(channel, zkServer, NettyServerCnxnFactory.this);
           // Store the connection object as a channel attribute.
            ctx.channel().attr(CONNECTION_ATTRIBUTE).set(cnxn);

            if (handshakeThrottlingEnabled) {
                // Favor to check and throttling even in dual mode which
                // accepts both secure and insecure connections, since
                // it's more efficient than throttling when we know it's
                // a secure connection in DualModeSslHandler.
                //
                // From benchmark, this reduced around 15% reconnect time.
                int outstandingHandshakesNum = outstandingHandshake.addAndGet(1);
                if (outstandingHandshakesNum > outstandingHandshakeLimit) {
                    outstandingHandshake.addAndGet(-1);
                    channel.close();
                    ServerMetrics.getMetrics().TLS_HANDSHAKE_EXCEEDED.add(1);
                } else {
                    cnxn.setHandshakeState(HandshakeState.STARTED);
                }
            }

            if (secure) {
                SslHandler sslHandler = ctx.pipeline().get(SslHandler.class);
                Future<Channel> handshakeFuture = sslHandler.handshakeFuture();
                handshakeFuture.addListener(new CertificateVerifier(sslHandler, cnxn));
            } else if (!shouldUsePortUnification) {
                allChannels.add(ctx.channel());
                addCnxn(cnxn);
            }
        }

         // Handle channel shutdown.
        @Override
        public void channelInactive(ChannelHandlerContext ctx) throws Exception {
            if (LOG.isTraceEnabled()) {
                LOG.trace("Channel inactive {}", ctx.channel());
            }

            allChannels.remove(ctx.channel());
            NettyServerCnxn cnxn = ctx.channel().attr(CONNECTION_ATTRIBUTE).getAndSet(null);
            if (cnxn != null) {
                if (LOG.isTraceEnabled()) {
                    LOG.trace("Channel inactive caused close {}", cnxn);
                }
                updateHandshakeCountIfStarted(cnxn);
               // Close the ZooKeeper connection.
                cnxn.close(ServerCnxn.DisconnectReason.CHANNEL_DISCONNECTED);
            }
        }

        // Handle channel exceptions.
        @Override
        public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) throws Exception {
            LOG.warn("Exception caught", cause);
            NettyServerCnxn cnxn = ctx.channel().attr(CONNECTION_ATTRIBUTE).getAndSet(null);
            if (cnxn != null) {
                LOG.debug("Closing {}", cnxn);
                updateHandshakeCountIfStarted(cnxn);
                cnxn.close(ServerCnxn.DisconnectReason.CHANNEL_CLOSED_EXCEPTION);
            }
        }
         // Handle custom channel events that disable or resume reading.
        @Override
        public void userEventTriggered(ChannelHandlerContext ctx, Object evt) throws Exception {
            try {
                if (evt == NettyServerCnxn.ReadEvent.ENABLE) {
                    LOG.debug("Received ReadEvent.ENABLE");
                    NettyServerCnxn cnxn = ctx.channel().attr(CONNECTION_ATTRIBUTE).get();
                    // TODO: Not sure if cnxn can be null here. It becomes null if channelInactive()
                    // or exceptionCaught() trigger, but it's unclear to me if userEventTriggered() can run
                    // after either of those. Check for null just to be safe ...
                    if (cnxn != null) {
                        if (cnxn.getQueuedReadableBytes() > 0) {
                            cnxn.processQueuedBuffer();
                            if (advancedFlowControlEnabled && cnxn.getQueuedReadableBytes() == 0) {
                                // trigger a read if we have consumed all
                                // backlog
                                ctx.read();
                                LOG.debug("Issued a read after queuedBuffer drained");
                            }
                        }
                    }
                    if (!advancedFlowControlEnabled) {
                        ctx.channel().config().setAutoRead(true);
                    }
                } else if (evt == NettyServerCnxn.ReadEvent.DISABLE) {
                    LOG.debug("Received ReadEvent.DISABLE");
                    ctx.channel().config().setAutoRead(false);
                }
            } finally {
                ReferenceCountUtil.release(evt);
            }
        }

         // Read request bytes sent by the client.
        @Override
        public void channelRead(ChannelHandlerContext ctx, Object msg) throws Exception {
            try {
                if (LOG.isTraceEnabled()) {
                    LOG.trace("message received called {}", msg);
                }
                try {
                    LOG.debug("New message {} from {}", msg, ctx.channel());
                    // Retrieve NettyServerCnxn from the channel attribute assigned in channelActive.
                    NettyServerCnxn cnxn = ctx.channel().attr(CONNECTION_ATTRIBUTE).get();
                    if (cnxn == null) {
                        LOG.error("channelRead() on a closed or closing NettyServerCnxn");
                    } else {
                        // Pass the incoming ByteBuf to NettyServerCnxn for request framing and dispatch.
                        cnxn.processMessage((ByteBuf) msg);
                    }
                } catch (Exception ex) {
                    LOG.error("Unexpected exception in receive", ex);
                    throw ex;
                }
            } finally {
                ReferenceCountUtil.release(msg);
            }
        }

        @Override
        public void channelReadComplete(ChannelHandlerContext ctx) throws Exception {
            if (advancedFlowControlEnabled) {
                NettyServerCnxn cnxn = ctx.channel().attr(CONNECTION_ATTRIBUTE).get();
                if (cnxn != null && cnxn.getQueuedReadableBytes() == 0 && cnxn.readIssuedAfterReadComplete == 0) {
                    ctx.read();
                    LOG.debug("Issued a read since we do not have anything to consume after channelReadComplete");
                }
            }

            ctx.fireChannelReadComplete();
        }

        // Use a single listener instance to reduce GC
        // Note: this listener is only added when LOG.isTraceEnabled() is true,
        // so it should not do any work other than trace logging.
        private final GenericFutureListener<Future<Void>> onWriteCompletedTracer = (f) -> {
            if (LOG.isTraceEnabled()) {
                LOG.trace("write success: {}", f.isSuccess());
            }
        };

     
        @Override
        public void write(ChannelHandlerContext ctx, Object msg, ChannelPromise promise) throws Exception {
            if (LOG.isTraceEnabled()) {
                promise.addListener(onWriteCompletedTracer);
            }
            super.write(ctx, msg, promise);
        }

    }

```


Now let us inspect how `NettyServerCnxn.processMessage` handles the incoming bytes.
##### NettyServerCnxn.processMessage

```java

void processMessage(ByteBuf buf) {
        checkIsInEventLoop("processMessage");
        LOG.debug("0x{} queuedBuffer: {}", Long.toHexString(sessionId), queuedBuffer);

        if (LOG.isTraceEnabled()) {
            LOG.trace("0x{} buf {}", Long.toHexString(sessionId), ByteBufUtil.hexDump(buf));
        }

        if (throttled.get()) {
            LOG.debug("Received message while throttled");
            // we are throttled, so we need to queue
            if (queuedBuffer == null) {
                LOG.debug("allocating queue");
                queuedBuffer = channel.alloc().compositeBuffer();
            }
            appendToQueuedBuffer(buf.retainedDuplicate());
            if (LOG.isTraceEnabled()) {
                LOG.trace("0x{} queuedBuffer {}", Long.toHexString(sessionId), ByteBufUtil.hexDump(queuedBuffer));
            }
        } else {
            LOG.debug("not throttled");
            if (queuedBuffer != null) {
                appendToQueuedBuffer(buf.retainedDuplicate());
                processQueuedBuffer();
            } else {
               // After handling any queued or throttled bytes, call receiveMessage to consume request frames.
                receiveMessage(buf);
                // Have to check !closingChannel, because an error in
                // receiveMessage() could have led to close() being called.
                if (!closingChannel && buf.isReadable()) {
                    if (LOG.isTraceEnabled()) {
                        LOG.trace("Before copy {}", buf);
                    }

                    if (queuedBuffer == null) {
                        queuedBuffer = channel.alloc().compositeBuffer();
                    }
                    appendToQueuedBuffer(buf.retainedSlice(buf.readerIndex(), buf.readableBytes()));
                    if (LOG.isTraceEnabled()) {
                        LOG.trace("Copy is {}", queuedBuffer);
                        LOG.trace("0x{} queuedBuffer {}", Long.toHexString(sessionId), ByteBufUtil.hexDump(queuedBuffer));
                    }
                }
            }
        }
    }

```

##### NettyServerCnxn.receiveMessage
`NettyServerCnxn.receiveMessage` is the core of the server's client-request read path.

```java

 private void receiveMessage(ByteBuf message) {
        checkIsInEventLoop("receiveMessage");
        try {
            while (message.isReadable() && !throttled.get()) {
                if (bb != null) {
                    if (LOG.isTraceEnabled()) {
                        LOG.trace("message readable {} bb len {} {}", message.readableBytes(), bb.remaining(), bb);
                        ByteBuffer dat = bb.duplicate();
                        dat.flip();
                        LOG.trace("0x{} bb {}", Long.toHexString(sessionId), ByteBufUtil.hexDump(Unpooled.wrappedBuffer(dat)));
                    }

                    if (bb.remaining() > message.readableBytes()) {
                        int newLimit = bb.position() + message.readableBytes();
                        bb.limit(newLimit);
                    }
                    // Fill bb with the serialized client request bytes.
                    message.readBytes(bb);
                    bb.limit(bb.capacity());

                    if (LOG.isTraceEnabled()) {
                        LOG.trace("after readBytes message readable {} bb len {} {}", message.readableBytes(), bb.remaining(), bb);
                        ByteBuffer dat = bb.duplicate();
                        dat.flip();
                        LOG.trace("after readbytes 0x{} bb {}",
                                  Long.toHexString(sessionId),
                                  ByteBufUtil.hexDump(Unpooled.wrappedBuffer(dat)));
                    }
                    if (bb.remaining() == 0) {
                        bb.flip();
                        packetReceived(4 + bb.remaining());

                        ZooKeeperServer zks = this.zkServer;
                        if (zks == null || !zks.isRunning()) {
                            throw new IOException("ZK down");
                        }
                        if (initialized) {
                             // Once the session is initialized, dispatch the complete frame through zks.processPacket, as in the NIO request-processing analysis.
                            // TODO: if zks.processPacket() is changed to take a ByteBuffer[],
                            // we could implement zero-copy queueing.
                            zks.processPacket(this, bb);
                        } else {
                            LOG.debug("got conn req request from {}", getRemoteSocketAddress());
                            // Before session initialization, the frame is a session connect request; dispatch it through zks.processConnectRequest.
                          // The earlier client startup article explains zks.processConnectRequest.
                            zks.processConnectRequest(this, bb);
                            initialized = true;
                        }
                        bb = null;
                    }
                } else {
                   // If bb has not been allocated yet, first read the four-byte request-length prefix from ByteBuf.
                    if (LOG.isTraceEnabled()) {
                        LOG.trace("message readable {} bblenrem {}", message.readableBytes(), bbLen.remaining());
                        ByteBuffer dat = bbLen.duplicate();
                        dat.flip();
                        LOG.trace("0x{} bbLen {}", Long.toHexString(sessionId), ByteBufUtil.hexDump(Unpooled.wrappedBuffer(dat)));
                    }

                    if (message.readableBytes() < bbLen.remaining()) {
                        bbLen.limit(bbLen.position() + message.readableBytes());
                    }
                   // Read the four-byte frame-length prefix from message.
                    message.readBytes(bbLen);
                    bbLen.limit(bbLen.capacity());
                    if (bbLen.remaining() == 0) {
                        bbLen.flip();

                        if (LOG.isTraceEnabled()) {
                            LOG.trace("0x{} bbLen {}", Long.toHexString(sessionId), ByteBufUtil.hexDump(Unpooled.wrappedBuffer(bbLen)));
                        }
                        // Decode the client's request length.
                        int len = bbLen.getInt();
                        if (LOG.isTraceEnabled()) {
                            LOG.trace("0x{} bbLen len is {}", Long.toHexString(sessionId), len);
                        }

                        bbLen.clear();
                        if (!initialized) {
                            if (checkFourLetterWord(channel, message, len)) {
                                return;
                            }
                        }
                        if (len < 0 || len > BinaryInputArchive.maxBuffer) {
                            throw new IOException("Len error " + len);
                        }
                        // checkRequestSize will throw IOException if request is rejected
                        zkServer.checkRequestSizeWhenReceivingMessage(len);
                       // Allocate a ByteBuffer of length len to receive the complete client request frame.
                        bb = ByteBuffer.allocate(len);
                    }
                }
            }
        } catch (IOException e) {
            LOG.warn("Closing connection to {}", getRemoteSocketAddress(), e);
            close(DisconnectReason.IO_EXCEPTION);
        } catch (ClientCnxnLimitException e) {
            // Common case exception, print at debug level
            ServerMetrics.getMetrics().CONNECTION_REJECTED.add(1);

            LOG.debug("Closing connection to {}", getRemoteSocketAddress(), e);
            close(DisconnectReason.CLIENT_RATE_LIMIT);
        }
    }

```

`receiveMessage` shows how ZooKeeper reads Netty's byte stream into complete client request messages.
After a request passes through ZooKeeper's server processor chain, how is its result returned to the client?
`FinalRequestProcessor` constructs the response, then `NettyServerCnxn.sendResponse` sends it.
##### NettyServerCnxn.sendBuffer
`sendResponse` calls `sendBuffer`, which calls `channel.writeAndFlush` to send the serialized response to the client.

```java

public void sendBuffer(ByteBuffer... buffers) {
        if (buffers.length == 1 && buffers[0] == ServerCnxnFactory.closeConn) {
            close(DisconnectReason.CLIENT_CLOSED_CONNECTION);
            return;
        }
        channel.writeAndFlush(Unpooled.wrappedBuffer(buffers)).addListener(onSendBufferDoneListener);
    }

```

This completes the server-side Netty I/O path: accept a channel, create its ZooKeeper connection, assemble request frames, dispatch requests, and write the serialized responses.

**Excerpt correction:** the original `sendPkt` excerpt omitted the semicolon after `Unpooled.wrappedBuffer(p.bb)`; it is restored from the pinned 3.6.2 source. All other executable excerpt lines are retained. These excerpts illustrate the application pipeline; the complete source also configures security handlers where SSL is enabled.

## Pinned source references

- [`ZooKeeper`](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/ZooKeeper.java): selection and reflective construction of the configured `ClientCnxnSocket`.
- [`ClientCnxnSocketNetty`](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/ClientCnxnSocketNetty.java): asynchronous connection, packet writes, pipeline initialization, and response framing.
- [`NettyServerCnxnFactory`](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/NettyServerCnxnFactory.java): server bootstrap, connection admission, and channel events.
- [`NettyServerCnxn`](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/NettyServerCnxn.java): request-frame assembly, dispatch, and serialized response writes.
