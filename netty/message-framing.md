---
layout: default
article: true
topic: Netty
lang: en
title: "Handling Fragmented and Coalesced Messages in Netty"
description: "Understand TCP stream boundaries and length-field decoding across fragmented and coalesced reads."
order: 460
series_order: 6
---

# Handling Fragmented and Coalesced Messages in Netty

TCP applications often encounter fragmented or coalesced reads, sometimes called “half packets” and “sticky packets.” TCP is a byte stream: it does not preserve the boundaries between application writes. Segmentation, buffering, and the receiver's read sizes can make one message arrive across several reads or several messages arrive in one read. This is independent of whether an application message happens to exceed a particular IP packet size. Two common observations follow.

1) Fragmentation: a read contains only part of an application message. Large messages commonly span several network segments, but even a small message may require multiple application reads.

2) Coalescing: a read contains bytes from multiple application messages. The receiver must use the application protocol to identify their boundaries; TCP cannot supply those boundaries.

Common framing strategies are:
1) A delimiter marks the end of each message.
2) A header carries the message length.
3) Every message has a fixed length.

These strategies usually require a byte accumulator at the receiver. Incoming bytes accumulate until the decoder can identify a complete message. The decoder consumes that message's bytes and continues with the next message, retaining an incomplete remainder for future reads.
Netty calls the transformation from a byte stream into messages decoding, and the implementing component a decoder. It supplies decoders for all three strategies. We will examine length-field framing.

## LengthFieldBasedFrameDecoder
Some protocols reserve a fixed number of bytes for a field carrying the message length. Netty provides `LengthFieldBasedFrameDecoder` for them.

## ByteToMessageDecoder
`ByteToMessageDecoder` is the base class for decoding bytes into messages and the parent of `LengthFieldBasedFrameDecoder`. It extends `ChannelInboundHandlerAdapter`.
Network reads reach `ByteToMessageDecoder.channelRead` through the pipeline.

### ByteToMessageDecoder.channelRead
Here is `channelRead`:

```

   // msg is the data delivered by network I/O.
public void channelRead(ChannelHandlerContext ctx, Object msg) throws Exception {
        // This decoder consumes ByteBuf messages.
        if (msg instanceof ByteBuf) {
         // CodecOutputList stores messages produced by decoding.
            CodecOutputList out = CodecOutputList.newInstance();
            try {
                first = cumulation == null;
                // cumulation is the byte accumulator, represented as a ByteBuf.
                // cumulator implements accumulation; the default is MERGE_CUMULATOR.
                // Merge incoming bytes into the existing cumulation.
                cumulation = cumulator.cumulate(ctx.alloc(),
                        first ? Unpooled.EMPTY_BUFFER : cumulation, (ByteBuf) msg);
              // Pass accumulated bytes to the concrete decoder.
                callDecode(ctx, cumulation, out);
            } catch (DecoderException e) {
                throw e;
            } catch (Exception e) {
                throw new DecoderException(e);
            } finally {

                if (cumulation != null && !cumulation.isReadable()) {
                    // Release an accumulator with no readable bytes left.
                    numReads = 0;
                    cumulation.release();
                    cumulation = null;
                } else if (++ numReads >= discardAfterReads) {
                    // After discardAfterReads reads (default 16), try discarding consumed space.
                    // We did enough reads already try to discard some bytes so we not risk to see a OOME.
                    // See https://github.com/netty/netty/issues/4275
                    numReads = 0;
                    discardSomeReadBytes();
                }
                // Count decoded output messages.
                int size = out.size();
                firedChannelRead |= out.insertSinceRecycled();
               // Fire channelRead for the decoded outputs.
                fireChannelRead(ctx, out, size);
               // Recycle the output-list object.
                out.recycle();
            }
        } else {
           // Forward non-ByteBuf messages to the next pipeline handler.
            ctx.fireChannelRead(msg);
        }
    }

```

How are bytes from a new buffer added to `cumulation`?

```

        // alloc supplies storage for the accumulating ByteBuf.
        // in is the newly received buffer to append.
        public ByteBuf cumulate(ByteBufAllocator alloc, ByteBuf cumulation, ByteBuf in) {
            if (!cumulation.isReadable() && in.isContiguous()) {
                // If cumulation is empty and input buffer is contiguous, use it directly
              // If the initial accumulator is empty, reuse in and release the old empty buffer.
                cumulation.release();
                return in;
            }
            try {
                // Count the bytes in this incoming buffer.
                final int required = in.readableBytes();
                if (required > cumulation.maxWritableBytes() ||
                        (required > cumulation.maxFastWritableBytes() && cumulation.refCnt() > 1) ||
                        cumulation.isReadOnly()) {
                    // Expand cumulation (by replacing it) under the following conditions:
                    // - cumulation cannot be resized to accommodate the additional data
                    // - cumulation can be expanded with a reallocation operation to accommodate but the buffer is
                    //   assumed to be shared (e.g. refCnt() > 1) and the reallocation may not be safe.
                   // Expand the accumulator if the required writable capacity is unavailable.
                   // Allocate storage for the unread accumulated bytes plus the incoming bytes.
                  // Copy existing unread data into the new buffer and release the old accumulator.
                    return expandCumulation(alloc, cumulation, in);
                }
             // Append the incoming readable bytes.
                cumulation.writeBytes(in, in.readerIndex(), required);
                in.readerIndex(in.writerIndex());
                return cumulation;
            } finally {
                // We must release in in all cases as otherwise it may produce a leak if writeBytes(...) throw
                // for whatever release (for example because of OutOfMemoryError)
                // Release the incoming buffer when it is not reused as the accumulator.
                in.release();
            }
        }
    }

```


Now that bytes are accumulated, how are messages decoded from them?
`callDecode` is the decoding entry point.
### callDecode

```

// in is the byte accumulator; out stores decoded messages.
protected void callDecode(ChannelHandlerContext ctx, ByteBuf in, List<Object> out) {
        try {
            // Continue decoding while readable bytes remain and progress is possible.
            while (in.isReadable()) {
                int outSize = out.size();

                if (outSize > 0) {
                    // Deliver decoded outputs through channelRead.
                    fireChannelRead(ctx, out, outSize);
                    // Clear the output list after delivering those messages.
                    out.clear();

                    // Check if this handler was removed before continuing with decoding.
                    // If it was removed, it is not safe to continue to operate on the buffer.
                    //
                    // See:
                    // - https://github.com/netty/netty/issues/4635
                   // Stop if this decoder's context was removed from the pipeline.
                    if (ctx.isRemoved()) {
                        break;
                    }
                    outSize = 0;
                }
               // Record the number of readable accumulated bytes before decoding.
                int oldInputLength = in.readableBytes();
              // Invoke the concrete decoder through the reentry-protection wrapper.
                decodeRemovalReentryProtection(ctx, in, out);

                // Check if this handler was removed before continuing the loop.
                // If it was removed, it is not safe to continue to operate on the buffer.
                //
                // See https://github.com/netty/netty/issues/1664
                if (ctx.isRemoved()) {
                    break;
                }

                if (outSize == out.size()) {
                    if (oldInputLength == in.readableBytes()) {
                       // If decoding consumed no input and produced no output, await more data.
                        break;
                    } else {
                        continue;
                    }
                }

                if (oldInputLength == in.readableBytes()) {
                    // Producing output without consuming bytes violates the decoder contract.
                    throw new DecoderException(
                            StringUtil.simpleClassName(getClass()) +
                                    ".decode() did not read anything but decoded a message.");
                }

                if (isSingleDecode()) {
                    break;
                }
            }
        } catch (DecoderException e) {
            throw e;
        } catch (Exception cause) {
            throw new DecoderException(cause);
        }
    }

```

Continue into `decodeRemovalReentryProtection`:

```

 final void decodeRemovalReentryProtection(ChannelHandlerContext ctx, ByteBuf in, List<Object> out)
            throws Exception {
       // Mark decodeState as STATE_CALLING_CHILD_DECODE.
        decodeState = STATE_CALLING_CHILD_DECODE;
        try {
            // Call the concrete decode implementation.
            decode(ctx, in, out);
        } finally {
           // Removal during decode sets STATE_HANDLER_REMOVED_PENDING.
          // In that case, removePending becomes true.
            boolean removePending = decodeState == STATE_HANDLER_REMOVED_PENDING;
            decodeState = STATE_INIT;
            if (removePending) {
               // Deliver pending outputs before finishing handler removal.
                fireChannelRead(ctx, out, out.size());
                out.clear();
                handlerRemoved(ctx);
            }
        }
    }

```

Now examine the concrete `LengthFieldBasedFrameDecoder.decode`:
###

```

protected final void decode(ChannelHandlerContext ctx, ByteBuf in, List<Object> out) throws Exception {
       // Decode at most one frame through the two-argument decode method.
        Object decoded = decode(ctx, in);
        if (decoded != null) {
            // Append a non-null frame to the output list.
            out.add(decoded);
        }
    }


// Concrete frame-decoding implementation
protected Object decode(ChannelHandlerContext ctx, ByteBuf in) throws Exception {
       // Each decoder has a configured maximum frame length.
       // A frame larger than that maximum is discarded.
        if (discardingTooLongFrame) {
            discardingTooLongFrame(in);
        }
        // Wait until enough bytes exist to include the entire length field and its offset.
        if (in.readableBytes() < lengthFieldEndOffset) {
            return null;
        }
        // lengthFieldOffset locates the length field within the frame.
        // Calculate that field's position within the accumulator.
        int actualLengthFieldOffset = in.readerIndex() + lengthFieldOffset;
          // lengthFieldLength is the field width in bytes.
          // Read the unadjusted length-field value.
        long frameLength = getUnadjustedFrameLength(in, actualLengthFieldOffset, lengthFieldLength, byteOrder);

        if (frameLength < 0) {
            failOnNegativeLengthField(in, frameLength, lengthFieldEndOffset);
        }

      //lengthFieldEndOffset = lengthFieldOffset+lengthFieldLength
      // lengthAdjustment reconciles the protocol's field meaning with total frame length.
      // Some protocols count a body only, while others include some or all header bytes.
     // Configure this adjustment according to the actual wire format.
     // Add lengthAdjustment and lengthFieldEndOffset to obtain the full frame length.
        frameLength += lengthAdjustment + lengthFieldEndOffset;

        if (frameLength < lengthFieldEndOffset) {
            failOnFrameLengthLessThanLengthFieldEndOffset(in, frameLength, lengthFieldEndOffset);
        }
       // Discard a frame exceeding maxFrameLength.
        if (frameLength > maxFrameLength) {
            exceededFrameLength(in, frameLength);
            return null;
        }

        // never overflows because it's less than maxFrameLength
        int frameLengthInt = (int) frameLength;
        // If the complete frame has not arrived, return without extracting a message.
        if (in.readableBytes() < frameLengthInt) {
            return null;
        }
        // initialBytesToStrip removes the configured prefix from each delivered frame.
        if (initialBytesToStrip > frameLengthInt) {
            failOnFrameLengthLessThanInitialBytesToStrip(in, frameLength, initialBytesToStrip);
        }
        in.skipBytes(initialBytesToStrip);

        // extract frame
        int readerIndex = in.readerIndex();
       // Calculate the number of frame bytes remaining after stripping.
        int actualFrameLength = frameLengthInt - initialBytesToStrip;
       // Extract one frame from the accumulator.
        ByteBuf frame = extractFrame(ctx, in, readerIndex, actualFrameLength);
        // Advance the reader index to the start of the next frame.
        in.readerIndex(readerIndex + actualFrameLength);
        return frame;
    }

```


This completes normal frame decoding.
If a frame exceeds the configured maximum, the decoder discards it. Here are the details.
### exceededFrameLength

```


 private void exceededFrameLength(ByteBuf in, long frameLength) {
        // Calculate how many frame bytes remain beyond the bytes already accumulated.
        long discard = frameLength - in.readableBytes();
        // Record the oversized frame length for later error reporting.
        tooLongFrameLength = frameLength;

        if (discard < 0) {
            // If all frame bytes are present with additional data, skip the oversized frame directly.
            // buffer contains more bytes then the frameLength so we can discard all now
            in.skipBytes((int) frameLength);
        } else {
            // Enter the discard mode and discard everything received so far.
         // Otherwise the accumulator holds only part of the oversized frame.
         // The remaining bytes may still be in transit.

           // Keep discarding on future decode invocations until the whole oversized frame is skipped.
            discardingTooLongFrame = true;
         // Record how many bytes still need to be discarded.
            bytesToDiscard = discard;
           // Discard all currently accumulated bytes from this oversized frame.
            in.skipBytes(in.readableBytes());
        }
        failIfNecessary(true);
    }

```

At the start of `decode`, `discardingTooLongFrame` determines whether bytes from a previously detected oversized frame still need discarding.
### discardingTooLongFrame

```

 private void discardingTooLongFrame(ByteBuf in) {
        long bytesToDiscard = this.bytesToDiscard;
        // Bound this invocation's discard by the available readable bytes.
        int localBytesToDiscard = (int) Math.min(bytesToDiscard, in.readableBytes());
       // Skip localBytesToDiscard bytes.
        in.skipBytes(localBytesToDiscard);
        bytesToDiscard -= localBytesToDiscard;
         // Update the remaining discard count.
        this.bytesToDiscard = bytesToDiscard;
        failIfNecessary(false);
    }

```

Continue into `failIfNecessary`:

```

private void failIfNecessary(boolean firstDetectionOfTooLongFrame) {

        if (bytesToDiscard == 0) {
            // Zero remaining bytes means the oversized frame is fully discarded.
            // Reset to the initial state and tell the handlers that
            // the frame was too large.
            long tooLongFrameLength = this.tooLongFrameLength;
           // Reset oversized-frame bookkeeping.
            this.tooLongFrameLength = 0;
            discardingTooLongFrame = false;
            if (!failFast || firstDetectionOfTooLongFrame) {
                fail(tooLongFrameLength);
            }
        } else {
            // Keep discarding and notify handlers if necessary.
            if (failFast && firstDetectionOfTooLongFrame) {
                // Throw when the configured failFast policy requires reporting the oversized frame.
                fail(tooLongFrameLength);
            }
        }
    }

```



## Source version and reconstructed figures

The original packet-size explanation has been corrected: TCP segmentation and application read boundaries are distinct, and TCP never guarantees application message boundaries. In this baseline the default merge cumulator can reuse a buffer or copy into expanded storage. The length decoder computes total frame size from the field value, field-end offset, and adjustment; `initialBytesToStrip` affects delivery rather than the size used to validate the frame.

Source baseline: Netty 4.1.53.Final (released October 13, 2020).

- [ByteToMessageDecoder.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/codec/src/main/java/io/netty/handler/codec/ByteToMessageDecoder.java)
- [LengthFieldBasedFrameDecoder.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/codec/src/main/java/io/netty/handler/codec/LengthFieldBasedFrameDecoder.java)
- [DelimiterBasedFrameDecoder.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/codec/src/main/java/io/netty/handler/codec/DelimiterBasedFrameDecoder.java)
- [FixedLengthFrameDecoder.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/codec/src/main/java/io/netty/handler/codec/FixedLengthFrameDecoder.java)
