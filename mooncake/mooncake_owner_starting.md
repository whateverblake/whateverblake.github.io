---
layout: default
title: How a Mooncake owner starts and mounts memory
article: true
topic: Mooncake
order: 30
series_order: 2
nav_title: "Turn a client into a memory owner"
description: "Follow the class relationships, TCP listeners, memory registration, and segment mounting."
---

# How a Mooncake owner starts and mounts memory

An **owner** is a client that lends its memory to the cluster. The master
records that memory as capacity and decides where objects go, but the object
bytes always stay in the owner.

This article starts the public `mooncake_client` program as an owner and
follows it until its 64 MiB pool is mounted on the master.

> **Setup:** CPU memory · TCP · `P2PHANDSHAKE`. In P2P mode one Transfer Engine
> asks another directly for its transport description; there is no external
> metadata server. The master still decides object placement and tracks
> whether the owner is alive.

Start with the objects inside the owner process. Indentation means "holds":

[![Owner class map: RealClient holds Client and ClientBufferAllocator. Client holds MasterClient, TransferSubmitter, mounted segment records and TransferEngine. TransferEngineImpl holds MultiTransport and the shared TransferMetadata. TcpTransport owns TcpContext; the metadata plugin owns the handshake listener.](assets/owner-class-map.svg)](assets/owner-class-map.svg)

Three details help when you read the source:

- `TransferSubmitter` belongs to `Client`. Its `engine_` refers to the **same**
  `TransferEngine` that `Client::transfer_engine_` holds.
- `TransferEngineImpl`, `MultiTransport` and `TcpTransport` share **one**
  `TransferMetadata` object (the dashed arrow).
- `Client::mounted_segments_` holds Store `Segment` records. The maps inside
  `TransferMetadata` hold Transfer Engine descriptions. They serve different
  purposes.

All source links use commit
[`719735896c86b56fabec6cf3e825fb2ea640597a`](https://github.com/kvcache-ai/Mooncake/tree/719735896c86b56fabec6cf3e825fb2ea640597a)
and the `TransferEngineImpl` implementation used by this TCP setup.

## 1. Start one owner

Build the programs with the [environment guide](environment_setting_up.html)
and start the master from the [previous article](mooncake_service_starting.html).
It must listen on `127.0.0.1:50051` in the same container. Then, in another
terminal **inside the container**:

```bash
cd /workspace/build/mooncake-store/src
./mooncake_client \
  --host=127.0.0.1:12345 \
  --metadata_server=P2PHANDSHAKE \
  --master_server_address=127.0.0.1:50051 \
  --global_segment_size='64 MB' \
  --local_buffer_size=0 \
  --protocol=tcp \
  --port=50052
```

Use the same arguments in a CLion run configuration for `mooncake_client`,
with the build step enabled. All addresses are container loopback addresses.

> **Note:** Mooncake's size parser reads `MB` as `1024 × 1024` bytes, so
> `'64 MB'` is **64 MiB** (67,108,864 bytes). It does not accept `MiB`. See
> `try_string_to_byte_size` in
> [utils.h](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/include/utils.h).

`--local_buffer_size=0` is intentional. This owner still contributes 64 MiB of
global storage; the local transfer buffer is a separate allocation that it
simply does not need.

## 2. How the objects fit together

The objects in the map are all inside one process. Each one owns one job: the
Store API, master requests, transfer submission, peer metadata or socket I/O.

| Object | Key member | Job |
| --- | --- | --- |
| `RealClient` | Inherits `PyClient`; inherited `client_` points to `Client`. | High-level API; owns this process's buffers and services. |
| `Client` | `master_client_` is a `MasterClient`. | Sends Store RPCs such as `MountSegment`, `Ping` and `PutStart`. |
| `Client` | `transfer_engine_` points to `TransferEngine`. | The engine that registers memory and moves bytes. |
| `Client` | `transfer_submitter_` points to `TransferSubmitter`. | Submits Store data transfers to the engine. |
| `TransferSubmitter` | `engine_` refers to that same `TransferEngine`. | Uses the client's engine; never creates a second one. |
| `TransferEngine` | `impl_` points to `TransferEngineImpl`. | Public transfer API; delegates to the implementation. |
| `TransferEngineImpl` | `multi_transports_` points to `MultiTransport`. | Manages installed transports and routes requests. |
| `TransferEngineImpl` | `metadata_` points to `TransferMetadata`. | Holds local and peer transport descriptions. |
| `MultiTransport` | `transport_map_["tcp"]` holds a `shared_ptr<Transport>` to a `TcpTransport`. | Picks the transport for each request. |
| `TcpTransport` | Inherits `Transport`; `context_` → `TcpContext`; `thread_` is its worker. | TCP memory registration and data transfer. |
| `TcpContext` | `io_context`, `acceptor`, a validation callback. | Runs async I/O, accepts data connections, checks memory ranges. |
| `TransferMetadata` | `handshake_plugin_` → `SocketHandShakePlugin` in P2P mode. | Exchanges descriptions with peers through the handshake listener. |

Through its `PyClient` base, `RealClient` also holds
`client_buffer_allocator_`, which manages local staging space. Global storage
is managed separately; sections 6–8 cover both.

### `Transport` is the interface, `TcpTransport` the implementation

`Transport` defines the operations every transport provides, and
`TcpTransport` implements them. `MultiTransport`'s map stores the base type,
and its `"tcp"` entry points to a `TcpTransport`: one object, seen through its
base class. Despite its name, `MultiTransport` can manage a single protocol,
and it is not an I/O thread.

### One shared `TransferMetadata`

`TransferEngineImpl` creates the metadata object and gives it to
`MultiTransport`. When TCP is installed, `MultiTransport` passes the same
object to `TcpTransport::install()`, which keeps it in `metadata_` (inherited
from `Transport`):

```text
TransferEngineImpl::metadata_ ──────────┐
MultiTransport::metadata_ ─────────────┼──> one TransferMetadata object
TcpTransport's inherited metadata_ ───┘
```

This matters during memory registration. TCP adds a `BufferDesc` to the local
description through `TransferMetadata::addLocalMemoryBuffer()`, and the
handshake handler reads the same object when a peer asks for it. Nothing has
to be copied between three metadata managers.

`TransferMetadata` holds the local and peer segment-description maps, the
name-to-ID map and the local handshake endpoint. In P2P mode
`handshake_plugin_` does the socket exchange; no external `storage_plugin_` is
created.

> This is **Transfer Engine metadata**: endpoints and registered address
> ranges. The master holds a different kind: keys, replica states and
> placement.

### `TcpContext` connects the sockets to the worker

`TcpTransport` creates its `TcpContext` and starts `thread_`. That thread calls
`context_->doAccept()` and then `context_->io_context.run()`.

- `io_context` tracks pending async operations and ready callbacks. It is an
  object, not a thread.
- `acceptor` listens for TCP data connections. It is built with that
  `io_context`.
- Each accepted connection becomes a `ServerSession`. Its async reads and
  writes use the socket's executor, so they run on the same event loop. There
  is no thread per connection.
- The validation callback uses the shared metadata to check that an incoming
  address range is registered.

The sending side uses the same event loop: `lane_runtime_` stores an executor
from the context, and connection groups, resolvers and sockets use it. The
next article follows that path through `PeerConnectionGroup` and
`ClientSession`.

The P2P handshake listener is a different socket on a different thread.
Sharing `TransferMetadata` does not merge them.

### When each piece becomes ready

The class map shows *what* exists. This shows *when* it starts:

[![Owner startup: create RealClient, connect to the master, initialize the Transfer Engine and TCP, allocate and register the pool, mount it on the master, start heartbeats, then start the client RPC server.](assets/owner-startup.svg)](assets/owner-startup.svg)

## 3. Connect to the master first

`main()` initializes `ResourceTracker` before any other thread so it can set up
signal handling. `RealClient::create()` builds the client and registers it with
the tracker, then `main()` calls `setup_internal()`.

Our `--host` includes a port, so `127.0.0.1:12345` becomes the logical client
name. Without a port, setup can pick a free one and retry; that branch is not
used here.

`setup_internal()` calls `Client::Create()`, which builds `Client` and connects
to the master. `MasterClient::Connect()` calls the master's
`WrappedMasterService::ServiceReady()`; the reply carries the Store version,
and the client checks that it matches its own. `Client::Create()` then asks
for storage configuration and initializes the Transfer Engine.

Read `RealClient::setup_internal` in
[real_client.cpp](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/real_client.cpp),
`Client::Create` in
[client_service.cpp](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/client_service.cpp)
and `MasterClient::Connect` in
[master_client.cpp](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/master_client.cpp).

## 4. Start the metadata and TCP listeners

The owner needs two listeners:

- The **handshake listener** (port **H**) answers peers that ask for the
  owner's transport description. Its socket belongs to `SocketHandShakePlugin`.
- The **TCP data listener** (port **D**) accepts connections that read or write
  object bytes. Its socket is `TcpContext::acceptor`, run by `TcpTransport`'s
  worker.

H and D are labels, not settings: the public revision picks both ports
automatically.

[![Two listeners: SocketHandShakePlugin listens on handshake port H; TcpContext::acceptor listens on data port D. A peer first asks H for the SegmentDesc, then connects to D to move bytes.](assets/owner-listeners.svg)](assets/owner-listeners.svg)

### A. Initialize the engine

After connecting, `Client::Create()` creates a `TransferEngine` and calls
`Client::InitTransferEngine()`, which enters
[`TransferEngineImpl::init()`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transfer_engine_impl.cpp).
It picks port H and creates `TransferMetadata` and `MultiTransport`. In P2P
mode the engine advertises this handshake port as its endpoint, and
`TransferMetadata` creates a `SocketHandShakePlugin`. Creating the plugin does
not start listening yet.

### B. `SocketHandShakePlugin` listens on H

[`TransferMetadata::addRpcMetaEntry()`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transfer_metadata.cpp)
saves the local handshake address, registers callbacks for peer metadata,
notifications and probes, and calls the plugin's `startDaemon()`.

[`SocketHandShakePlugin::startDaemon()`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transfer_metadata_plugin.cpp)
uses the prepared socket (or creates and binds one), calls `listen()` on
`listen_fd_`, and starts its `listener_` thread, which waits in `accept()`.
`TransferMetadata` supplies the request callbacks; the plugin owns the socket.

Setup now continues while this listener runs. A later peer request reaches
`receivePeerMetadata()`, which returns the owner's description. That
description fills in further as TCP is installed and buffers are registered.

### C. Install TCP and describe the data endpoint

Back in `Client::InitTransferEngine()`, the TCP transport is installed through
[`TcpTransport::install()`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transport/tcp_transport/tcp_transport.cpp).
It picks port D, and `allocateLocalSegmentID()` creates or updates the local
`SegmentDesc` with the TCP data host, port and protocol version.

> **Note:** despite its name, this does not mount a Store memory pool. The
> global pool is allocated and registered later, in sections 6–7.

Installation calls `startHandshakeDaemon()` again; the plugin sees its
listener is already running and returns. `updateLocalSegmentDesc()` then
updates the description. In P2P mode nothing is uploaded anywhere: peers fetch
it through listener H.

### D. `TcpContext::acceptor` listens on D

TCP installation constructs
[`TcpContext`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transport/tcp_transport/tcp_transport_session_impl.h).
Its constructor builds `acceptor(io_context)` (an `asio::ip::tcp::acceptor`),
then opens, binds and listens on D. It also stores the range-validation
callback. `TcpTransport` then starts its worker thread:

```cpp
context_->doAccept();         // Register an asynchronous accept.
context_->io_context.run();   // Run ready callbacks and wait for I/O.
```

When a data connection arrives, the accept callback creates a
`ServerSession` and calls `start()`, which begins reading a request header. A
WRITE request then receives bytes into a registered range; a READ request sends
bytes from one. Every session runs on this one event loop.

### What is ready after this stage

| Port | Who listens | How requests are handled |
| --- | --- | --- |
| Handshake H | `SocketHandShakePlugin::listen_fd_`, accepted by its `listener_` thread | Callbacks in `TransferMetadata`, such as `receivePeerMetadata()`. |
| TCP data D | `TcpContext::acceptor` | The `TcpTransport` worker runs the loop; one `ServerSession` per connection. |

A peer first asks H for the owner's data endpoint and registered ranges, then
connects to D to move bytes. Both listeners are up, but there is still no
storage: listening on a port does not make memory available to the Store.

## 5. Create the transfer submitter and local buffer

After the engine, `Client::Create()` calls `Client::InitTransferSubmitter()`.
The submitter turns Store transfers into Transfer Engine requests. With a
TCP-only engine, a local memory-copy shortcut is enabled by default for
same-endpoint transfers; remote transfers still use TCP.

Back in `RealClient::setup_internal()`, `ClientBufferAllocator` is created.
With `--local_buffer_size=0` it has no backing buffer and registration is
skipped. With a positive size, setup would allocate a separate buffer,
register it with the engine and record its bounds in `local_buffer_region_`.
That registration alone does not mount any storage.

See `TransferSubmitter::TransferSubmitter` in
[transfer_task.cpp](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/transfer_task.cpp)
and the constructors in
[client_buffer.cpp](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/client_buffer.cpp).

## 6. Allocate the global pool

Setup allocates one 64 MiB CPU pool. `RealClient::segment_ptrs_` keeps it alive,
and its address and size go to `Client::MountSegment()`. From here on the pool
exists once, but three different records describe it:

[![One 64 MiB pool and three descriptions: MemoryRegion in TransferEngineImpl, BufferDesc inside SegmentDesc in TransferMetadata, and the Store Segment sent to the master.](assets/owner-memory.svg)](assets/owner-memory.svg)

## 7. Register the range, then mount it

Mounting connects two facts: **the owner has real memory**, and **the master
may now hand out pieces of it**. The pool's contents are never sent to the
master.

[![Mounting a segment: RealClient calls Client::MountSegment, Client registers the range with the TransferEngine, builds a Segment and sends MountSegment through MasterClient; the master creates an allocator and records, and the owner records the mount on success.](assets/segment-mount-flow.svg)](assets/segment-mount-flow.svg)

### The classes involved

`RealClient::setup_internal()` calls
`client_->MountSegment(ptr, mount_size, protocol, seg_location)`.
`Client::MountSegment()` delegates to `MountSegmentAndGetId()`, which does the
work and returns the segment UUID; the wrapper returns only success or an
error.

| Class | Job during the mount |
| --- | --- |
| `RealClient` | Allocates the pool, keeps it alive, passes address and size on. |
| `Client` | Checks the range, registers it, builds the `Segment`, calls the master, records the mount. |
| `TransferEngine` / `TransferEngineImpl` | Registers the range; tracks pending and committed registrations. |
| `MultiTransport` | Holds the transports that registration visits. Does not send the RPC. |
| `TcpTransport` | Adds a `BufferDesc` through `TransferMetadata`. |
| `TransferMetadata` | Serves the updated description to peers. |
| `MasterClient` | Sends the `Segment` and owner client UUID to the master. |

`TransferSubmitter` takes no part; it is used later when data moves. No object
transfer is needed to finish a mount.

### Register before announcing

`MountSegmentAndGetId()` validates the parameters, locks
`mounted_segments_mutex_`, checks for overlap with existing mounts and calls
`registerLocalMemory()`. Inside `TransferEngineImpl::registerLocalMemory()`:

1. Create a `MemoryRegion` with the address, size, location and access flag.
2. Reserve the range in `registering_memory_regions_` after an overlap check.
3. Ask each installed transport to register the range.
4. On success, move the entry into `local_memory_regions_`.

The pending map stops another registration from claiming an overlapping range
in the meantime. Both maps belong to `TransferEngineImpl`.

TCP registration creates a `BufferDesc` and calls
`TransferMetadata::addLocalMemoryBuffer()`, which copies the current local
`SegmentDesc`, appends the buffer and swaps the stored description.
`TcpTransport` never touches the engine's pending map.

### One allocation, several descriptions

The allocation is the real bytes. Each structure below describes the same
range for a different part of Mooncake. None of them copies the payload.

| Structure | Key fields | Where it lives |
| --- | --- | --- |
| `MemoryRegion` | `addr`, `length`, `location`, `remote_accessible` | Owner's `TransferEngineImpl`: first `registering_memory_regions_`, then `local_memory_regions_`, keyed by base address. |
| `BufferDesc` | `name`, `addr`, `length` | An entry in `SegmentDesc::buffers`. |
| `SegmentDesc` | Engine name, protocol, buffers, TCP data endpoint | `TransferMetadata::segment_id_to_desc_map_`, in the owner or in a peer that fetched it. |
| Store `Segment` | UUID, name, base, size, protocol, host ID, `te_endpoint` | Owner's `Client::mounted_segments_` and the master's `MountedSegment`. |
| `MountedSegment` | `segment`, `status`, `buf_allocator` | Master's `SegmentManager::mounted_segments_`. |

On this CPU path, `RealClient::segment_ptrs_` keeps the allocation alive
through a smart pointer with a deleter. The maps describe the memory; this
holder owns it.

#### Inside `SegmentDesc`

The fields that matter for TCP:

```cpp
// Selected fields from TransferMetadata's nested types.
struct BufferDesc {
    std::string name;
    uint64_t addr;
    uint64_t length;
};

struct SegmentDesc {
    std::string name;
    std::string protocol;
    std::vector<BufferDesc> buffers;
    std::string tcp_data_host;
    int tcp_data_port{0};
    int tcp_proto_version{1};
};
```

- `name` is the engine's handshake endpoint in P2P mode.
- `tcp_data_host` and `tcp_data_port` point at the separate data listener.
- `tcp_proto_version` is set to 2 by TCP installation in this revision; the
  default of 1 keeps older descriptions working.
- `buffers` lists registered ranges reachable through this engine. A
  `BufferDesc` covers a whole region, such as the 64 MiB pool, not one object.
  TCP fills its `name` with the local engine name.

One `SegmentDesc` can hold several buffers: several mounted pools, and also a
registered staging buffer that is *not* Store capacity. So counting `buffers`
is not the same as counting Store segments.

#### How the local description changes

During TCP installation, `allocateLocalSegmentID()` creates the local
description and calls `TransferMetadata::addLocalSegment()`:

```text
segment_id_to_desc_map_[LOCAL_SEGMENT_ID] → shared_ptr<SegmentDesc>
segment_name_to_id_map_[engine_name]      → LOCAL_SEGMENT_ID
```

`LOCAL_SEGMENT_ID` is 0. When the pool is registered, `addLocalMemoryBuffer()`
makes a new `SegmentDesc`, copies the old one, appends the `BufferDesc` and
swaps the map's pointer under the metadata lock. Readers holding the old
snapshot are not affected.

The engine commits the `MemoryRegion` after transport registration succeeds.
The `MemoryRegion` map and `SegmentDesc::buffers` are separate records updated
by the same call path.

Sources: [data structure declarations](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/include/transfer_metadata.h)
and [`TransferMetadata::addLocalMemoryBuffer()`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transfer_metadata.cpp).

### Build the Store record and call the master

After registration, `Client` builds a `Segment`:

| Field | Value in our example |
| --- | --- |
| `id` | A new UUID generated by the owner's `Client`, not by the master. |
| `name` | Logical client name: `127.0.0.1:12345`. |
| `base` | The pool's address in the owner process. |
| `size` | 64 MiB. |
| `protocol` | `tcp`. |
| `host_id` | Host identity used for placement; separate from client and segment UUIDs. |
| `te_endpoint` | The owner's P2P handshake endpoint. Peers use it to find the TCP data endpoint. |

`MasterClient::MountSegment(segment)` adds its `client_id_` to the request. A
client can mount several segments, so the two UUIDs answer different
questions: **who** owns the capacity, and **which** pool is being mounted.

```text
Owner process                         Master process
MasterClient::MountSegment
  └─ RPC: Segment + client UUID ─────> WrappedMasterService::MountSegment
                                       └─ MasterService::MountSegment
```

The reply is just success or an error. No pool or object is created on the
reply path, and P2P handshakes are separate from this RPC: the mount only gives
the master the endpoint to put into later replica descriptors.

Sources: [`Client::MountSegmentAndGetId`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/client_service.cpp),
[`MasterClient::MountSegment`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/master_client.cpp),
[`WrappedMasterService::MountSegment`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/rpc_service.cpp),
[`Segment`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/include/types.h).

## 8. The master records the segment

`WrappedMasterService::MountSegment()` calls `MasterService::MountSegment()`,
which gets a `ScopedSegmentAccess` from `segment_manager_`. That object is a
lock guard plus access helper, not a second manager.

While holding it, the master puts the **client UUID** into
`client_ping_queue_`, which starts liveness tracking. This happens before the
mount completes: if the queue is full, the mount fails rather than leaving new
capacity untracked.

`ScopedSegmentAccess::MountSegment()` then validates the base, size and UUID.
For a new mount it creates the allocator, attaches usage tracking and inserts
the records. If the UUID is already mounted with status `OK`, the outer
service treats that as success and does not create a second allocator.

### Where the segment is recorded

[![Where a mounted segment is recorded: the master keeps MountedSegment, allocator_manager_ and other indexes pointing at one OffsetBufferAllocator; the owner keeps the real pool and a simple Segment record.](assets/segment-mount-state.svg)](assets/segment-mount-state.svg)

The main master-side record:

```cpp
// In SegmentManager. UUID is the Store segment ID.
std::unordered_map<UUID, MountedSegment, boost::hash<UUID>>
    mounted_segments_;

struct MountedSegment {
    Segment segment;
    SegmentStatus status;
    std::shared_ptr<BufferAllocatorBase> buf_allocator;
};
```

The new `MountedSegment` holds the `Segment`, status `SegmentStatus::OK` and
the allocator. `OK` means "available for allocation". It is a segment status,
not a replica status like `PROCESSING` or `COMPLETE`.

Other indexes find the same capacity in other ways:

| `SegmentManager` member | Lookup | Used for |
| --- | --- | --- |
| `mounted_segments_` | Segment UUID → `MountedSegment` | The full record, status and allocator. |
| `client_segments_` | Client UUID → segment UUIDs | An owner's segments, for cleanup and liveness. |
| `client_by_name_` | Segment name → client UUID | The client behind a logical name. |
| `segment_id_by_name_` | Segment name → segment UUID | Name lookup. Holds **one** ID, not an owner's full list. |
| `segments_by_host_` | Host ID → name → segment UUIDs | Allocatable segments per host. Added when `host_id` is set. |
| `allocator_manager_` | Segment name → allocators | Allocators of `OK` segments, for the allocation strategy. |

Inside `AllocatorManager`, `allocators_` holds those vectors and `names_` the
available names. A vector is needed because one logical name can have several
pools; the UUID maps tell them apart. `segment_id_by_name_` is overwritten on
each mount, so do not treat it as the full list.

`MountedSegment::buf_allocator` and the allocator-manager entry are the
**same object**, not two free-space records.

### Why the master needs an allocator

The owner allocated the **whole pool**. The master still has to split it
between future objects without giving the same bytes to two of them. For this
configuration, mounting creates:

```text
OffsetBufferAllocator(name, base, size, te_endpoint)
  └─ OffsetAllocator: free blocks, size bins, and allocation handles
```

`OffsetBufferAllocator` keeps the segment's identity, base, capacity and
endpoint. Its inner `OffsetAllocator` tracks which ranges are free or reserved.
This is bookkeeping only: the master allocates no 64 MiB payload and never
dereferences the owner's address.

With the pool at the example address `0x70000000`:

| Moment | Owner memory | Master's allocator |
| --- | --- | --- |
| Before mount | The 64 MiB allocation exists. | No allocator yet. |
| After mount | Unchanged. | Pool available. No key created. |
| A 4096-byte Put | Bytes are written into the chosen range. | Reserves a range, returns its address in a replica descriptor. |
| Object reclaimed | The pool still exists. | Frees the range; neighbouring free blocks can merge. |

If the allocator chooses offset `0x2000`, the Put caller receives destination
`0x70002000` plus the owner's endpoint, and its Transfer Engine sends the
bytes there. (Sizes may be rounded internally; the example does not show the
allocator's size classes.)

> **Two levels of choice:** the **allocation strategy picks a segment**; the
> **segment's allocator picks a range inside it**. `AllocatorManager` only
> lists the candidate allocators.

This allocator is unrelated to the owner's `ClientBufferAllocator`, which
manages local staging memory. Our owner has zero staging space, yet the master
still creates an allocator for its 64 MiB global segment. The
[offset allocator source](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/offset_allocator.cpp)
contains the free-bin search, block splitting and merging.

### Both sides finish the mount

The master updates capacity accounting, the client-to-host information and
the effective tenant quotas, then returns success. Only then does the owner's
`Client` record the mount:

```cpp
// In Client, not SegmentManager. The value is Segment, not MountedSegment.
std::unordered_map<UUID, Segment, boost::hash<UUID>> mounted_segments_;
// After a successful master RPC:
mounted_segments_[segment.id] = segment;
```

This owner-side map is used for overlap checks, unmounting and remounting. It
holds no allocation state.

> **Debugger tip:** both `Client` and `SegmentManager` have a member called
> `mounted_segments_`, with different value types. Check the enclosing class.

Finally, `EnsureStorageControlPlaneStarted()` starts two threads, once:
**heartbeats** tell the master the owner is alive, and **task polling** fetches
work such as replica copies or moves. Both loop every second on the normal
path, and they can run while later mounts proceed.

### How the descriptions reach the master and another client

Three processes are involved. "Remote metadata" can mean the master's Store
records or another client's Transfer Engine cache, and they get there in
different ways:

[![Who learns about the owner's memory: 1 MountSegment sends a Segment to the master; 2 the PutStart reply gives a requester one 4096-byte range; 3 the requester fetches the owner's SegmentDesc over P2P; 4 a TCP WRITE moves the bytes.](assets/owner-memory-distribution.svg)](assets/owner-memory-distribution.svg)

**1. Mounting sends Store metadata to the master.** `MasterClient::MountSegment()`
sends a serialized `Segment` and the owner's client UUID. It does not send
`SegmentDesc`, copy the registration maps or broadcast anything to other
clients.

**2. A Put caller gets one range.** After choosing space, the master returns a
replica descriptor with an `AllocatedBuffer::Descriptor`:

```cpp
struct Descriptor {
    uint64_t size_;
    uintptr_t buffer_address_;
    std::string protocol_;
    std::string transport_endpoint_;
};
```

The pool may cover 64 MiB from `0x70000000`, while this descriptor names only
4096 bytes at `0x70002000`. `transport_endpoint_` says which owner's engine to
open.

**3. The caller fetches the owner's description on demand.**
`TransferSubmitter::submitTransferEngineOperation()` calls
`engine_.openSegment(handle.transport_endpoint_)`. On a cache miss this reaches
`TransferMetadata::getSegmentID()`, then `getSegmentDescInternal()` and
`SocketHandShakePlugin::exchangeMetadata()`. The owner answers in
`TransferMetadata::receivePeerMetadata()` by encoding its local `SegmentDesc`
(ID 0). The caller decodes the reply into a **new local `SegmentDesc`**: no
pointer is shared across the network. It stores it under a caller-local ID:

```text
Caller process — example remote ID 1:
segment_name_to_id_map_[owner_endpoint] → 1
segment_id_to_desc_map_[1]             → owner's decoded SegmentDesc
```

The ID depends on the caller's history. The owner's local ID 0, the caller's
remote ID and the Store segment UUID are three different identifiers. The
caller does not add the remote region to its own `local_memory_regions_` or
`mounted_segments_`: it caches a description of someone else's memory.

> **Note:** the request also carries the caller's own description, but in
> this revision the owner's `receivePeerMetadata()` does not cache it. One
> exchange does not fill both peers' caches.

**4. The bytes move.** With the description cached, TCP knows the data
endpoint, and the allocation descriptor supplies the exact address and size.
Registering, mounting and fetching metadata never move object bytes; the
later WRITE does.

| Where | Class | What it holds |
| --- | --- | --- |
| Owner allocation | `RealClient` | The real memory and its lifetime holder. |
| Owner registration | `TransferEngineImpl` | Committed `MemoryRegion`, keyed by base address. |
| Owner engine metadata | `TransferMetadata` | Local `SegmentDesc` (ID 0) with the `BufferDesc`. |
| Owner Store state | `Client` | Store `Segment`, keyed by UUID after a successful mount. |
| Master | `SegmentManager` | `MountedSegment`, status, allocator and indexes. |
| Requesting peer | its own `TransferMetadata` | A decoded owner `SegmentDesc` under a peer-local ID. |

Cached descriptions are snapshots: registering another owner buffer does not
push updates into every peer's cache.

Sources: [`getSegmentID()` and `receivePeerMetadata()`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-transfer-engine/src/transfer_metadata.cpp),
[`AllocatedBuffer::Descriptor`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/include/allocator.h),
[`MasterService::MountSegment`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/master_service.cpp),
[`ScopedSegmentAccess::MountSegment`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/segment.cpp),
[`SegmentManager` and `MountedSegment`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/include/segment.h),
[`AllocatorManager`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/include/allocation_strategy.h),
[`OffsetBufferAllocator`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/allocator.cpp),
[`Client::mounted_segments_`](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/include/client_service.h).

## 9. Finish setup and start the client RPC server

The standalone program starts its IPC (inter-process communication) service
for local dummy clients. Both listeners are already running.

Only after setup returns does `main()` start the dummy-client monitor, build
the real-client RPC server, register its handlers and listen on `50052`. That
step comes after mounting, not before. See `main` and
`RegisterClientRpcService` in
[real_client_main.cpp](https://github.com/kvcache-ai/Mooncake/blob/719735896c86b56fabec6cf3e825fb2ea640597a/mooncake-store/src/real_client_main.cpp).

| Address or port | Purpose |
|---|---|
| `127.0.0.1:50051` | Master RPC |
| `127.0.0.1:12345` | Logical client name given to setup |
| Selected handshake port (H) | Peer metadata and handshakes |
| Selected TCP data port (D) | Object bytes |
| `127.0.0.1:50052` | Standalone real-client RPC service |

Read H and D from the startup logs; this revision picks them automatically.
(The author's debug checkout adds `MC_TE_HANDSHAKE_PORT`, `MC_TCP_DATA_PORT`
and `mc-*` thread names locally. They are not upstream features.)

## 10. Failures and breakpoints

Registration and mounting are separate steps, not one transaction:

- If a transport registration fails, the engine unregisters the transports it
  tried and releases the pending range.
- If the master mount RPC fails, the method returns an error and records no
  local mount, but it does **not** undo the earlier engine registration.

Normal cleanup runs through `RealClient::tearDownAll_internal()` and
destructors: services stop, the local buffer is unregistered, resources and
allocations are freed, and `Client` stops its control threads and tries to
unmount its segments. When an owner dies unexpectedly, the master's liveness
tracking cleans up later, so a failed startup does not prove every remote
record is already gone.

Inspect one boundary at a time with these breakpoints:

| Breakpoint | What to inspect |
|---|---|
| `RealClient::setup_internal` | Host, protocol, global size, local size |
| `MasterClient::Connect` | Master address and returned version |
| `TransferEngineImpl::init` | Logical name and handshake endpoint |
| `TcpTransport::install` | Data port and local segment description |
| `Client::MountSegmentAndGetId` | Pool address, size, Store UUID |
| `TransferEngineImpl::registerLocalMemory` | Pending and committed memory maps |
| `TransferMetadata::addLocalMemoryBuffer` | Buffer address and description list |
| `MasterClient::MountSegment` | Outgoing `Segment`, owner UUID, RPC result |
| `WrappedMasterService::MountSegment` | The same arguments, on the master |
| `MasterService::MountSegment` | Segment received by the master |
| `ScopedSegmentAccess::MountSegment` | Allocator and mounted-segment record |
| `OffsetBufferAllocator::OffsetBufferAllocator` | Owner base address, capacity, new bookkeeping |
| `Client::EnsureStorageControlPlaneStarted` | First start of heartbeat and task polling |
| `RegisterClientRpcService` | Final handler registration |

Keep the owner running while you inspect master-side addresses: a pointer
value stored on the master still refers to memory in the owner. The next
article follows a Put into this pool.
