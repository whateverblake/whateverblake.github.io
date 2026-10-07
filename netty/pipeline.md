---
layout: default
article: true
topic: Netty
lang: en
title: "How Netty Pipeline Events Travel Through Handlers"
description: "Follow inbound and outbound event propagation through handler contexts and channel initializers."
order: 430
series_order: 3
---

# How Netty Pipeline Events Travel Through Handlers

Every Netty channel has a **pipeline**: a chain of handlers that events pass through. This article explains how the chain is built, how a handler is wrapped in a context, and how an event moves from one handler to the next.

> **Source:** Netty 4.1.53.Final (October 2020). Code excerpts keep the original selection; comments are translated. Figures are the author's original diagrams with English labels.

## 1. The pipeline

The pipeline is the chain-of-responsibility pattern. It is a **doubly linked list**: each user handler is wrapped in a `DefaultChannelHandlerContext`, and the contexts are the list's nodes. Their order follows how and where the handlers were added.

### `DefaultChannelPipeline`

The default pipeline starts with two fixed nodes, **head** and **tail**; your handlers go between them. I/O has two directions, **read** and **write**, and Netty has one handler interface for each:

| Direction | Interface | Receives | Travels |
| --- | --- | --- | --- |
| Inbound | `ChannelInboundHandler` | read events and inbound lifecycle events | head → tail |
| Outbound | `ChannelOutboundHandler` | write requests and other outbound operations | tail → head |

An outbound call made through a **context** starts at that context, not at the tail.

[![Inbound and outbound event directions through the pipeline](assets/pipeline-01.svg){: .diagram}](assets/pipeline-01.svg)

### Handler

A handler is the basic unit of event processing. Your application's I/O logic lives in your own handlers.

### `ChannelHandlerContext`

A context holds one handler plus its position in the pipeline. The pipeline's nodes are contexts; the usual implementation is `DefaultChannelHandlerContext`:

```java
final class DefaultChannelHandlerContext extends AbstractChannelHandlerContext {

    // DefaultChannelHandlerContext stores the user-defined handler.
    private final ChannelHandler handler;

    DefaultChannelHandlerContext(
            DefaultChannelPipeline pipeline, EventExecutor executor, String name, ChannelHandler handler) {
        super(pipeline, executor, name, handler.getClass());
        this.handler = handler;
    }

    @Override
    public ChannelHandler handler() {
        return handler;
    }
}
```

Its superclass, `AbstractChannelHandlerContext`, has `prev` and `next` fields. That is what makes the pipeline a doubly linked list.

## 2. Wrapping a handler in a context

What happens when you call `pipeline.addLast()` with your handler? It ends up here:

```java
 @Override
    public final ChannelPipeline addLast(EventExecutorGroup group, String name, ChannelHandler handler) {
        final AbstractChannelHandlerContext newCtx;
        synchronized (this) {
            checkMultiplicity(handler);
           // newContext constructs a DefaultChannelHandlerContext that stores this handler.
            newCtx = newContext(group, filterName(name, handler), handler);
           // Append the new context before the pipeline's tail node.
            addLast0(newCtx);

            // If the registered is false it means that the channel was not registered on an eventLoop yet.
            // In this case we add the context to the pipeline and add a task that will call
            // ChannelHandler.handlerAdded(...) once the channel is registered.
            if (!registered) {
                newCtx.setAddPending();
                callHandlerCallbackLater(newCtx, true);
                return this;
            }

            EventExecutor executor = newCtx.executor();
            if (!executor.inEventLoop()) {
                callHandlerAddedInEventLoop(newCtx, executor);
                return this;
            }
        }
        callHandlerAdded0(newCtx);
        return this;
    }
```

### `executionMask`

Creating a `DefaultChannelHandlerContext` runs the `AbstractChannelHandlerContext` constructor, which computes `executionMask`. A pipeline has many event types, and each handler implements only some callbacks. The mask records **which callbacks this handler wants**, so Netty can skip handlers that don't care about an event:

```java
private static int mask0(Class<? extends ChannelHandler> handlerType) {
        int mask = MASK_EXCEPTION_CAUGHT;
        try {
            if (ChannelInboundHandler.class.isAssignableFrom(handlerType)) {
                mask |= MASK_ALL_INBOUND;

                if (isSkippable(handlerType, "channelRegistered", ChannelHandlerContext.class)) {
                    mask &= ~MASK_CHANNEL_REGISTERED;
                }
                if (isSkippable(handlerType, "channelUnregistered", ChannelHandlerContext.class)) {
                    mask &= ~MASK_CHANNEL_UNREGISTERED;
                }
                if (isSkippable(handlerType, "channelActive", ChannelHandlerContext.class)) {
                    mask &= ~MASK_CHANNEL_ACTIVE;
                }
                if (isSkippable(handlerType, "channelInactive", ChannelHandlerContext.class)) {
                    mask &= ~MASK_CHANNEL_INACTIVE;
                }
                if (isSkippable(handlerType, "channelRead", ChannelHandlerContext.class, Object.class)) {
                    mask &= ~MASK_CHANNEL_READ;
                }
                if (isSkippable(handlerType, "channelReadComplete", ChannelHandlerContext.class)) {
                    mask &= ~MASK_CHANNEL_READ_COMPLETE;
                }
                if (isSkippable(handlerType, "channelWritabilityChanged", ChannelHandlerContext.class)) {
                    mask &= ~MASK_CHANNEL_WRITABILITY_CHANGED;
                }
                if (isSkippable(handlerType, "userEventTriggered", ChannelHandlerContext.class, Object.class)) {
                    mask &= ~MASK_USER_EVENT_TRIGGERED;
                }
            }

            if (ChannelOutboundHandler.class.isAssignableFrom(handlerType)) {
                mask |= MASK_ALL_OUTBOUND;

                if (isSkippable(handlerType, "bind", ChannelHandlerContext.class,
                        SocketAddress.class, ChannelPromise.class)) {
                    mask &= ~MASK_BIND;
                }
                if (isSkippable(handlerType, "connect", ChannelHandlerContext.class, SocketAddress.class,
                        SocketAddress.class, ChannelPromise.class)) {
                    mask &= ~MASK_CONNECT;
                }
                if (isSkippable(handlerType, "disconnect", ChannelHandlerContext.class, ChannelPromise.class)) {
                    mask &= ~MASK_DISCONNECT;
                }
                if (isSkippable(handlerType, "close", ChannelHandlerContext.class, ChannelPromise.class)) {
                    mask &= ~MASK_CLOSE;
                }
                if (isSkippable(handlerType, "deregister", ChannelHandlerContext.class, ChannelPromise.class)) {
                    mask &= ~MASK_DEREGISTER;
                }
                if (isSkippable(handlerType, "read", ChannelHandlerContext.class)) {
                    mask &= ~MASK_READ;
                }
                if (isSkippable(handlerType, "write", ChannelHandlerContext.class,
                        Object.class, ChannelPromise.class)) {
                    mask &= ~MASK_WRITE;
                }
                if (isSkippable(handlerType, "flush", ChannelHandlerContext.class)) {
                    mask &= ~MASK_FLUSH;
                }
            }

            if (isSkippable(handlerType, "exceptionCaught", ChannelHandlerContext.class, Throwable.class)) {
                mask &= ~MASK_EXCEPTION_CAUGHT;
            }
        } catch (Exception e) {
            // Should never reach here.
            PlatformDependent.throwException(e);
        }

        return mask;
    }
```

The mask comes from the callbacks the handler class overrides, taking `@Skip` annotations into account.

## 3. How an event travels

The pipeline is a linked list, so how does an event move from node to node? Take `channelRegistered` as the example. When a channel registers with its `NioEventLoop`, it fires `channelRegistered`, starting at `DefaultChannelPipeline.fireChannelRegistered()`:

```java
public final ChannelPipeline fireChannelRegistered() {
         // head is the first context: registration propagates from head toward tail.
        AbstractChannelHandlerContext.invokeChannelRegistered(head);
        return this;
    }
```

The static `AbstractChannelHandlerContext.invokeChannelRegistered`:

```java
  static void invokeChannelRegistered(final AbstractChannelHandlerContext next) {
        EventExecutor executor = next.executor();
        if (executor.inEventLoop()) {
             // Invoke the registration callback on this context.
            next.invokeChannelRegistered();
        } else {
            executor.execute(new Runnable() {
                @Override
                public void run() {
                    next.invokeChannelRegistered();
                }
            });
        }
    }
```

The instance method it calls:

```java
private void invokeChannelRegistered() {
        if (invokeHandler()) {
            try {
                // Call channelRegistered on the handler associated with this context.
                // This invokes the callback overridden by application code.
                ((ChannelInboundHandler) handler()).channelRegistered(this);
            } catch (Throwable t) {
                notifyHandlerException(t);
            }
        } else {
            fireChannelRegistered();
        }
    }
```

To pass the event on, your handler's `channelRegistered` calls `ctx.fireChannelRegistered()`:

```java
public ChannelHandlerContext fireChannelRegistered() {
  // Find the next inbound context toward the tail that can handle channelRegistered.
invokeChannelRegistered(findContextInbound(MASK_CHANNEL_REGISTERED));
        return this;
    }
```

The same pattern holds for every event. In the diagram, `XXX` is the event (registered, added, …) and `YY` its direction (inbound or outbound):

[![Propagate an event across handler contexts](assets/pipeline-02.svg){: .diagram}](assets/pipeline-02.svg)

> **Propagation is opt-in.** An event does not visit every handler automatically. Each handler must call `ctx.fireXXX()` (or the outbound equivalent) to pass it on.

## 4. `ChannelInitializer`

`ChannelInitializer` is a built-in inbound handler that installs your other handlers. You add it first and override `initChannel` to fill the pipeline. When any handler is added, Netty calls its `handlerAdded` callback; for `ChannelInitializer` that callback runs `initChannel` and then removes the initializer itself:

```java
 @Override
    public void handlerAdded(ChannelHandlerContext ctx) throws Exception {
       // Check whether the channel has registered yet.
       // Before registration, handler-added callbacks are retained as pending callbacks.
       // Registration later processes that pending callback list.
    // Invoke handlerAdded for each pending addition.
        if (ctx.channel().isRegistered()) {
            // This should always be true with our current DefaultChannelPipeline implementation.
            // The good thing about calling initChannel(...) in handlerAdded(...) is that there will be no ordering
            // surprises if a ChannelInitializer will add another ChannelInitializer. This is as all handlers
            // will be added in the expected order.
           // Invoke the application's overridden initChannel method.
           // This installs the application handlers in the pipeline.
           // After successful initialization, remove the ChannelInitializer itself.
          // The head, tail, and installed application handlers remain.
            if (initChannel(ctx)) {

                // We are done with init the Channel, removing the initializer now.

                removeState(ctx);
            }
        }
    }
```

That is the whole pipeline mechanism.

## Notes on the source

- Outbound calls made through a context start at the previous outbound context; calls made through the channel or the pipeline start at the tail.
- Both lifecycle events and I/O operations go through the pipeline.

Source references (Netty 4.1.53.Final, released October 13, 2020):

- [DefaultChannelPipeline.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/DefaultChannelPipeline.java)
- [AbstractChannelHandlerContext.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/AbstractChannelHandlerContext.java)
- [ChannelHandlerMask.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/ChannelHandlerMask.java)
- [ChannelInitializer.java](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/ChannelInitializer.java)
