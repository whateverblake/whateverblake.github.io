---
layout: default
title: Mooncake source walkthrough — a client that puts and gets
article: true
topic: Mooncake
order: 40
series_order: 3
nav_title: "Follow a Put and Get"
description: "Trace a value from the C++ API through connection lanes and sockets to owner memory and back."
---

# A client that puts and gets

The master is running and an owner has mounted 64 MiB of CPU memory. Now a
second client, the **caller**, puts a 4096-byte value into that memory and
reads it back. This article follows the call from the C++ API down to the TCP
sockets and back.

> **Setup:** the same as before: CPU memory · TCP · `P2PHANDSHAKE` · one
> memory replica. The [master article](mooncake_service_starting.html) covers
> key metadata and lookup; the [owner article](mooncake_owner_starting.html)
> covers listeners, registration and mounting.

## 1. Caller and owner share one client stack

"Owner" and "caller" are roles, not classes. Both use `RealClient`, `Client`,
`TransferEngine`, `TransferMetadata`, `MultiTransport`, `TcpTransport` and
`TransferSubmitter`. The owner program calls `RealClient::create()` and
`setup_internal()`; our application calls `RealClient::create()` and
`setup_real()`, which delegates to the same `setup_internal()`.

[![Same client stack, two roles: both run the shared setup (connect to the master, Transfer Engine, TCP listener, submitter); the owner then registers and mounts a 64 MiB global pool, the caller only registers a 16 MiB staging buffer.](assets/client-role-workflow.svg)](assets/client-role-workflow.svg)

Only the memory settings differ:

| Setting or behavior | Owner (previous article) | Caller (this article) |
| --- | --- | --- |
| Global segment size | 64 MiB | 0 |
| Local staging buffer | 0 | 16 MiB |
| Transfer Engine and TCP listeners | Created | Created |
| Register local staging memory | Skipped: size is zero | Register the 16 MiB buffer |
| Register and mount a global pool | Yes | Skipped: size is zero |
| Heartbeat and task polling | Start after the first mount | Not started: nothing is mounted |

The caller still needs its own Transfer Engine: its staging buffer is the
source of a Put and the destination of a Get. Contributing no storage does not
make it an RPC-only client.

Unlike the owner program, our application uses `RealClient` directly and
starts no client RPC server. Its logical name, `127.0.0.1:12346`, must differ
from the owner's; its handshake and data ports are picked separately.

For the shared startup details, see the owner's
[class map](mooncake_owner_starting.html),
[listener setup](mooncake_owner_starting.html#4-start-the-metadata-and-tcp-listeners)
and [local-buffer setup](mooncake_owner_starting.html#5-create-the-transfer-submitter-and-local-buffer).
The delegation is in
[`RealClient::setup_real()`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/real_client.cpp).

## 2. A small C++ Put/Get program

The application never builds a TCP work item or calls `PutStart` itself;
`RealClient` does that. This complete program creates a fresh key on each run,
puts 4096 bytes, reads them back, checks them and removes the object. The
master and owner must already be running in the same container.

Create `mooncake-store/src/blog_roundtrip.cpp` in your **Mooncake checkout**:

```cpp
#include <chrono>
#include <iostream>
#include <span>
#include <string>

#include "real_client.h"

int main() {
    auto client = mooncake::RealClient::create();
    const int setup = client->setup_real(
        "127.0.0.1:12346",       // Logical name, different from the owner.
        "P2PHANDSHAKE",
        0,                      // Contribute no global storage.
        16 * 1024 * 1024,        // Local staging buffer: 16 MiB.
        "tcp", "", "127.0.0.1:50051");
    if (setup != 0) {
        std::cerr << "setup failed: " << setup << '\n';
        return 1;
    }

    const auto id = std::chrono::steady_clock::now()
                        .time_since_epoch().count();
    const std::string key = "blog/example/" + std::to_string(id);
    const std::string value(4096, 'x');
    mooncake::ReplicateConfig config;
    config.replica_num = 1;

    const int put_result = client->put(
        key, std::span<const char>(value.data(), value.size()), config);
    bool matched = false;
    if (put_result == 0) {
        // Release the returned buffer before tearing down its client.
        auto buffer = client->get_buffer(key);
        if (buffer) {
            const std::string received(
                static_cast<const char*>(buffer->ptr()), buffer->size());
            matched = received == value;
        }
    }

    const int remove_result = client->remove(key, true);
    const int close_result = client->tearDownAll();
    std::cout << "put=" << put_result << ", matched=" << matched
              << ", remove=" << remove_result
              << ", close=" << close_result << '\n';
    return put_result == 0 && matched && remove_result == 0
                   && close_result == 0 ? 0 : 1;
}
```

For the CPU build from the [environment guide](environment_setting_up.html),
add this target at the end of `mooncake-store/src/CMakeLists.txt`:

```cmake
add_executable(blog_roundtrip blog_roundtrip.cpp)
target_compile_features(blog_roundtrip PRIVATE cxx_std_20)
target_link_libraries(blog_roundtrip PRIVATE
    mooncake_store transfer_engine asio_shared
    gflags::gflags yalantinglibs::yalantinglibs)
```

Inside the container, reconfigure, build and run:

```bash
cmake -S /workspace/mooncake -B /workspace/build
cmake --build /workspace/build --target blog_roundtrip --parallel 2
MC_STORE_MEMCPY=0 /workspace/build/mooncake-store/src/blog_roundtrip
```

The first command reuses the CMake options from the environment guide.
`MC_STORE_MEMCPY=0` turns off the Store's direct memory-copy shortcut so the
transfer goes through the Transfer Engine. (The normal copy into the staging
buffer still happens.)

In CLion: reload CMake, select `blog_roundtrip`, set `MC_STORE_MEMCPY=0` in
the run configuration's environment, keep **Before launch → Build** on, start
the master and owner, then debug.

Source: [`RealClient` API](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/include/real_client.h).

## 3. Follow one Put

A Put has three milestones: **reserve** space on the master, **move** the
bytes to the owner, **finalize** on the master.

[![One Put, three milestones: PutStart returns a replica descriptor; the caller fetches the owner's SegmentDesc over P2P the first time; a TCP WRITE sends header and bytes and the owner acknowledges; PutEnd marks the replica COMPLETE.](assets/put-sequence.svg)](assets/put-sequence.svg)

1. **Stage the bytes.** `RealClient::put_internal()` allocates from
   `client_buffer_allocator_`, copies the value in, and builds Store `Slice`
   records (pointer + size). The buffer stays alive until the Put finishes.
2. **Reserve the destination.** `Client::Put()` calls
   `MasterClient::PutStart()`. The reply carries the owner's endpoint, the
   allocated address and the length. The
   [master's Put example](mooncake_service_starting.html#4-example-what-put-stores)
   shows how that replica is created.
3. **Find the owner's data port.** `TransferWrite()` → `TransferData()` →
   `TransferSubmitter::submitTransferEngineOperation()`, whose `openSegment()`
   uses the peer cache or fetches the owner's description over P2P. The
   [owner's metadata section](mooncake_owner_starting.html#how-the-descriptions-reach-the-master-and-another-client)
   lists every map involved.
4. **Move the bytes.** Submit a WRITE through the TCP connection group and
   session (sections 4–6).
5. **Finalize.** After the transfer completes, `Client::Put()` sends
   `PutEnd()`. Only then is the Put done.

For example, the destination can be 4096 bytes at `0x70002000` in the owner.
That is a remote address; the caller cannot dereference it. The
[allocator section](mooncake_owner_starting.html#why-the-master-needs-an-allocator)
shows how the range is reserved inside the mounted pool.

> **Note:** in this revision `Client::Put()` treats `OBJECT_ALREADY_EXISTS` as
> success **without** replacing the value. Use a fresh key while debugging, or
> the write is skipped. Replacement uses the separate upsert API.

Follow [`RealClient::put_internal()`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/real_client.cpp)
and [`Client::Put()`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/client_service.cpp).

## 4. From a Store transfer to a TCP work item

For each Store slice, `submitTransferEngineOperation()` fills a transfer
request:

| Request field | Value for this Put |
| --- | --- |
| `opcode` | `WRITE` |
| `source` | Pointer into the caller's staging buffer |
| `target_id` | The caller's local Transfer Engine ID for the owner |
| `target_offset` | Owner destination address + this slice's offset |
| `length` | Bytes in this slice |

> **Note:** despite its name, `target_offset` holds a remote **address** on
> this memory path, not an offset from zero.

The submitter gets a batch ID and calls `submitTransfer()`. `MultiTransport`
routes the request to TCP, which splits it into transport slices and wraps
each piece of work in a `TcpWorkItem`. Each layer describes the same work at a
different level:

| Object | Role |
| --- | --- |
| Store `Slice` | Part of the application's staged value. |
| `TransferRequest` | Source, target, length and operation. |
| `TransferTask` | Tracks completion of a submitted request. |
| TCP transport slice | The transport's piece of that request. |
| `TcpWorkItem` | One TCP job queued for a connection lane. |
| `TransferFuture` | Lets the Store caller wait for the result. |

None of these wrappers copies the value again. The source buffer just has to
stay valid until the transfer finishes.

### What a `TcpWorkItem` carries

A `TcpWorkItem` wraps a transport `Slice`: operation, local address, remote
address and byte count. It does not contain the bytes or the key. Here are two
work items for the same owner (addresses are examples):

| Field via `TcpWorkItem::slice` | Work A: WRITE a new value | Work B: READ an existing value |
| --- | --- | --- |
| `opcode` | `WRITE` | `READ` |
| `source_addr` | `0x10000000`: caller bytes to send | `0x10002000`: caller buffer to fill |
| `tcp.dest_addr` | `0x70002000`: owner range reserved for the value | `0x70008000`: owner range holding the value |
| `length` | 4096 | 4096 |
| Bytes flow | caller → owner | owner → caller |

> **Watch the names on READ:** `source_addr` is always **local** memory (here,
> the destination of the bytes) and `tcp.dest_addr` is always **remote** memory
> (here, the source).

For **A**, `ClientSession` sends a WRITE header and then the 4096 bytes, and the
owner's `ServerSession` writes them to `0x70002000`. For **B**, `ClientSession`
sends a READ header for `0x70008000`, and the owner sends the bytes back into
`0x10002000`.

Both items target the same owner data endpoint, so they share one
`PeerConnectionGroup`; with two free lanes they run at the same time. (Reading
the value that A is still writing is different: wait for that Put to finish
first.) Application code never builds these items; it calls `put()` and
`get_buffer()`.

### One peer group, several lanes

**`PeerConnectionGroup` is a connection pool plus scheduler for one peer data
endpoint**: here, the owner's host and data port D. It never connects to the
master, and each different peer endpoint gets its own group. Its `lanes`
vector holds `ConnectionLane` objects; each lane runs one `TcpWorkItem` at a
time over its own TCP connection.

[![One peer group, several connections: the caller's PeerConnectionGroup has a queue and connection lanes; each lane's ClientSession shares the lane's socket; each connection reaches its own ServerSession through the owner's acceptor on port D.](assets/tcp-lanes.svg)](assets/tcp-lanes.svg)

The group exists for three reasons:

- **Overlap.** While one lane waits for the network or an acknowledgement,
  another keeps transferring.
- **Reuse.** A healthy socket serves later work items; no new connection per
  transfer.
- **Bounds.** Work beyond the free lanes waits in a bounded queue instead of
  opening unlimited sockets. The group also coordinates reconnection.

In the picture, work A runs on lane 0, B on lane 1, and C (another WRITE) waits.
If B finishes first, lane 1 takes C over its existing connection while A is
still running. A work item is a piece of transport work, not necessarily a
whole `put()` call. More lanes do not mean proportionally more throughput: they
still share bandwidth, CPU and the owner's memory bandwidth.

Reading the diagram from top to bottom:

1. New work enters the group's `queue`; `runGroupPump()` hands it to free lanes.
2. Each lane keeps its active work in `current`. Its `resolver` and `socket`
   are created when it needs a connection.
3. `startLaneSession()` creates a `ClientSession` with `lane->socket` and saves
   it in `lane->session`. The lane's `socket` and the session's `socket_` are
   shared pointers to **the same socket**.
4. On the owner, each accepted connection gets its own socket and
   `ServerSession`, all through the same `TcpContext::acceptor` on port D.
5. After a successful operation the lane can take more work on the same
   socket, with a new `ClientSession`. A failed connection may be closed and
   reconnected.

The diagram shows two lanes; `ConnectionLaneState::lanes_per_peer` defaults to
four. A lane is a connection slot, not a thread. The group's `executor` comes
from the caller's `TcpContext::io_context`, and one TCP worker thread runs the
callbacks of every lane.

Members: [`PeerConnectionGroup` and `ConnectionLane`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/include/transport/tcp_transport/tcp_transport.h).
Scheduling and reuse: [`runGroupPump`, `startLaneSession`, `handleLaneTerminal`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transport/tcp_transport/tcp_transport_lane_impl.h).
Routing: [`MultiTransport`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/multi_transport.cpp),
[`TcpTransport::prepareTransfer` and `startTransfer`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transport/tcp_transport/tcp_transport.cpp).

## 5. How `runGroupPump()` starts running

The TCP worker and its event loop already exist from client setup (see the
owner's [TcpContext section](mooncake_owner_starting.html#tcpcontext-connects-the-sockets-to-the-worker)).
This is how new work reaches them:

[![From posted work to a running session: the submitting thread posts runGroupPump to the executor; on the TCP worker, runGroupPump starts async_resolve, handleLaneResolved starts async_connect, handleLaneConnected makes the lane usable, startLaneSession runs the session I/O, and handleLaneTerminal reuses the lane.](assets/asio-flow.svg)](assets/asio-flow.svg)

When work enters a group, the pump is scheduled like this:

```cpp
asio::post(group->executor, [group, pump_epoch] {
    runGroupPump(group, pump_epoch);
});
```

`post()` only queues the handler. The calling thread does not jump into
`TcpTransport::worker()`; the worker, already inside `io_context.run()`, runs
the handler later. The pump runs on **events** (new work, a finished
connection, a finished session, a retry), not on a timer. It gives queued work
to free lanes and starts a connection for any lane that needs one.

### Resolve, connect, then send

`startLaneConnect()` creates a resolver and a socket on `group->executor`, sets
the stage to `RESOLVING` and calls `async_resolve()`. *Asynchronous* means the
result arrives later through a callback; it does not mean a new thread per
request.

The bundled Asio may run the blocking lookup on an internal resolver thread
and post the completion back to the event loop. Then `handleLaneResolved()`
starts `async_connect()`, and `handleLaneConnected()` makes the lane available
to the pump. For a numeric address like `127.0.0.1` there is no real DNS
lookup, but the callback flow is the same.

Two mechanisms protect the callbacks:

- captured `shared_ptr`s keep the group and lane **alive** while callbacks are
  pending;
- the **epoch** value lets a callback recognize that it belongs to an old
  attempt and ignore itself.

Sources: [`postGroupPump`, `runGroupPump`, `startLaneConnect`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transport/tcp_transport/tcp_transport_lane_impl.h),
[`TcpTransport::worker`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transport/tcp_transport/tcp_transport.cpp),
[bundled Asio resolver](https://github.com/alibaba/yalantinglibs/blob/7801bc9ad9021781f15217552214e325a1cf7373/include/ylt/thirdparty/asio/detail/impl/resolver_service_base.ipp).

## 6. The bytes between two sessions

Once a lane is connected, `startLaneSession()` creates a `ClientSession` and
calls `initiate()` with the source pointer, remote address, length and
operation.

[![A TCP WRITE: ClientSession sends a header with address and length, then the body; ServerSession checks the range, reads the body into owner memory, and sends a success status after the full body.](assets/tcp-write.svg)](assets/tcp-write.svg)

The client session sends a header with the operation, destination address and
byte count, then, for `WRITE`, the bytes from the staging buffer (in chunks if
large). The key is not sent: the Store already turned it into an address.

On the owner (see how an accepted socket
[becomes a `ServerSession`](mooncake_owner_starting.html#d-tcpcontextacceptor-listens-on-d)):

1. `readHeader()` decodes the operation and target range.
2. The session checks that the range is registered memory.
3. For `WRITE`, `readBody()` receives the bytes into the owner buffer.
4. With TCP protocol v2, the owner sends a success status once the **whole**
   body has arrived.
5. The session waits for the next header on the same connection.

The range check is transport memory validation. It is not a key lookup or a
tenant permission check.

> **When is a v2 WRITE done?** Only when the body write has finished **and**
> the owner's status has arrived. A local socket completion alone does not
> prove the owner processed the whole body. (The two can overlap in time; the
> diagram shows the logical order.)

Source: [`ClientSession`, `ServerSession` and `TcpContext`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transport/tcp_transport/tcp_transport_session_impl.h).

## 7. Wait, then finalize

The session's terminal callback enters `handleLaneTerminal()`, which records
the result and frees the lane for more work. `TransferData()` waits on the
transfer future (a future is not a thread). Then `Client::Put()` calls
`PutEnd()`; the master's
[PutEnd section](mooncake_service_starting.html#putend-make-the-replica-readable)
covers the state change. The application call returns and the staging
allocation can be released.

| Failure | What it means for the caller |
| --- | --- |
| `PutStart` fails | No destination was returned. |
| Peer discovery or TCP transfer fails | The value did not arrive; the client can revoke the reserved replica with `PutRevoke`. |
| `PutEnd` fails | The bytes may already be on the owner, but the Store did not confirm the object. |

Pausing the owner in a debugger also pauses its I/O and heartbeats; the earlier
articles cover cleanup and liveness.

Sources: [`handleLaneTerminal()`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transport/tcp_transport/tcp_transport_lane_impl.h),
[`TransferFuture`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/transfer_task.cpp).

## 8. Get the same key

The same caller now runs `get_buffer(key)`. Its `RealClient`, Transfer Engine,
buffer allocator and TCP worker already exist, and the owner's description is
cached.

[![Get for the same key: GetReplicaList returns readable replicas and a lease; the caller picks a replica, allocates a local destination, sends a TCP READ, and receives a status and the 4096 bytes.](assets/get-sequence.svg)](assets/get-sequence.svg)

1. `RealClient::get_buffer_internal()` calls `Client::Query(key)`, which asks
   the master for readable replicas and a lease. The
   [master's Get section](mooncake_service_starting.html#5-how-get-finds-the-same-key)
   follows the indexes.
2. `SelectBestReplica()` picks one (here there is only one). The caller
   allocates a local destination from `ClientBufferAllocator` and calls
   `Client::Get()`.
3. The transfer path prepares a READ for the owner's address and length,
   reusing the cached description and a healthy connection.
4. The owner's `ServerSession` handles the READ. With v2 it sends a status and
   then the bytes, which land in the local destination.
5. `get_buffer()` returns a buffer handle. The example checks the bytes and
   releases the handle before tearing down the client.

Get reserves nothing on the owner and calls no `PutEnd()`; it only reads the
completed replica. The read must finish within its lease, so a long pause at a
breakpoint can make it fail.

Sources: [`RealClient::get_buffer_internal()`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/real_client.cpp),
[`Client::Query()`, `Client::Get()`, `TransferRead()`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/client_service.cpp).

## 9. A breakpoint route

Start with a fresh caller process and a fresh key so the first peer handshake
and the first TCP connection both happen. With an existing connection, the
connection breakpoints do not fire again.

| Process | Breakpoint | What to inspect |
| --- | --- | --- |
| Caller | `RealClient::put_internal` | Application bytes, staging pointer, Store slices. |
| Caller | `TransferSubmitter::submitTransferEngineOperation` | Endpoint, target ID, source and target addresses. |
| Owner | `TransferMetadata::receivePeerMetadata` | Description returned to the caller. |
| Caller | `TcpTransport::runGroupPump` | Pending work, lane state, pump epoch. |
| Caller | `handleLaneResolved`, `handleLaneConnected` | Resolution and connection results. |
| Caller | `ClientSession::writeHeader`, `writeBody` | Operation, destination address, local payload. |
| Owner | `ServerSession::readHeader`, `readBody` | Registered target range, received bytes. |
| Caller | `TcpTransport::handleLaneTerminal` | Success or failure, lane reuse. |
| Caller | `RealClient::get_buffer_internal` | Read destination and buffer lifetime. |

> **Debugging async code:** "step into" cannot follow a callback that runs
> later on another thread. Put a breakpoint inside the callback and resume.
> And if the debugger stops all threads of the owner, its heartbeats and I/O
> stop too.

That connects the three original drawings: **startup** creates the services,
**mounting** makes owner memory available, and **Put** reserves a range, moves
the bytes into it and finalizes the record.
