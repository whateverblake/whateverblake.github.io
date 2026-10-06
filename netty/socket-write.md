---
layout: default
article: true
topic: Netty
lang: en
title: "How NioSocketChannel Writes and Flushes Data"
description: "Follow queued outbound buffers, gathering writes, flush promises, and socket backpressure."
order: 450
series_order: 5
---

# How NioSocketChannel Writes and Flushes Data


## Introduction
This article follows how one endpoint in a Netty connection writes bytes to the network.
## Scope
The analysis uses the NIO transport.

## Writing bytes to the network
Assume a custom handler writes `hello world` to its peer from `channelActive`, using its context:

```

public class ClientHandler extends SimpleChannelInboundHandler<ByteBuf> {
    @Override
    public void channelActive(ChannelHandlerContext ctx) throws Exception {
        // Copy the string into a ByteBuf.
        ctx.writeAndFlush(Unpooled.copiedBuffer("hello world".getBytes()));
    }
}

```

Follow the `ctx.writeAndFlush` call chain.
writeAndFlush(msg) --> writeAndFlush(msg,promise) --> write(msg,flush,promise)
The methods in this chain belong to `ChannelHandlerContext`; here is the internal `write` method:

```

// In this example, flush is true.
private void write(Object msg, boolean flush, ChannelPromise promise) {
        ObjectUtil.checkNotNull(msg, "msg");
        try {
            if (isNotValidPromise(promise, true)) {
                ReferenceCountUtil.release(msg);
                // cancelled
                return;
            }
        } catch (RuntimeException e) {
            ReferenceCountUtil.release(msg);
            throw e;
        }
        // Search backward toward the head for an outbound context matching the write/flush mask.
        // Invoke writeAndFlush on that context.
        // That delegates to the associated outbound handler's callbacks.
       // The final transport context is HeadContext.

        final AbstractChannelHandlerContext next = findContextOutbound(flush ?
                (MASK_WRITE | MASK_FLUSH) : MASK_WRITE);
        final Object m = pipeline.touch(msg, next);
        EventExecutor executor = next.executor();
        if (executor.inEventLoop()) {
            if (flush) {
                next.invokeWriteAndFlush(m, promise);
            } else {
                next.invokeWrite(m, promise);
            }
        } else {
         // If the caller is outside the selected executor, submit the write as a task.
            final WriteTask task = WriteTask.newInstance(next, m, promise, flush);
            if (!safeExecute(executor, task, promise, m, !flush)) {
                // We failed to submit the WriteTask. We need to cancel it so we decrement the pending bytes
                // and put it back in the Recycler for re-use later.
                //
                // See https://github.com/netty/netty/issues/8343.
                task.cancel();
            }
        }
    }

```

For pipeline propagation, see [Netty's Event Pipeline](pipeline.html).
For executor and thread affinity, see [Netty's Thread Model](thread-model.html).
Here is `AbstractChannelHandlerContext.invokeWriteAndFlush`:

```

void invokeWriteAndFlush(Object msg, ChannelPromise promise) {
        if (invokeHandler()) {
           // Invoke the context's associated handler.write callback.
            invokeWrite0(msg, promise);
            // Invoke its handler.flush callback.
            invokeFlush0();
        } else {
            writeAndFlush(msg, promise);
        }
    }

```

`HeadContext` also implements the handler interfaces and reaches the underlying transport. Examine its `write` and `flush` callbacks.

```

 @Override
        public void write(ChannelHandlerContext ctx, Object msg, ChannelPromise promise) {
            unsafe.write(msg, promise);
        }

        @Override
        public void flush(ChannelHandlerContext ctx) {
            unsafe.flush();
        }

```

These delegate to `unsafe`. Start with `unsafe.write`:
### unsafe.write

```

 @Override
        public final void write(Object msg, ChannelPromise promise) {
            assertEventLoop();
            // Pending outbound data is retained in outboundBuffer before transport writes.
           // Flushing consumes eligible entries from this outbound queue.
            ChannelOutboundBuffer outboundBuffer = this.outboundBuffer;
            if (outboundBuffer == null) {
                // If the outboundBuffer is null we know the channel was closed and so
                // need to fail the future right away. If it is not null the handling of the rest
                // will be done in flush0()
                // See https://github.com/netty/netty/issues/2362
                safeSetFailure(promise, newClosedChannelException(initialCloseCause));
                // release message now to prevent resource-leak
                ReferenceCountUtil.release(msg);
                return;
            }

            int size;
            try {
                // Accept ByteBuf and FileRegion messages; reject unsupported message types.
              // Convert a heap ByteBuf to a direct buffer when needed for this transport.
              // See the pooled-memory article for allocation details.

                msg = filterOutboundMessage(msg);
               // Estimate this message's byte size.
                size = pipeline.estimatorHandle().size(msg);
                if (size < 0) {
                    size = 0;
                }
            } catch (Throwable t) {
                safeSetFailure(promise, t);
                ReferenceCountUtil.release(msg);
                return;
            }
            // Append the message to outboundBuffer.
            outboundBuffer.addMessage(msg, size, promise);
        }

```

`ChannelOutboundBuffer` queues messages before transport writes. Before examining `addMessage`, look at its important fields.

```

public final class ChannelOutboundBuffer {
    // Assuming a 64-bit JVM:
    //  - 16 bytes object header
    //  - 6 reference fields
    //  - 2 long fields
    //  - 2 int fields
    //  - 1 boolean field
    //  - padding
   // Estimated per-entry overhead; JOL can help inspect object layout.
    static final int
CHANNEL_OUTBOUND_BUFFER_ENTRY_OVERHEAD =
            SystemPropertyUtil.getInt("io.netty.transport.outboundBufferEntrySizeOverhead", 96);

    private static final InternalLogger logger = InternalLoggerFactory.getInstance(ChannelOutboundBuffer.class);

    private static final FastThreadLocal<ByteBuffer[]> NIO_BUFFERS = new FastThreadLocal<ByteBuffer[]>() {
        @Override
        protected ByteBuffer[] initialValue() throws Exception {
            return new ByteBuffer[1024];
        }
    };
    // The channel that owns this outbound buffer.
    private final Channel channel;

    // Entry(flushedEntry) --> ... Entry(unflushedEntry) --> ... Entry(tailEntry)
    //
    // The Entry that is the first in the linked-list structure that was flushed
    // The first flushed entry eligible for writing.
    private Entry flushedEntry;
    // The Entry which is the first unflushed in the linked-list structure
  // Newly appended messages start in the unflushed part of the linked list.
    private Entry unflushedEntry;
    // The Entry which represents the tail of the buffer
   // The last entry appended to the queue.
    private Entry tailEntry;
    // The number of flushed entries that are not written yet
    private int flushed;

    private int nioBufferCount;
    private long nioBufferSize;

    private boolean inFail;

    // Total pending outbound bytes, including entry overhead.
    @SuppressWarnings("UnusedDeclaration")
    private volatile long totalPendingSize;

    // Bit mask recording unwritable conditions.
    @SuppressWarnings("UnusedDeclaration")
    private volatile int unwritable;

```

Now examine `ChannelOutboundBuffer.addMessage`:
### addMessage

```

public void addMessage(Object msg, int size, ChannelPromise promise) {
       // Wrap the message in a recyclable Entry node.
       // See the Recycler article for Netty's object reuse mechanism.

        Entry entry = Entry.newInstance(msg, size, total(msg), promise);
        if (tailEntry == null) {
            flushedEntry = null;
        } else {
           // Append after the existing tail entry.
            Entry tail = tailEntry;
            tail.next = entry;
        }
        // Move tailEntry to the newly appended entry.
        tailEntry = entry;

        if (unflushedEntry == null) {
           // If this is the first unflushed message, initialize unflushedEntry.
            unflushedEntry = entry;
        }

        // increment pending bytes after adding message to the unflushed arrays.
        // See https://github.com/netty/netty/issues/1619
      // Update total pending outbound bytes.
        incrementPendingOutboundBytes(entry.pendingSize, false);
    }

```

`unsafe.write` appends application messages to this linked outbound queue. Netty configures high and low watermarks. When pending bytes exceed the high watermark, the buffer becomes unwritable and fires `channelWritabilityChanged`. `incrementPendingOutboundBytes` implements that transition. These watermarks signal backpressure; they do not prevent application code from appending more messages.

Next, follow how queued data is flushed to the transport.
### unsafe.flush

```

 @Override
        public final void flush() {
            assertEventLoop();

            ChannelOutboundBuffer outboundBuffer = this.outboundBuffer;
            if (outboundBuffer == null) {
                return;
            }
           // Mark entries beginning at unflushedEntry as flushed and eligible for writing.
            outboundBuffer.addFlush();
            // Write eligible queued data to the transport.
            flush0();
        }

```

First examine `outboundBuffer.addFlush`:
### outboundBuffer.addFlush()

```

 public void addFlush() {
        // There is no need to process all entries if there was already a flush before and no new messages
        // where added in the meantime.
        //
        // See https://github.com/netty/netty/issues/2577
        Entry entry = unflushedEntry;
        if (entry != null) {
            if (flushedEntry == null) {
                // there is no flushedEntry yet, so start with the entry
                flushedEntry = entry;
            }
            do {
                // Count the messages now eligible for writing.
                flushed ++;
                if (!entry.promise.setUncancellable()) {
                    // Was cancelled so make sure we free up memory and notify about the freed bytes
                    int pending = entry.cancel();
                    decrementPendingOutboundBytes(pending, false, true);
                }
                entry = entry.next;
            } while (entry != null);

            // All flushed so reset unflushedEntry
           // Clear unflushedEntry because all currently queued messages have been flushed.
            unflushedEntry = null;
        }
    }

```


### flush0
`flush0` enters the transport-write path:

```

protected void flush0() {
         // Avoid reentrant flushing while inFlush0 is already true.
            if (inFlush0) {
                // Avoid re-entrance
                return;
            }

            final ChannelOutboundBuffer outboundBuffer = this.outboundBuffer;
            if (outboundBuffer == null || outboundBuffer.isEmpty()) {
                return;
            }
           // Mark a flush as in progress.
            inFlush0 = true;

            // Mark all pending write requests as failure if the channel is inactive.
          // Fail the flush if the underlying channel is not active.
            if (!isActive()) {
                try {
                    if (isOpen()) {
                        outboundBuffer.failFlushed(new NotYetConnectedException(), true);
                    } else {
                        // Do not trigger channelWritabilityChanged because the channel is closed already.
                        outboundBuffer.failFlushed(newClosedChannelException(initialCloseCause), false);
                    }
                } finally {
                    inFlush0 = false;
                }
                return;
            }

            try {
              // Perform the actual transport write.
                doWrite(outboundBuffer);
            } catch (Throwable t) {
                if (t instanceof IOException && config().isAutoClose()) {
                    /**
                     * Just call {@link #close(ChannelPromise, Throwable, boolean)} here which will take care of
                     * failing all flushed messages and also ensure the actual close of the underlying transport
                     * will happen before the promises are notified.
                     *
                     * This is needed as otherwise {@link #isActive()} , {@link #isOpen()} and {@link #isWritable()}
                     * may still return {@code true} even if the channel should be closed as result of the exception.
                     */
                    initialCloseCause = t;
                    close(voidPromise(), t, newClosedChannelException(t), false);
                } else {
                    try {
                        shutdownOutput(voidPromise(), t);
                    } catch (Throwable t2) {
                        initialCloseCause = t;
                        close(voidPromise(), t2, newClosedChannelException(t), false);
                    }
                }
            } finally {
                inFlush0 = false;
            }
        }

```

Here is `doWrite`:
### doWrite

```

protected void doWrite(ChannelOutboundBuffer in) throws Exception {
        // Obtain the underlying Java SocketChannel.
        SocketChannel ch = javaChannel();
        // Set the maximum write-spin budget for this invocation.
        int writeSpinCount = config().getWriteSpinCount();
        do {
            if (in.isEmpty()) {
                // All written so clear OP_WRITE
               // With no queued data left, clear OP_WRITE interest.
                clearOpWrite();
                // Directly return here so incompleteWrite(...) is not called.
                return;
            }

            // Ensure the pending writes are made of ByteBufs only.
            // Determine the current gathering-write byte limit.
            int maxBytesPerGatheringWrite = ((NioSocketChannelConfig) config).getMaxBytesPerGatheringWrite();
            // Expose the queued data as a ByteBuffer array; examined below.
            ByteBuffer[] nioBuffers = in.nioBuffers(1024, maxBytesPerGatheringWrite);
            // Count the buffers selected for this write.
            int nioBufferCnt = in.nioBufferCount();

            // Always us nioBuffers() to workaround data-corruption.
            // See https://github.com/netty/netty/issues/2761
            switch (nioBufferCnt) {
               // No ByteBuffer is available in this batch.
                case 0:
                    // We have something else beside ByteBuffers to write so fallback to normal writes.
                    // For example, the current message may be a FileRegion.
                    writeSpinCount -= doWrite0(in);
                    break;
                // Only one ByteBuffer needs writing.
                case 1: {
                    // Only one ByteBuf so use non-gathering write
                    // Zero length buffers are not added to nioBuffers by ChannelOutboundBuffer, so there is no need
                    // to check if the total size of all the buffers is non-zero.
                   // Obtain that pending buffer.
                    ByteBuffer buffer = nioBuffers[0];
                   // Count the bytes we will attempt to write.
                    int attemptedBytes = buffer.remaining();
                    // Write through the Java channel and record the actual byte count.
                    final int localWrittenBytes = ch.write(buffer);
                    if (localWrittenBytes <= 0) {
                       // A zero-byte nonblocking write indicates that writing cannot currently progress.
                       // Register OP_WRITE so a later readiness event can resume flushing.
                        incompleteWrite(true);
                        return;
                    }
                  // Adapt maxBytesPerGatheringWrite using attempted and actual bytes.
                    adjustMaxBytesPerGatheringWrite(attemptedBytes, localWrittenBytes, maxBytesPerGatheringWrite);
                    // Update the outbound queue from the actual bytes written.
                   // Fully consumed entries are removed.
                   // A partial write leaves bytes from the current message pending.
                 // Advance its ByteBuf reader index so the next write resumes at the remaining bytes.
                    in.removeBytes(localWrittenBytes);
                    --writeSpinCount;
                    break;
                }
         // Multiple ByteBuffers can be written in a gathering write.
                default: {
                    // Zero length buffers are not added to nioBuffers by ChannelOutboundBuffer, so there is no need
                    // to check if the total size of all the buffers is non-zero.
                    // We limit the max amount to int above so cast is safe
                    // Obtain the total bytes represented by this batch.
                    long attemptedBytes = in.nioBufferSize();
                   // Write the buffer array through SocketChannel and record the result.
                    final long localWrittenBytes = ch.write(nioBuffers, 0, nioBufferCnt);
                    if (localWrittenBytes <= 0) {
                         // As above, zero progress requires OP_WRITE readiness.
                        incompleteWrite(true);
                        return;
                    }
                    // Casting to int is safe because we limit the total amount of data in the nioBuffers to int above.
            // Adapt the gathering-write byte limit as in the single-buffer case.
                    adjustMaxBytesPerGatheringWrite((int) attemptedBytes, (int) localWrittenBytes,
                            maxBytesPerGatheringWrite);
                  // Consume the bytes actually written from the outbound queue.
                    in.removeBytes(localWrittenBytes);
                  // Spend one write-spin iteration.
                    --writeSpinCount;
                    break;
                }
            }
        } while (writeSpinCount > 0);
        // A negative spin budget denotes no-progress handling; an exhausted budget with progress schedules another flush task.
        incompleteWrite(writeSpinCount < 0);
    }

```

`ChannelOutboundBuffer.nioBuffers` exposes eligible queued messages as NIO buffers so `SocketChannel` can write them directly.
### nioBuffers

```

  // maxCount bounds the number of ByteBuffers included in this batch.
  // maxBytes bounds the batch's target byte size, while permitting at least one buffer to make progress.
 public ByteBuffer[] nioBuffers(int maxCount, long maxBytes) {
        assert maxCount > 0;
        assert maxBytes > 0;
        long nioBufferSize = 0;
        int nioBufferCount = 0;
        final InternalThreadLocalMap threadLocalMap = InternalThreadLocalMap.get();
        // NIO_BUFFERS initially supplies a thread-local array with 1024 slots.
        ByteBuffer[] nioBuffers = NIO_BUFFERS.get(threadLocalMap);
        Entry entry = flushedEntry;
        // Traverse only flushed entries eligible for this write.
        while (isFlushedEntry(entry) && entry.msg instanceof ByteBuf) {
            if (!entry.cancelled) {
                ByteBuf buf = (ByteBuf) entry.msg;
                final int readerIndex = buf.readerIndex();
                // Count this entry's readable bytes.
                final int readableBytes = buf.writerIndex() - readerIndex;

                if (readableBytes > 0) {
                    // If at least one buffer is included already, stop before adding an entry that exceeds the byte limit.
                    if (maxBytes - readableBytes < nioBufferSize && nioBufferCount != 0) {
                        // If the nioBufferSize + readableBytes will overflow maxBytes, and there is at least one entry
                        // we stop populate the ByteBuffer array. This is done for 2 reasons:
                        // 1. bsd/osx don't allow to write more bytes then Integer.MAX_VALUE with one writev(...) call
                        // and so will return 'EINVAL', which will raise an IOException. On Linux it may work depending
                        // on the architecture and kernel but to be safe we also enforce the limit here.
                        // 2. There is no sense in putting more data in the array than is likely to be accepted by the
                        // OS.
                        //
                        // See also:
                        // - https://www.freebsd.org/cgi/man.cgi?query=write&sektion=2
                        // - http://linux.die.net/man/2/writev
                        break;
                    }
                  // Increase the accumulated byte count.
                    nioBufferSize += readableBytes;
                    int count = entry.count;
                    if (count == -1) {
                        //noinspection ConstantValueVariableUse
                       // nioBufferCount reports how many NIO buffers represent this ByteBuf.
                        entry.count = count = buf.nioBufferCount();
                    }
                   // Count the buffers already accumulated and expand the array if required.
                   // The initial array is often sufficient in this call path, but expansion remains necessary for larger maxCount values.
                    int neededSpace = min(maxCount, nioBufferCount + count);
                    if (neededSpace > nioBuffers.length) {
                        nioBuffers = expandNioBufferArray(nioBuffers, neededSpace, nioBufferCount);
                        NIO_BUFFERS.set(threadLocalMap, nioBuffers);
                    }
                    if (count == 1) {
                        ByteBuffer nioBuf = entry.buf;
                        if (nioBuf == null) {
                            // cache ByteBuffer as it may need to create a new ByteBuffer instance if its a
                            // derived buffer
                           // internalNioBuffer exposes a view with position at readerIndex and limit at readerIndex + readableBytes.
                            entry.buf = nioBuf = buf.internalNioBuffer(readerIndex, readableBytes);
                        }
                        // Store the view in the selected NIO-buffer array.
                       // Increment the selected-buffer count.
                        nioBuffers[nioBufferCount++] = nioBuf;
                    } else {
                        // The code exists in an extra method to ensure the method is not too big to inline as this
                        // branch is not very likely to get hit very frequently.
                      // A composite ByteBuf may expose multiple NIO buffers.
                      // Add those views using the helper for multiple buffers.
                        nioBufferCount = nioBuffers(entry, buf, nioBuffers, nioBufferCount, maxCount);
                    }
                    // Stop once maxCount buffers have been selected.
                    if (nioBufferCount >= maxCount) {
                        break;
                    }
                }
            }
            entry = entry.next;
        }
    // Record the number of selected NIO buffers.
        this.nioBufferCount = nioBufferCount;
    // Record their total readable bytes.
        this.nioBufferSize = nioBufferSize;

        return nioBuffers;
    }

```

`SocketChannel` writes the resulting `ByteBuffer[]` to the transport.

What happens to an entry after its bytes are written?
### removeBytes
An entry may be consumed completely or only partially. `removeBytes` maintains the queue accordingly.

```

 public void removeBytes(long writtenBytes) {
        for (;;) {
             // Obtain the current entry's message.
            Object msg = current();
            if (!(msg instanceof ByteBuf)) {
                assert writtenBytes == 0;
                break;
            }

            final ByteBuf buf = (ByteBuf) msg;
            // Read the ByteBuf's current reader index.
            final int readerIndex = buf.readerIndex();
            // Count its readable bytes.
            final int readableBytes = buf.writerIndex() - readerIndex;
           // If writtenBytes covers the entire entry, the entry has been consumed.
           // Therefore remove it from the queue.
           // remove also releases the message and completes its promise.
            if (readableBytes <= writtenBytes) {
                if (writtenBytes != 0) {
                   // Report progress when a progressive promise is configured.
                    progress(readableBytes);
                   // Subtract the bytes consumed from the remaining written-byte count.
                    writtenBytes -= readableBytes;
                }
                remove();
            } else { // readableBytes > writtenBytes
                 // Only part of this entry has been written.
               // Advance its readerIndex and retain the entry for the next flush.
                if (writtenBytes != 0) {
                    buf.readerIndex(readerIndex + (int) writtenBytes);
                    progress(writtenBytes);
                }
                break;
            }
        }
       // Clear the selected NIO-buffer array after processing.
        clearNioBuffers();
    }

```

Removing an entry reduces `totalPendingSize` by its pending-byte estimate and overhead. If the total falls below the low watermark, Netty clears the corresponding unwritable bit. When this makes the channel writable again, it fires `channelWritabilityChanged`.

Finally examine `incompleteWrite`:

### incompleteWrite

```

  protected final void incompleteWrite(boolean setOpWrite) {

        // Did not write completely.
        // setOpWrite indicates whether selector write readiness is needed.
       // A zero-progress write means the transport cannot accept more bytes right now.
       // Register OP_WRITE and resume when the socket becomes writable.
        if (setOpWrite) {
            // Add OP_WRITE to the channel's selector interests.
            setOpWrite();
        } else {
            // It is possible that we have set the write OP, woken up by NIO because the socket is writable, and then
            // use our write quantum. In this case we no longer want to set the write OP because the socket is still
            // writable (as far as we know). We will find out next time we attempt to write if the socket is writable
            // and set the write OP if necessary.
          // When the spin budget expires after progress, clear OP_WRITE and schedule another flush task.
            clearOpWrite();

            // Schedule flush again later so other tasks can be picked up in the meantime
            eventLoop().execute(flushTask);
        }
    }

```


---
This completes the write-path walkthrough.


## Source version and reconstructed figures

A successful socket write means bytes were accepted by the local transport, not that the peer application consumed them. Writes can be partial. `incompleteWrite(true)` waits for selector write readiness after no progress; `incompleteWrite(false)` schedules another flush after the spin budget is exhausted. The original description of the false branch as “all data flushed” was incorrect. Composite buffers can produce multiple NIO views, and array expansion is not universally impossible.

Source baseline: Netty 4.1.53.Final (released October 13, 2020).

- [AbstractChannelHandlerContext.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/AbstractChannelHandlerContext.java)
- [AbstractChannel.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/AbstractChannel.java)
- [ChannelOutboundBuffer.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/ChannelOutboundBuffer.java)
- [NioSocketChannel.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/socket/nio/NioSocketChannel.java)
- [AbstractNioByteChannel.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/nio/AbstractNioByteChannel.java)
