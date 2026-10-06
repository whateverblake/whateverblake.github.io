"""Generate English illustrations for the migrated Jianshu articles.

Uses only the Python standard library. Source excerpts are read from the
pinned historical source cache; diagrams are explanatory reconstructions,
not debugger screenshots. The website serves the generated SVGs directly.
"""
from pathlib import Path
from html import escape
import json,re,textwrap
REPO=Path(__file__).resolve().parents[1]
CACHE=Path('/Users/blake/Downloads/jianshu_blog/source-references')
VERSIONS={
 'zk':('ZooKeeper 3.6.2','zookeeper-3.6.2','apache/zookeeper','803c7f1a12f85978cb049af5e4ef23bd8b688715'),
 'netty':('Netty 4.1.53.Final','netty-4.1.53.Final','netty/netty','d4a0050ef33cab2542a80e11489a4977a63859f8'),
 'legacy':('Legacy: Netty 4.1.50.Final','netty-4.1.50.Final','netty/netty','8c5b72aaf02e7f349a9972dd9179b449b5a6067b'),
 'jdk':('OpenJDK 8u272-b10','jdk8u272-b10','openjdk/jdk8u','c3b5603e949d6272d777ef57952833672a97b4e3'),
}
Z='zookeeper-server/src/main/java/org/apache/zookeeper/'
N='common/src/main/java/io/netty/'
B='buffer/src/main/java/io/netty/buffer/'
T='transport/src/main/java/io/netty/'
J='jdk/src/share/classes/'
INK='#182a42'; MUTED='#54677d'; BLUE='#2161ad'; TEAL='#087e78'; PURPLE='#7251aa'; ORANGE='#ad5b18'
SPECS={}
def spec(topic,slug,index,title,kind,data,version,path,note=''):
 SPECS[(topic,slug,index)]=dict(title=title,kind=kind,data=data,version=version,path=path,note=note)
def flow(topic,slug,index,title,steps,version,path,note=''):
 spec(topic,slug,index,title,'flow',steps,version,path,note)
def fields(topic,slug,index,title,rows,version,path,note=''):
 spec(topic,slug,index,title,'fields',rows,version,path,note)
def code(topic,slug,index,title,version,path,needle,count=16,note=''):
 spec(topic,slug,index,title,'code',{'needle':needle,'count':count},version,path,note)
# ZooKeeper setup: reproducible instructions instead of missing IDE captures.
flow('zookeeper','debugging-environment',1,'Get the historical ZooKeeper source',[
 ('Repository','https://github.com/apache/zookeeper'),
 ('Release','Check out release-3.6.2; available in October 2020.'),
 ('Source modules','zookeeper-server contains server/client Java; zookeeper-jute generates protocol classes.')], 'zk','pom.xml','Recreated setup panel; no IDE session is claimed.')
flow('zookeeper','debugging-environment',2,'Clone and import the Maven project',[
 ('Clone','git clone https://github.com/apache/zookeeper.git'),
 ('Select the release','git checkout --detach release-3.6.2'),
 ('IntelliJ IDEA','Open the root pom.xml as a Maven project; select a compatible JDK.')], 'zk','pom.xml','Equivalent reproducible steps replace the missing import dialog.')
flow('zookeeper','debugging-environment',3,'Confirm the version before debugging',[
 ('Git reference','git describe --tags --exact-match'),
 ('Expected release tag','release-3.6.2'),
 ('Immutable revision','803c7f1a12f85978cb049af5e4ef23bd8b688715')], 'zk','pom.xml','Version selection is shown as commands rather than an invented IDE screenshot.')
flow('zookeeper','debugging-environment',4,'Generate protocol classes and build',[
 ('From the source root','mvn -DskipTests package'),
 ('Maven reactor','Build zookeeper-jute and its generated protocol records before zookeeper-server.'),
 ('IDE synchronization','Reload Maven; use the module dependency classpath rather than adding individual jars.')], 'zk','pom.xml','Build instructions derived from the release Maven project.')
flow('zookeeper','debugging-environment',5,'Configure a standalone debug launch',[
 ('Main class','org.apache.zookeeper.server.ZooKeeperServerMain'),
 ('Program argument','Absolute path to your local zoo.cfg'),
 ('Working directory','Use a local dataDir and a free clientPort from zoo.cfg.'),
 ('Breakpoints','initializeAndRun → runFromConfig → server startup')], 'zk',Z+'server/ZooKeeperServerMain.java','This is a run-configuration guide, not a capture from a debugging run.')
fields('zookeeper','standalone-server-startup',1,'Default session timeout bounds',[
 ('tickTime','Base heartbeat interval; example: 2000 ms'),
 ('minSessionTimeout','Defaults to 2 × tickTime → 4000 ms'),
 ('maxSessionTimeout','Defaults to 20 × tickTime → 40000 ms'),
 ('Explicit configuration','The defaults apply only when the value is -1.')], 'zk',Z+'server/ZooKeeperServer.java','The interval is negotiated with the client; examples are illustrative.')
fields('zookeeper','standalone-server-startup',2,'ServerConfig: configuration fields',[
 ('clientPortAddress','InetSocketAddress — non-TLS client listener'),
 ('secureClientPortAddress','InetSocketAddress — optional TLS listener'),
 ('dataDir / dataLogDir','File — snapshot and transaction log directories'),
 ('tickTime','int — base timing interval'),
 ('minSessionTimeout / maxSessionTimeout','int — configured bounds; -1 selects defaults'),
 ('maxClientCnxns / listenBacklog','int — connection and accept-queue limits')], 'zk',Z+'server/ServerConfig.java','Selected declarations reconstructed from source.')
flow('zookeeper','standalone-server-startup',3,'Accept and dispatch NIO work',[
 ('AcceptThread.doAccept','Accept SocketChannel and enqueue it for a selected SelectorThread.'),
 ('SelectorThread.processAcceptedConnections','Register the channel; create NIOServerCnxn; attach it to its SelectionKey.'),
 ('SelectorThread.handleIO','Disable selection while one IOWorkRequest is being handled.'),
 ('WorkerService / IOWorkRequest.doWork','Perform NIOServerCnxn.doIO on the worker pool.'),
 ('updateQueue','Re-register the connection’s current read/write interests.')], 'zk',Z+'server/NIOServerCnxnFactory.java','English redraw of the original I/O model. Each connection avoids concurrent I/O tasks.')
fields('zookeeper','client-startup',1,'ConnectStringParser: split endpoints and path',[
 ('Input example','host1:2181,host2:2181/application'),
 ('chrootPath','String — /application in this example'),
 ('serverAddresses','ArrayList<InetSocketAddress> — unresolved endpoint addresses'),
 ('Validation','Validate a nonempty chroot; default client port is 2181.')], 'zk',Z+'client/ConnectStringParser.java')
fields('zookeeper','client-startup',2,'StaticHostProvider: select a server',[
 ('serverAddresses','List<InetSocketAddress> — candidate endpoints'),
 ('currentIndex','int — endpoint being attempted'),
 ('lastIndex','int — last connected endpoint'),
 ('next(spinDelay)','Cycle through endpoints; resolve the chosen address.'),
 ('onConnected()','Record the successful currentIndex as lastIndex.')], 'zk',Z+'client/StaticHostProvider.java','Other fields support dynamic reconfiguration; selected fields explain the article’s basic path.')
fields('zookeeper','client-startup',3,'ClientCnxn: transport, requests and events',[
 ('SendThread','Owns connection and request/reply I/O'),
 ('EventThread','Delivers callbacks and watcher events'),
 ('outgoingQueue','LinkedBlockingDeque<Packet> — waiting to send'),
 ('pendingQueue','Queue<Packet> — sent, awaiting replies'),
 ('sessionId / sessionTimeout','Session identity and timing'),
 ('hostProvider / watcher','Endpoint selection and client watch registry')], 'zk',Z+'ClientCnxn.java')
code('zookeeper','client-startup',4,'Packet: request and response state','zk',Z+'ClientCnxn.java',r'^    static class Packet \{',27,'Selected original declarations; blank lines omitted. No runtime values are invented.')
flow('zookeeper','client-startup',5,'Establish the socket, then the session',[
 ('ZooKeeper constructor','Create ClientCnxn and start SendThread / EventThread.'),
 ('SendThread.startConnect','Select an endpoint; connect the client SocketChannel.'),
 ('primeConnection','Queue ConnectRequest and register read/write interests.'),
 ('Server receives ConnectRequest','Negotiate timeout; create or reopen a session.'),
 ('ConnectResponse','Client reads the session ID, password and timeout.'),
 ('Connected event','SendThread updates state; EventThread delivers the watcher event.')], 'zk',Z+'ClientCnxn.java')
fields('zookeeper','expiry-queue',1,'Group expiration times into interval buckets',[
 ('Example interval','1000 ms; these are illustrative times, not a runtime dump.'),
 ('connection A','Deadline 2100 ms → bucket 3000 ms'),
 ('connection B','Deadline 2900 ms → bucket 3000 ms'),
 ('connection C','Deadline 3000 ms → bucket 4000 ms'),
 ('roundToNextInterval(time)','(time / expirationInterval + 1) × expirationInterval'),
 ('expiryMap','Each bucket maps to a set of objects to expire.')], 'zk',Z+'server/ExpiryQueue.java','The formula rounds strictly to the next interval, even when the deadline is already aligned.')
flow('zookeeper','node-creation',1,'Queue a create request on the client',[
 ('ZooKeeper.create','Build RequestHeader, CreateRequest and the expected response record.'),
 ('ClientCnxn.submitRequest','Pass the records to queuePacket and wait for completion.'),
 ('queuePacket','Create a Packet and put it in outgoingQueue.'),
 ('SendThread / ClientCnxnSocketNIO','Assign xid, serialize to ByteBuffer and write the socket.'),
 ('pendingQueue','Correlate the server’s reply with the waiting request.')], 'zk',Z+'ClientCnxn.java')
flow('zookeeper','node-creation',2,'Decode the request on the server',[
 ('SelectorThread.handleIO','Schedule an IOWorkRequest for the ready connection.'),
 ('NIOServerCnxn.doIO','Read the length prefix, then the message payload.'),
 ('ZooKeeperServer.processPacket','Deserialize RequestHeader; retain the body in the Request.'),
 ('RequestThrottler','Apply request admission before forwarding to the processor chain.')], 'zk',Z+'server/ZooKeeperServer.java')
flow('zookeeper','node-creation',3,'Standalone request processor chain',[
 ('RequestThrottler','Admission and request throttling'),
 ('PrepRequestProcessor','Validate the operation and build the transaction.'),
 ('SyncRequestProcessor','Append transaction records and flush the log.'),
 ('FinalRequestProcessor','Apply the transaction to the database; send the client reply.')], 'zk',Z+'server/ZooKeeperServer.java','This is the standalone path; quorum mode inserts additional processors.')
flow('zookeeper','watch-processing',1,'Register a persistent watch on the server',[
 ('Client addWatch request','An addWatch operation carries the path and watch mode.'),
 ('Server I/O and admission','processPacket → RequestThrottler → standalone processor chain'),
 ('FinalRequestProcessor','Dispatch OpCode.addWatch.'),
 ('DataTree.addWatch','Register the connection watcher with the selected watch managers.'),
 ('Later changes','Triggered events are sent on the connection and delivered by the client EventThread.')], 'zk',Z+'server/FinalRequestProcessor.java','The original article uses persistent addWatch. Ordinary read-operation watches also follow the shared request machinery.')
fields('zookeeper','data-recovery',1,'Transaction log and snapshot filenames',[
 ('log.100000001','Illustrative: log begins with zxid 0x100000001.'),
 ('log.100000080','Illustrative: a later transaction log segment.'),
 ('snapshot.10000007f','Illustrative: snapshot associated with zxid 0x10000007f.'),
 ('File suffix','Hexadecimal zxid; these names are examples, not captured output.'),
 ('Recovery','Restore a usable snapshot, then replay subsequent transaction records.')], 'zk',Z+'server/persistence/FileTxnSnapLog.java','The suffix does not mean a snapshot contains only zxids strictly smaller than it; snapshots are fuzzy.')
code('zookeeper','data-recovery',2,'Transaction header fields','zk','zookeeper-jute/src/main/resources/zookeeper.jute',r'    class TxnHeader \{',7,'The body record depends on the operation type. This replaces the missing parsed-log screenshot.')
fields('zookeeper','data-recovery',3,'What a snapshot stores for znodes',[
 ('ACL cache','Shared ACL definitions referenced by node records'),
 ('Path','A node’s full path in the data tree'),
 ('DataNode.data','byte[] — payload'),
 ('DataNode.acl','Long — ACL cache key'),
 ('DataNode.stat','StatPersisted — transaction IDs, times, versions and owner'),
 ('Recovery','DataTree.deserialize reconstructs nodes and parent-child relationships.')], 'zk',Z+'server/DataTree.java','A source-based schema replaces the missing parsed-snapshot screenshot; it is not a binary hex dump.')
fields('zookeeper','data-recovery',4,'What a snapshot stores for sessions',[
 ('Session count','Number of persisted sessions'),
 ('sessionId','long — session identifier'),
 ('timeout','int — session timeout in milliseconds'),
 ('sessionsWithTimeouts','Map<Long, Integer> reconstructed during deserialization'),
 ('Next section','After sessions, deserialize the data tree.')], 'zk',Z+'server/util/SerializeUtils.java','Field layout from serializeSnapshot / deserializeSnapshot; no session values are invented.')
fields('zookeeper','data-recovery',5,'DataTree: the in-memory data model',[
 ('nodes','NodeHashMap — full path → DataNode'),
 ('dataWatches / childWatches','IWatchManager — watch registrations'),
 ('ephemerals','Map<Long, HashSet<String>> — session → ephemeral paths'),
 ('aclCache','ReferenceCountedACLCache — shared ACL records'),
 ('lastProcessedZxid','Latest applied transaction ID')], 'zk',Z+'server/DataTree.java')
fields('zookeeper','data-recovery',6,'NodeHashMapImpl: nodes and digest accounting',[
 ('nodes','ConcurrentHashMap<String, DataNode>'),
 ('digestEnabled','boolean — whether to track the tree digest'),
 ('digestCalculator','DigestCalculator — calculate node contributions'),
 ('hash','AdHash — aggregate digest'),
 ('put / remove / preChange / postChange','Keep node storage and digest accounting consistent.')], 'zk',Z+'server/NodeHashMapImpl.java')
fields('zookeeper','data-recovery',7,'DataNode: persisted and derived state',[
 ('data','byte[] — znode payload'),
 ('acl','Long — shared ACL reference'),
 ('stat','StatPersisted — persistent metadata'),
 ('children','Set<String> — child names, not complete paths'),
 ('digest / digestCached','Cached node digest and validity flag')], 'zk',Z+'server/DataNode.java')
flow('zookeeper','leader-election',1,'Election votes cross thread and queue boundaries',[
 ('QuorumPeer','Produce a proposal; read Notification votes.'),
 ('FastLeaderElection.WorkerSender','Consume sendqueue<ToSend>; serialize a vote.'),
 ('QuorumCnxManager.SendWorker','Consume the peer’s queueSendMap entry; write the peer socket.'),
 ('QuorumCnxManager.RecvWorker','Read a peer socket; publish a Message to recvQueue.'),
 ('FastLeaderElection.WorkerReceiver','Decode Message; publish Notification to recvqueue.'),
 ('QuorumPeer.lookForLeader','Evaluate notifications and update or accept the proposal.')], 'zk',Z+'server/quorum/FastLeaderElection.java','The lower-case sendqueue/recvqueue belong to election; queueSendMap/recvQueue belong to QuorumCnxManager.')
flow('zookeeper','leader-election',2,'Fast leader election: propose, compare, converge',[
 ('Enter LOOKING','Increment logicalclock and initialize the proposal.'),
 ('sendNotifications','Broadcast the currently proposed leader.'),
 ('Read the next vote','Compare election epoch, peer epoch, zxid and server ID as appropriate.'),
 ('Update proposal when needed','Broadcast the better proposal and retain eligible received votes.'),
 ('Quorum decision','Check enough matching votes and the finalization conditions.'),
 ('Leave LOOKING','Become LEADING or FOLLOWING; return the agreed Vote.')], 'zk',Z+'server/quorum/FastLeaderElection.java')
fields('zookeeper','leader-election',3,'Peer connection topology for election',[
 ('Peer 1','SendWorker / RecvWorker pair for peers 2 and 3'),
 ('Peer 2','SendWorker / RecvWorker pair for peers 1 and 3'),
 ('Peer 3','SendWorker / RecvWorker pair for peers 1 and 2'),
 ('queueSendMap','Per-peer bounded send queues'),
 ('Duplicate connection resolution','The larger server ID is responsible for initiating the retained connection.'),
 ('Purpose','One retained socket per peer pair; each endpoint handles sending and receiving.')], 'zk',Z+'server/quorum/QuorumCnxManager.java')
flow('zookeeper','leader-follower-initialization',1,'Connect followers to the elected leader',[
 ('Leader.lead','Start LearnerCnxAcceptor.'),
 ('LearnerCnxAcceptorHandler','Accept follower sockets on the configured quorum addresses.'),
 ('LearnerHandler','Create a handler for each accepted learner connection.'),
 ('Follower.followLeader','Find the elected leader; connect through LeaderConnector.'),
 ('Follower ↔ LearnerHandler','Exchange protocol records on the established socket.')], 'zk',Z+'server/quorum/Leader.java')
flow('zookeeper','leader-follower-initialization',2,'Agree on the new epoch',[
 ('Follower → Leader: FOLLOWERINFO','Send acceptedEpoch, server ID and protocol information.'),
 ('Leader.getEpochToPropose','Wait for enough connecting followers; propose a new epoch.'),
 ('Leader → Follower: LEADERINFO','Send the proposed epoch.'),
 ('Follower → Leader: ACKEPOCH','Return the prior currentEpoch and last zxid in the acknowledgement.'),
 ('Leader.waitForEpochAck','Collect acknowledgements from a quorum before synchronization.')], 'zk',Z+'server/quorum/LearnerHandler.java','An epoch orders ensemble incarnations; ACKEPOCH also carries the follower’s prior state summary.')
flow('zookeeper','leader-follower-initialization',3,'Synchronize data, then begin serving',[
 ('Leader.syncFollower','Compare the follower’s zxid and the leader’s available history.'),
 ('DIFF / TRUNC / SNAP','Send missing committed proposals, trim divergent history, or send a snapshot.'),
 ('NEWLEADER','Follower persists synchronized state and acknowledges the new leader.'),
 ('Leader.waitForNewLeaderAck','Wait for a quorum to acknowledge the NEWLEADER record.'),
 ('UPTODATE','Signal that the learner can start normal request processing.'),
 ('BROADCAST','The active leader/follower ensemble processes client requests.')], 'zk',Z+'server/quorum/LearnerHandler.java')
# Netty thread, pipeline and adaptive reads.
flow('netty','thread-model',1,'Reactor roles in a Netty NIO server',[
 ('Boss NioEventLoop','Accept connections on NioServerSocketChannel.'),
 ('New NioSocketChannel','Wrap an accepted SocketChannel.'),
 ('Worker EventLoopGroup','Choose one NioEventLoop for the child channel.'),
 ('Assigned NioEventLoop','Handle that channel’s I/O and tasks; many channels may share the same loop.')], 'netty',T+'bootstrap/ServerBootstrap.java')
fields('netty','thread-model',2,'Three kinds of NioEventLoop work',[
 ('Selector I/O','Ready registered channel operations'),
 ('taskQueue','Immediate Runnable tasks submitted to this loop'),
 ('scheduledTaskQueue','Delayed and periodic tasks when their deadlines arrive'),
 ('One event-loop thread','Execute these categories while balancing I/O and task work.')], 'netty',T+'channel/nio/NioEventLoop.java')
code('netty','thread-model',3,'Wrap the executor with the current EventExecutor','netty',N+'util/concurrent/SingleThreadEventExecutor.java',r'        this.executor = ThreadExecutorMap.apply\(executor, this\);',1,'Actual constructor assignment from source; ThreadExecutorMap installs the executing EventExecutor context.')
fields('netty','pipeline',1,'Inbound and outbound traversal directions',[
 ('Inbound events','HEAD → inbound handler 1 → inbound handler 2 → TAIL'),
 ('Outbound operations','TAIL → outbound handler 2 → outbound handler 1 → HEAD'),
 ('Nodes','ChannelHandlerContext wraps each handler in the linked pipeline.'),
 ('Direction','An event finds the next context that supports that event and direction.')], 'netty',T+'channel/AbstractChannelHandlerContext.java')
flow('netty','pipeline',2,'Propagate an event across handler contexts',[
 ('Pipeline starts the event','fireChannelXXX delegates to the head context.'),
 ('Find the next context','findContextInbound / findContextOutbound follows the required direction.'),
 ('Invoke the handler','invokeChannelXXX calls handler.channelXXX(ctx, ...).'),
 ('Handler continues propagation','ctx.fireChannelXXX locates and invokes the next interested context.'),
 ('Repeat','Propagation continues only when the handler forwards the event.')], 'netty',T+'channel/AbstractChannelHandlerContext.java','XXX stands for an event such as Read or Registered; the source has concrete methods for each event.')
fields('netty','socket-read',1,'Adaptive receive buffer SIZE_TABLE',[
 ('Indices 0–30','16, 32, 48, …, 496: increments of 16'),
 ('Indices 31–52','512, 1024, 2048, …, 1073741824: powers of two'),
 ('Total entries','31 + 22 = 53'),
 ('HandleImpl','Select the next receive-buffer capacity from this table.'),
 ('Capacity changes','Increase promptly after a full read; decrease after repeated small reads.')], 'netty',T+'channel/AdaptiveRecvByteBufAllocator.java')
# Legacy allocator: original drawings match 4.1.50, not the redesigned October release.
L='legacy'
flow('netty','pooled-memory',1,'Legacy pooled-memory hierarchy',[
 ('PooledByteBufAllocator','Own heap and direct arenas; assign an arena to each thread cache.'),
 ('PoolArena','Manage chunk lists and subpage pools.'),
 ('PoolChunk','Default 16 MiB of memory; divide it into 2048 pages.'),
 ('Page','Default 8 KiB; allocate runs of pages or subdivide one page.'),
 ('PoolSubpage','Split a page into fixed-size allocation elements.')], L,B+'PoolArena.java','This preserves the original allocator model. Netty 4.1.53 uses SizeClasses and a different run allocator.')
fields('netty','pooled-memory',2,'Threads share arenas, keep their own caches',[
 ('Thread 1 → cache 1','Assigned to arena A'),
 ('Thread 2 → cache 2','May also use arena A'),
 ('Thread 3 → cache 3','Assigned to arena B'),
 ('Arena selection','PoolThreadLocalCache selects a least-used arena.'),
 ('Thread-local cache','Reuse memory regions locally before asking the shared arena.')], L,B+'PooledByteBufAllocator.java')
fields('netty','pooled-memory',3,'Subpage pools are circular doubly linked lists',[
 ('Head','Sentinel PoolSubpage; initialized with prev = next = head'),
 ('head.next','First subpage with available allocation elements'),
 ('PoolSubpage.prev / next','Link each available subpage into its size-specific pool'),
 ('Empty pool','Only the head sentinel remains.'),
 ('Pool choice','Each element-size class has its own head.')], L,B+'PoolSubpage.java')
fields('netty','pooled-memory',4,'A default legacy chunk contains 2048 pages',[
 ('Chunk capacity','16 MiB = 16777216 bytes'),
 ('Page capacity','8 KiB = 8192 bytes'),
 ('Page 0','Byte offsets 0–8191'),
 ('Page 1','Byte offsets 8192–16383'),
 ('Page 2047','Byte offsets 16769024–16777215'),
 ('Memory addresses','Add the page offset to the backing memory’s base address.')], L,B+'PoolChunk.java')
fields('netty','pooled-memory',5,'Pooled versus oversized direct allocation',[
 ('Normal / subpage request','Allocate from a pooled chunk and its pages/subpages.'),
 ('Request larger than chunkSize','Allocate a separate unpooled chunk for that request.'),
 ('Direct memory','The arena obtains the backing direct buffer.'),
 ('Returned ByteBuf','A view of the allocated region with offset and capacity.')], L,B+'PoolArena.java','Pooling and thread-cache reuse are different layers; not every request allocates new backing memory.')
fields('netty','pooled-memory',6,'Legacy tinySubpagePools',[
 ('Normalized element sizes','16, 32, 48, …, 496 bytes'),
 ('Array length','32; slot 0 is unused for positive allocations'),
 ('Index','normalizedCapacity >>> 4'),
 ('Each array slot','Head of the corresponding PoolSubpage linked list'),
 ('Normalization example','An 18-byte request becomes a 32-byte element.')], L,B+'PoolArena.java')
fields('netty','pooled-memory',7,'Legacy smallSubpagePools',[
 ('Normalized element sizes','512, 1024, 2048, 4096 bytes'),
 ('Array length','4 for the default 8 KiB page size'),
 ('Each array slot','Head of the subpage pool for that element size'),
 ('Normalization example','A 513-byte request becomes a 1024-byte element.'),
 ('Page-sized and larger','Use the normal page-run allocation path.')], L,B+'PoolArena.java')
fields('netty','pooled-memory',8,'PoolChunkList: lists of chunks grouped by usage',[
 ('List traversal','qInit → q000 → q025 → q050 → q075 → q100'),
 ('Each list','Own a linked chain of PoolChunk objects.'),
 ('Allocation','Can move a chunk toward lists with higher usage.'),
 ('Freeing','Can move a chunk toward lists with lower usage.'),
 ('Overlapping intervals','Reduce unnecessary movement between neighboring lists.')], L,B+'PoolChunkList.java')
code('netty','pooled-memory',9,'Legacy chunk-list category initialization',L,B+'PoolArena.java',r'        q100 = new PoolChunkList',6,'Actual source declarations replace the missing code screenshot. Constructor arguments are minUsage / maxUsage percentages.')
fields('netty','pooled-memory',10,'Legacy chunk migration thresholds',[
 ('qInit','minUsage = Integer.MIN_VALUE; maxUsage = 25'),
 ('q000','minUsage = 1; maxUsage = 50'),
 ('q025','minUsage = 25; maxUsage = 75'),
 ('q050','minUsage = 50; maxUsage = 100'),
 ('q075','minUsage = 75; maxUsage = 100'),
 ('q100','minUsage = 100; maxUsage = Integer.MAX_VALUE'),
 ('Threshold calculation','Use the source’s percentage formulas, rounding and integer conversion.')], L,B+'PoolChunkList.java','The original approximate “4.16M” values depend on interpreting MiB versus decimal MB; percentages are the authoritative inputs.')
flow('netty','pooled-memory',11,'Legacy pooled direct allocation entry path',[
 ('PooledByteBufAllocator.buffer','Select direct or heap allocation according to the allocator setting.'),
 ('directBuffer → newDirectBuffer','Obtain the current thread’s PoolThreadCache.'),
 ('PoolArena.allocate','Normalize capacity; try the thread cache and size-class pools.'),
 ('PoolChunk.allocate','Allocate a page run or a subpage element.'),
 ('PooledByteBuf.init','Bind the buffer to its backing memory, handle and offset.')], L,B+'PoolArena.java')
spec('netty','pooled-memory',12,'Legacy page-run buddy tree','tree',[],L,B+'PoolChunk.java','A 16 MiB root divides to 2048 leaves of 8 KiB. This is the pre-redesign allocator.')
spec('netty','pooled-memory',13,'Legacy subpage handle bit layout','bits',[],L,B+'PoolSubpage.java','handle = 0x4000000000000000L | ((long) bitmapIdx << 32) | memoryMapIdx; marker is bit 62, not 2^64.')
# Recycler: selected declarations and English flow redraws.
flow('netty','recycler',1,'Recycler ownership and cross-thread queues',[
 ('Recycler → thread-local Stack','Own the reusable objects for one thread.'),
 ('Stack.elements','Array of DefaultHandle values ready to reuse.'),
 ('Same-thread recycle','Push a handle directly onto its owning stack.'),
 ('Cross-thread recycle','Publish the handle through a WeakOrderQueue for the owning stack.'),
 ('WeakOrderQueue → Head → Link','Linked batches transfer handles back to Stack.elements.')], 'netty',N+'util/Recycler.java')
code('netty','recycler',2,'DefaultHandle: object and ownership state','netty',N+'util/Recycler.java',r'    private static final class DefaultHandle',13,'Actual declarations replace the missing IntelliJ class screenshot.')
code('netty','recycler',3,'Head: capacity accounting and the first Link','netty',N+'util/Recycler.java',r'        private static final class Head',8,'The head deliberately does not hold a reference to the Stack or WeakOrderQueue.')
code('netty','recycler',4,'Link: a batch of recycled handles','netty',N+'util/Recycler.java',r'        static final class Link extends AtomicInteger',6,'AtomicInteger supplies the writer index; readIndex is the consumer’s position.')
flow('netty','recycler',5,'Recycle an object back through its handle',[
 ('Object.recycle','Application wrapper calls handle.recycle(this).'),
 ('DefaultHandle.recycle','Validate the object and ownership state.'),
 ('Stack.push','Choose the same-thread or cross-thread return path.')], 'netty',N+'util/Recycler.java')
fields('netty','recycler',6,'Stack.push chooses the return path',[
 ('Condition','stack.threadRef.get() == Thread.currentThread()'),
 ('True → pushNow','Return the handle directly to the owning stack.'),
 ('False → pushLater','Return through the recycling thread’s WeakOrderQueue.'),
 ('Purpose','Avoid pushing into another thread’s elements array directly.')], 'netty',N+'util/Recycler.java')
flow('netty','recycler',7,'Get an object from Recycler',[
 ('ObjectPool.get','Delegate to the underlying Recycler.'),
 ('Recycler.get','Find the current thread’s Stack and call pop.'),
 ('Stack.pop','Reuse a handle, scavenging cross-thread queues when required.'),
 ('Empty stack','Create a new handle and object via newObject.'),
 ('Result','Return handle.value to the caller.')], 'netty',N+'util/Recycler.java')
fields('netty','recycler',8,'Scavenging dead cross-thread queues',[
 ('Stack.head','Start of the WeakOrderQueue chain'),
 ('cursor / prev','Track progress while transferring handles back to the stack'),
 ('Dead producer thread','owner.get() == null; drain remaining handles when possible'),
 ('Unlinking','The original logic cannot unlink a queue without a predecessor.'),
 ('Version caveat','Queue management is implementation-specific; this diagram describes the pinned Recycler source.')], 'netty',N+'util/Recycler.java','Explanatory state labels replace runtime object addresses. A dead producer is not the same as an immediately collectible queue.')
# OpenJDK reference handling: original images were code/debugger captures.
code('netty','java-reference-processing',1,'Reference constructors select a queue','jdk',J+'java/lang/ref/Reference.java',r'    Reference\(T referent\) \{',10,'The referent is a specially handled reference field; registration with a queue is optional.')
fields('netty','java-reference-processing',2,'Registered queue versus no queue',[
 ('new WeakReference(object)','Constructor uses no application ReferenceQueue.'),
 ('new WeakReference(object, queue)','Associate this reference with the supplied queue.'),
 ('ReferenceQueue.NULL','Sentinel used when the constructor’s queue is null.'),
 ('ReferenceQueue.ENQUEUED','Sentinel after successful enqueueing.'),
 ('Application','poll or remove reads reference objects, not their former referents.')], 'jdk',J+'java/lang/ref/Reference.java')
code('netty','java-reference-processing',3,'Reference: queue and VM-managed links','jdk',J+'java/lang/ref/Reference.java',r'    private T referent;',36,'Selected source fields replace the missing class/debugger capture. VM links require special treatment.')
flow('netty','java-reference-processing',4,'Move pending references to their queues',[
 ('Garbage collector','Discover eligible references; update VM-managed reference state.'),
 ('Reference.pending','Head of the VM’s pending reference list.'),
 ('Reference Handler thread','Detach a reference while holding Reference.lock.'),
 ('Special Cleaner path','Run Cleaner.clean for a Cleaner reference.'),
 ('Ordinary reference path','If its queue is not NULL, enqueue the Reference object.'),
 ('Application queue','Observe the enqueued reference through ReferenceQueue.poll / remove.')], 'jdk',J+'java/lang/ref/Reference.java','This describes OpenJDK 8. It is not a claim that System.gc always performs a collection or immediate enqueueing.')
code('netty','java-reference-processing',5,'Reference Handler detects Cleaner references','jdk',J+'java/lang/ref/Reference.java',r'                c = r instanceof Cleaner',9,'Actual source around the Cleaner type check; no debugger values are shown.')
code('netty','java-reference-processing',6,'Ordinary pending references are enqueued','jdk',J+'java/lang/ref/Reference.java',r'        ReferenceQueue<\? super Object> q = r.queue;',6,'Source-level replacement for the original queue-processing screenshot.')
fields('netty','java-reference-processing',7,'Use a conditional breakpoint to narrow observations',[
 ('Breakpoint','Reference.tryHandlePending at the pending-list handling path'),
 ('Example condition','pending instanceof WeakReference'),
 ('Exclude weak-map traffic','&& !(pending instanceof java.util.WeakHashMap.Entry)'),
 ('IDE context','Some conditions may need evaluation from the declaring source scope.'),
 ('Observation','Inspect the reference and queue; runtime timing and values vary.'),
 ('Do not infer','A requested GC or breakpoint alone does not guarantee object reclamation.')], 'jdk',J+'java/lang/ref/Reference.java','Recreated debugging instructions, not a screenshot from a reproduced IntelliJ session.')
# Java zero-copy: abstract data paths, with copy mechanisms labeled correctly.
flow('netty','java-zero-copy',1,'Ordinary file-to-socket copy path',[
 ('Disk → page cache','DMA transfers file bytes into kernel memory.'),
 ('Page cache → user buffer','CPU copies bytes for read / FileInputStream.'),
 ('User buffer → socket buffer','CPU copies bytes for socket write.'),
 ('Socket buffer → network interface','DMA transfers outgoing bytes to the device.')], 'jdk',J+'sun/nio/ch/FileChannelImpl.java','Conceptual Linux data path for the Java example; the pinned FileChannel implementation supplies the Java entry points.')
flow('netty','java-zero-copy',2,'sendfile avoids the user-buffer round trip',[
 ('Disk → kernel page cache','Read file pages as needed.'),
 ('Page cache → network stack','sendfile submits file data without a user-space buffer copy.'),
 ('Network device','DMA transmits bytes; kernel copy behavior depends on OS/device support.'),
 ('FileChannel.transferTo','May use sendfile when the platform and channel pair support it.')], 'jdk',J+'sun/nio/ch/FileChannelImpl.java','Conceptual path; “zero-copy” does not mean that every platform performs zero CPU copies.')
flow('netty','java-zero-copy',3,'Ordinary reads copy data into a user array',[
 ('Storage → kernel page cache','Populate cached file pages.'),
 ('Kernel page cache → byte[]','Copy bytes into the Java process’s read buffer.'),
 ('Java business logic','Read and process the user-space array.')], 'jdk',J+'sun/nio/ch/FileChannelImpl.java','Conceptual buffered-I/O model for the original FileInputStream example.')
flow('netty','java-zero-copy',4,'mmap exposes file-backed pages to the process',[
 ('Map the file','FileChannel.map creates a virtual-memory mapping.'),
 ('Page fault / page cache','The kernel resolves accesses to file-backed pages.'),
 ('MappedByteBuffer access','The process reads/writes the mapped pages without a separate read-buffer copy.'),
 ('Persistence','Dirty pages are flushed by the OS; force requests writeback when needed.')], 'jdk',J+'sun/nio/ch/FileChannelImpl.java','Conceptual mapping; copying mapped data into byte[] still performs a CPU copy.')

class Drawing:
 def __init__(self,s,height,width=1000):
  self.s=s;self.height=height;self.width=width;self.parts=[]
  title=s['title'];desc=s['note'] or title
  self.parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description"><title id="title">{escape(title)}</title><desc id="description">{escape(desc)}</desc><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{BLUE}"/></marker></defs><rect width="{width}" height="{height}" rx="16" fill="#f5f8fc"/><g font-family="Arial, Helvetica, sans-serif">')
  self.text(34,38,VERSIONS[s['version']][0].upper(),13,MUTED,True)
  for i,line in enumerate(textwrap.wrap(title,62)):self.text(34,77+i*32,line,27,INK,True)
 def text(self,x,y,text,size=18,color=INK,bold=False,mono=False,anchor='start'):
  if re.search(r'[\u3400-\u9fff]',text):raise ValueError('Non-English diagram text: '+text)
  fam=' font-family="Menlo, Consolas, monospace"' if mono else ''
  self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{700 if bold else 400}" text-anchor="{anchor}"{fam}>{escape(text)}</text>')
 def rect(self,x,y,w,h,fill='white',stroke='#d5dfeb',rx=10):self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"/>')
 def arrow(self,x1,y1,x2,y2):self.parts.append(f'<path d="M {x1} {y1} L {x2} {y2}" stroke="{BLUE}" stroke-width="2.2" fill="none" marker-end="url(#arrow)"/>')
 def save(self,path,source_url):
  y=self.height-86
  for i,line in enumerate(textwrap.wrap(self.s['note'] or 'English explanatory reconstruction from the named source.',110)):
   self.text(34,y+i*19,line,14,MUTED)
  label=Path(self.s['path']).name
  self.parts.append(f'<a href="{escape(source_url,quote=True)}">');self.text(34,self.height-22,'Source: '+label+' • '+VERSIONS[self.s['version']][0],13,BLUE);self.parts.append('</a></g></svg>')
  path.write_text('\n'.join(self.parts)+'\n')

def source_info(s):
 _,dirname,repo,commit=VERSIONS[s['version']]
 p=CACHE/dirname/s['path']
 if not p.exists():raise ValueError('Missing source: '+str(p))
 return p,f'https://github.com/{repo}/blob/{commit}/{s["path"]}'
def excerpt(s):
 p,url=source_info(s);lines=p.read_text().splitlines();pattern=s['data']['needle']
 start=next((i for i,line in enumerate(lines) if re.search(pattern,line)),None)
 if start is None:raise ValueError(f'Cannot find {pattern} in {p}')
 selected=lines[start:start+s['data']['count']]
 selected=[line for line in selected if line.strip()]
 selected=textwrap.dedent('\n'.join(selected)).splitlines()
 return selected,start+1,url

manifest=json.loads((REPO/'_migration/article-manifest.json').read_text())
records=[]
for a in manifest['articles']:
 for im in a['images']:
  key=(a['topic'],a['slug'],im['index'])
  if key not in SPECS:raise ValueError('Unspecified illustration '+str(key))
  s=SPECS[key];path=REPO/a['topic']/im['asset'];path.parent.mkdir(parents=True,exist_ok=True)
  source_path,url=source_info(s);line=None
  if s['kind']=='flow':
   heights=[]
   for title,body in s['data']:heights.append(55+24*len(textwrap.wrap(body,82)))
   height=140+sum(heights)+30*(len(heights)-1)+125;d=Drawing(s,height);y=135
   for i,((title,body),h) in enumerate(zip(s['data'],heights)):
    d.rect(42,y,916,h);d.text(63,y+30,f'{i+1:02}  '+title,20,BLUE,True)
    for j,t in enumerate(textwrap.wrap(body,82)):d.text(63,y+57+j*24,t,18)
    if i<len(heights)-1:d.arrow(500,y+h+3,500,y+h+25)
    y+=h+30
  elif s['kind']=='fields':
   heights=[40+23*len(textwrap.wrap(v,84)) for _,v in s['data']]
   height=140+sum(heights)+12*len(heights)+120;d=Drawing(s,height);y=132
   for (name,val),h in zip(s['data'],heights):
    d.rect(42,y,916,h);d.text(63,y+28,name,20,TEAL,True)
    for j,t in enumerate(textwrap.wrap(val,84)):d.text(63,y+53+j*23,t,18)
    y+=h+12
  elif s['kind']=='code':
   lines,line,url=excerpt(s)
   # Source lines are soft-wrapped visually; this does not change the excerpt text.
   display=[]
   for t in lines:display+=textwrap.wrap(t,98,replace_whitespace=False,drop_whitespace=False) or ['']
   height=170+len(display)*24+145;d=Drawing(s,height);d.rect(34,133,932,len(display)*24+35,fill='#edf3fa')
   for i,t in enumerate(display):d.text(53,159+i*24,t,15,INK,mono=True)
   d.text(34,height-109,f'Selected excerpt begins at source line {line}; no runtime state is shown.',14,MUTED)
  elif s['kind']=='tree':
   d=Drawing(s,700);levels=[(0,['16 MiB']),(1,['8 MiB','8 MiB']),(2,['4 MiB']*4),(3,['…']*4),(11,['8 KiB']*8)]
   for row,(depth,labels) in enumerate(levels):
    n=len(labels);w=min(150,850/n-12);y=140+row*85
    for i,label in enumerate(labels):
     cx=90+(i+.5)*820/n;d.rect(cx-w/2,y,w,52,fill='#e7eff9');d.text(cx,y+32,label,18,BLUE,True,anchor='middle')
     if row<2:
      for j in [i*2,i*2+1]:d.arrow(cx,y+54,90+(j+.5)*820/(n*2),y+81)
    d.text(34,y+32,'d='+str(depth),14,MUTED)
   d.text(34,574,'Root depth 0 → leaf depth 11: 2048 pages; depthMap is fixed, memoryMap tracks allocation.',16,INK)
  elif s['kind']=='bits':
   d=Drawing(s,640);segments=[(34,110,'63','unused','#eef0f4'),(144,110,'62','subpage marker','#dfeaf8'),(254,332,'61 … 32','bitmapIdx','#e0f3ed'),(586,380,'31 … 0','memoryMapIdx','#eee6f6')]
   for x,w,bits,label,color in segments:
    d.rect(x,156,w,128,fill=color);d.text(x+w/2,188,'bits '+bits,16,INK,True,anchor='middle')
    for i,t in enumerate(textwrap.wrap(label,max(9,int(w/12)))):d.text(x+w/2,224+i*25,t,18,INK,anchor='middle')
   for i,t in enumerate(['0x4000000000000000L','| ((long) bitmapIdx << 32)','| memoryMapIdx']):d.text(54,344+i*33,t,22,BLUE,mono=True)
   d.text(34,476,'bitmapIdx identifies an element within one subpage.',18)
   d.text(34,507,'memoryMapIdx identifies the selected page in the legacy buddy tree.',18)
  else:raise ValueError(s['kind'])
  d.save(path,url)
  records.append({'article':a['slug'],'topic':a['topic'],'image_index':im['index'],'asset':str(path.relative_to(REPO)),'title':s['title'],'kind':s['kind'],'version':VERSIONS[s['version']][0],'source_path':s['path'],'source_url':url,'source_line':line,'note':s['note'],'reconstruction':True})
assert len(records)==69
(REPO/'_migration/figure-provenance.json').write_text(json.dumps(records,indent=2)+'\n')
print('Generated',len(records),'English SVG figures and source provenance records.')
