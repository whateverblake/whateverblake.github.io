"""Regenerate the blog's dependency-free SVG diagrams with Python 3.

Run from any directory: python3 /path/to/mooncake/assets/draw_diagrams.py
All output is written beside this file. Text and geometry are kept explicit
so the technical diagrams remain easy to review and edit.
"""

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parent
INK = "#15283f"
MUTED = "#536579"
BLUE = "#2563b0"
TEAL = "#087f78"
PURPLE = "#7651ac"
ORANGE = "#b35a13"


class Drawing:
    def __init__(self, title, subtitle, height, width=720):
        self.height = height
        self.parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title><desc id="desc">{escape(subtitle)}</desc>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"/></marker></defs>
<rect width="{width}" height="{height}" rx="20" fill="#f4f7fb"/>
<g font-family="Arial, Helvetica, sans-serif">''']
        self.text(32, 43, title, 27, INK, True)
        self.text(32, 75, subtitle, 18, MUTED)

    def text(self, x, y, text, size=21, color=INK, bold=False, anchor="start"):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{700 if bold else 400}" text-anchor="{anchor}">{escape(text)}</text>')

    def box(self, x, y, w, h, title, lines=(), color=BLUE):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="white" stroke="#dce4ee" stroke-width="1.5"/>')
        self.parts.append(f'<rect x="{x}" y="{y+12}" width="5" height="{h-24}" rx="2" fill="{color}"/>')
        self.text(x+20, y+33, title, 22, color, True)
        for i, line in enumerate(lines):
            self.text(x+20, y+63+i*27, line, 20)

    def arrow(self, x1, y1, x2, y2, color=BLUE, dashed=False):
        dash = ' stroke-dasharray="7 6"' if dashed else ''
        self.parts.append(f'<path d="M {x1} {y1} L {x2} {y2}" fill="none" stroke="{color}" stroke-width="2.5"{dash} marker-end="url(#arrow)"/>')

    def line(self, x1, y1, x2, y2):
        self.parts.append(f'<path d="M {x1} {y1} L {x2} {y2}" stroke="#bdcbdc" stroke-width="2" stroke-dasharray="5 7"/>')

    def save(self, name):
        self.text(32, self.height-20, "MOONCAKE  /  SOURCE WALKTHROUGH", 12, MUTED, True)
        self.parts.append('</g></svg>')
        (OUT / (name+'.svg')).write_text('\n'.join(self.parts)+'\n')


def steps(name, title, subtitle, rows, color):
    d = Drawing(title, subtitle, 130+len(rows)*118)
    for i, (heading, detail) in enumerate(rows):
        y = 103+i*118
        d.box(64, y, 592, 89, f'{i+1:02}  {heading}', [detail], color)
        if i < len(rows)-1:
            d.arrow(360, y+91, 360, y+114, color)
    d.save(name)


d = Drawing('One cluster, three processes', 'The master chooses a location. Clients move the bytes.', 570)
d.box(204, 110, 312, 102, 'MASTER', ['Keys • replicas • free space'], BLUE)
d.box(32, 346, 292, 110, 'CALLER', ['Put / Get API', 'Local staging buffer'], TEAL)
d.box(396, 346, 292, 110, 'OWNER', ['Mounted memory pool', 'Stores object bytes'], PURPLE)
d.arrow(170, 340, 270, 220, BLUE)
d.text(39, 258, 'Placement RPCs', 20, BLUE)
d.arrow(548, 340, 456, 220, BLUE)
d.text(496, 234, 'Mount + heartbeat', 19, BLUE)
d.arrow(325, 330, 390, 330, PURPLE)
d.arrow(325, 387, 390, 387, ORANGE)
d.text(360, 314, 'P2P metadata', 19, PURPLE, anchor='middle')
d.text(360, 491, 'TCP data: caller → owner on Put', 22, ORANGE, True, 'middle')
d.text(360, 520, 'Get returns bytes from owner → caller', 20, MUTED, anchor='middle')
d.save('cluster')

steps('master-startup', 'Start the master', 'One process • non-HA path • fresh state', [
    ('Parse and validate configuration', 'main() builds the effective MasterConfig.'),
    ('Construct the RPC server', 'Address, port, and worker count are configured.'),
    ('Construct the service objects', 'WrappedMasterService owns MasterService.'),
    ('Initialize state and start workers', 'Managers exist before any owner mounts memory.'),
    ('Start the HTTP admin server', 'Monitoring and management use a separate port.'),
    ('Register RPC handlers', 'Bind PutStart, MountSegment, Ping, and others.'),
    ('Run the RPC server', 'A serving thread starts; main waits for shutdown.'),
], BLUE)

d = Drawing('What the master keeps', 'These are records and coordination state, not payload pools.', 605)
d.box(32, 110, 656, 89, 'MasterService', ['Owns metadata, managers, and background work.'], BLUE)
d.arrow(184, 201, 184, 226)
d.arrow(536, 201, 536, 226)
d.box(32, 231, 304, 143, 'Object metadata', ['Tenant + key', 'Replica state + address', 'Writer + lease'], BLUE)
d.box(384, 231, 304, 143, 'SegmentManager', ['Mounted owner regions', 'Free-space allocators', 'Client / host indexes'], PURPLE)
d.box(32, 398, 304, 143, 'ClientTaskManager', ['Copy / move assignments', 'Status + retry state', 'Owners execute tasks'], TEAL)
d.box(384, 398, 304, 143, 'Background workers', ['Expiry + eviction', 'Replica / task cleanup', 'Drain jobs + admission'], ORANGE)
d.save('master-state')

steps('owner-startup', 'Turn a client into an owner', 'Standalone mooncake_client • TCP • P2PHANDSHAKE', [
    ('Create RealClient and Client', 'Prepare process resources and parse settings.'),
    ('Connect to the Master service', 'Check service version and request storage settings.'),
    ('Initialize the Transfer Engine', 'Create metadata state and the handshake listener.'),
    ('Install TCP and create the submitter', 'Start the data listener and I/O worker.'),
    ('Allocate storage and register it', 'Prepare a global pool; register its address range.'),
    ('Mount the segment at the master', 'Record capacity and start heartbeat / task polling.'),
    ('Finish standalone service startup', 'Register client RPC handlers and start that server.'),
], PURPLE)

d = Drawing('One pool, three descriptions', 'Example owner: 64 MiB global pool, zero local staging.', 865)
d.box(32, 109, 656, 117, 'OWNER PROCESS: actual memory', ['Allocated pool holds the object bytes.', 'RealClient keeps the CPU allocation alive.'], PURPLE)
d.arrow(360, 231, 360, 259, PURPLE)
d.box(32, 267, 656, 141, '1  MemoryRegion: engine bookkeeping', ['Reserve in registering_memory_regions_.', 'Register with the installed transport.', 'Commit into local_memory_regions_.'], TEAL)
d.arrow(360, 414, 360, 445, TEAL)
d.box(32, 452, 656, 117, '2  SegmentDesc: peer transfer metadata', ['TCP endpoint + BufferDesc address ranges.', 'Peers request it through the P2P handshake.'], PURPLE)
d.arrow(360, 574, 360, 607, BLUE)
d.box(32, 614, 656, 143, '3  Store Segment: master-visible capacity', ['UUID + logical name + base + size + TE endpoint.', 'MountSegment RPC sends this record to the master.', 'Master creates an allocator for the reported range.'], BLUE)
d.text(360, 808, 'Local buffer registration alone does not mount storage.', 21, MUTED, anchor='middle')
d.save('owner-memory')

d = Drawing('Inside one owner process', 'Object relationships • classic Transfer Engine • TCP + P2P', 1390)
d.box(112, 112, 496, 111, 'RealClient', ['High-level API + process-owned buffers', 'Inherits PyClient; client_ holds Client.'], PURPLE)
d.arrow(360, 228, 360, 261, PURPLE)
d.box(112, 268, 496, 111, 'Client', ['MasterClient handles Store RPCs.', 'TransferSubmitter uses the same engine below.'], TEAL)
d.arrow(360, 384, 360, 426, TEAL)
d.text(379, 411, 'transfer_engine_', 18, MUTED)
d.box(112, 433, 496, 85, 'TransferEngine', ['Public transfer API'], TEAL)
d.arrow(360, 523, 360, 565, TEAL)
d.text(379, 550, 'impl_', 18, MUTED)
d.box(112, 572, 496, 111, 'TransferEngineImpl', ['Registration state + transport coordination', 'Holds MultiTransport and TransferMetadata.'], TEAL)
d.arrow(224, 688, 184, 747, TEAL)
d.arrow(496, 688, 540, 747, PURPLE)
d.text(32, 719, 'multi_transports_', 18, MUTED)
d.text(535, 719, 'metadata_', 18, MUTED)
d.box(32, 754, 300, 111, 'MultiTransport', ['transport_map_["tcp"]', 'Selects the transport.'], TEAL)
d.box(392, 754, 296, 165, 'TransferMetadata', ['ONE shared object', 'SegmentDesc / BufferDesc', 'Peer cache + local info', 'Handshake callbacks'], PURPLE)
d.arrow(337, 810, 387, 810, PURPLE, True)
d.arrow(184, 870, 184, 940, TEAL)
d.text(204, 907, 'Transport pointer', 17, MUTED)
d.box(32, 947, 300, 139, 'TcpTransport', ['Implements Transport', 'context_ holds TcpContext.', 'thread_ runs TCP I/O.'], ORANGE)
d.parts.append(f'<path d="M 333 1010 L 361 1010 L 361 886 L 387 886" fill="none" stroke="{PURPLE}" stroke-width="2.5" stroke-dasharray="7 6" marker-end="url(#arrow)"/>')
d.arrow(664, 924, 664, 961, PURPLE)
d.text(421, 955, 'handshake_plugin_', 17, MUTED)
d.box(392, 968, 296, 118, 'SocketHandShakePlugin', ['Implements HandShakePlugin', 'Separate P2P listener'], PURPLE)
d.arrow(184, 1091, 184, 1140, ORANGE)
d.box(32, 1147, 300, 138, 'TcpContext', ['io_context: event-loop state', 'acceptor: new connections', 'validate_addr_: range check'], ORANGE)
d.text(394, 1182, 'Solid: member relationship', 19, INK, True)
d.text(394, 1215, 'Dashed: shared metadata', 19, PURPLE, True)
d.text(394, 1248, 'Arrows do not imply', 19, MUTED)
d.text(394, 1274, 'one thread per object.', 19, MUTED)
d.text(360, 1335, 'Transfer metadata describes memory; the master tracks keys.', 21, INK, True, 'middle')
d.save('owner-objects')

d = Drawing('The owner: classes and important members', 'CPU memory · TCP + P2PHANDSHAKE · all objects are in one process', 1480, width=1200)

def class_group(x, y, w, h, title, fill, stroke):
    d.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
    d.text(x+22, y+35, title, 25, stroke, True)

class_group(24, 109, 1152, 1241, 'RealClient : PyClient', '#fff4e8', ORANGE)
d.text(48, 177, 'High-level Store API + backing allocations', 22)
d.text(48, 213, 'client_ holds the Client shown below.', 21, MUTED)
d.text(48, 245, 'client_ and client_buffer_allocator_ are inherited from PyClient.', 18, MUTED)
d.box(770, 150, 382, 104, 'ClientBufferAllocator', ['client_buffer_allocator_', 'Local staging memory'], ORANGE)

class_group(48, 280, 1104, 1043, 'Client', '#eaf3ff', BLUE)
d.box(72, 346, 312, 142, 'MasterClient', ['master_client_', 'Store RPCs to the master', 'MountSegment / PutStart'], BLUE)
d.box(432, 346, 312, 142, 'TransferSubmitter', ['transfer_submitter_', 'engine_: TransferEngine&', 'Uses the same engine below'], TEAL)
d.box(792, 346, 336, 142, 'mounted_segments_', ['UUID → Segment', 'Owner-side Store records', 'No master allocator here'], BLUE)
d.arrow(588, 493, 588, 541, TEAL, True)
d.text(609, 524, 'engine_ reference', 19, TEAL)

class_group(72, 548, 1056, 748, 'TransferEngine', '#f0edf9', PURPLE)
d.text(95, 613, 'Client::transfer_engine_ holds this public API wrapper.', 20, MUTED)
d.arrow(700, 602, 700, 643, PURPLE)
d.text(718, 628, 'impl_', 19, PURPLE)

class_group(96, 650, 1008, 624, 'TransferEngineImpl', '#faf8ff', PURPLE)
d.text(120, 718, 'Local registration bookkeeping:', 20, MUTED)
d.text(120, 748, 'local_memory_regions_  ·  registering_memory_regions_', 21)
d.text(120, 776, 'multi_transports_ ↓', 18, TEAL)
d.text(624, 776, 'metadata_ ↓', 18, PURPLE)

class_group(120, 792, 432, 458, 'MultiTransport', '#e4f4f0', TEAL)
d.text(142, 856, 'transport_map_["tcp"]', 21)
d.text(142, 885, 'shared_ptr<Transport> → TcpTransport', 19)
d.text(142, 918, 'metadata_', 20, PURPLE)
d.arrow(557, 911, 619, 911, PURPLE, True)

class_group(142, 953, 388, 273, 'TcpTransport : Transport', '#fff4e8', ORANGE)
d.text(163, 1019, 'thread_: runs the TCP event loop', 20)
d.text(163, 1052, 'metadata_: inherited shared pointer', 19, PURPLE)
d.text(163, 1083, 'context_ ↓', 19, ORANGE)
d.box(162, 1095, 348, 110, 'TcpContext', ['io_context: event-loop state', 'acceptor: TCP data port D'], ORANGE)
d.parts.append(f'<path d="M 533 1050 L 586 1050 L 586 947 L 619 947" fill="none" stroke="{PURPLE}" stroke-width="2.5" stroke-dasharray="7 6" marker-end="url(#arrow)"/>')

class_group(624, 792, 456, 458, 'TransferMetadata (shared)', '#eee7f9', PURPLE)
d.text(646, 856, 'local_rpc_meta_: handshake endpoint H', 20)
d.text(646, 887, 'segment_id_to_desc_map_', 21)
d.text(646, 918, 'segment_name_to_id_map_', 21)
d.text(646, 949, 'Shared with the TCP transport', 20, MUTED)
d.text(646, 980, 'handshake_plugin_ ↓', 18, PURPLE)
d.box(644, 996, 416, 229, 'SocketHandShakePlugin', [], PURPLE)
d.text(664, 1057, 'listen_fd_: listens on handshake port H', 19)
d.text(664, 1088, 'listener_: accepts connections', 19)
d.text(664, 1125, 'on_metadata_callback_ →', 19)
d.text(664, 1155, 'TransferMetadata::receivePeerMetadata', 19)
d.text(664, 1193, 'Other callbacks: connection / notify / probe', 18)

d.text(40, 1385, 'Nested boxes: held objects / state, not exclusive ownership or separate threads.', 21, MUTED)
d.text(40, 1414, 'Dashed arrows: references. Both metadata_ arrows reach the same shared object.', 21, PURPLE)
d.save('owner-class-map')

d = Drawing('Master service: key metadata and available storage', 'TCP + CPU memory · nested boxes show the main member relationships', 1470, width=1200)
class_group(24, 110, 1152, 1280, 'MasterService', '#eaf3ff', BLUE)
class_group(48, 186, 664, 1170, 'metadata_shards_: 1024 MetadataShard', '#f0edf9', PURPLE)
d.text(72, 252, 'Find an object by tenant + key', 22, PURPLE)
class_group(72, 281, 616, 1048, 'MetadataShard  [s]', '#faf8ff', PURPLE)
d.text(96, 347, 'mutex: protects this shard', 21)
d.text(96, 379, 'tenants: TenantId → TenantState', 21)
class_group(96, 402, 568, 900, 'TenantState', '#e4f4f0', TEAL)
d.text(120, 469, 'metadata: string key → ObjectMetadata', 21)
d.text(120, 501, 'processing_keys: keys with unfinished writes', 21)
class_group(120, 553, 520, 720, 'ObjectMetadata  [key]', '#f7fcfa', TEAL)
d.text(144, 619, 'tenant_id · user_key · writer client_id', 21)
d.text(144, 651, 'size · lease_timeout', 21)
d.text(144, 691, 'replicas_: vector<Replica>', 21, TEAL)
class_group(144, 716, 472, 530, 'Replica', '#fff4e8', ORANGE)
d.text(168, 782, 'id_: ReplicaID (uint64_t)', 21)
d.text(168, 813, 'status_: ReplicaStatus enum', 21)
d.text(168, 844, 'data_: variant holding MemoryReplicaData', 20)
class_group(168, 866, 424, 354, 'MemoryReplicaData', '#fffaf1', ORANGE)
d.text(192, 933, 'buffer: unique_ptr<AllocatedBuffer>', 20)
d.box(192, 966, 376, 227, 'AllocatedBuffer', [], ORANGE)
d.text(212, 1032, 'buffer_ptr_: address in the owner', 19)
d.text(212, 1063, 'size_ · protocol = "tcp"', 20)
d.text(212, 1094, 'offset_handle_: reserved range', 19)
d.text(212, 1130, 'allocator_: weak_ptr', 20, PURPLE)
d.text(212, 1168, 'No payload stored in this object.', 18, MUTED)

class_group(752, 186, 400, 1170, 'SegmentManager', '#e4f4f0', TEAL)
d.text(776, 252, 'segment_manager_: storage capacity', 19, TEAL)
d.box(776, 292, 352, 170, 'mounted_segments_', ['Segment UUID → MountedSegment', 'segment: owner pool description', 'status: SegmentStatus', 'buf_allocator: shared_ptr'], BLUE)
d.box(776, 505, 352, 157, 'AllocatorManager', ['allocator_manager_', 'allocators_: name → vector', 'of shared allocator pointers'], TEAL)
d.arrow(952, 667, 952, 721, TEAL)
d.text(775, 701, 'Same allocator', 19, TEAL)
d.box(776, 728, 352, 209, 'OffsetBufferAllocator', ['base_ · total_size_ · endpoint'], TEAL)
d.box(796, 846, 312, 73, 'OffsetAllocator', ['Free blocks and size bins'], TEAL)
d.parts.append(f'<path d="M 1129 421 L 1140 421 L 1140 818 L 1131 818" fill="none" stroke="{TEAL}" stroke-width="2.5" marker-end="url(#arrow)"/>')
d.parts.append(f'<path d="M 570 1124 L 732 1124 L 732 819 L 771 819" fill="none" stroke="{PURPLE}" stroke-width="2.5" stroke-dasharray="7 6" marker-end="url(#arrow)"/>')
d.box(776, 998, 352, 294, 'Other segment indexes', [], BLUE)
d.text(796, 1060, 'client_segments_', 21)
d.text(796, 1091, 'owner UUID → segment UUIDs', 19)
d.text(796, 1133, 'client_by_name_', 21)
d.text(796, 1174, 'segment_id_by_name_', 21)
d.text(796, 1215, 'segments_by_host_', 21)
d.text(796, 1259, 'These locate pools, not keys.', 19, MUTED)
d.text(40, 1424, 'Solid arrows: shared allocator references. Dashed arrow: AllocatedBuffer holds a weak reference.', 21, MUTED)
d.save('master-class-map')

steps('master-key-lookup', 'Get follows the key to its replica', 'Example after a successful Put: one readable 4096-byte replica', [
    ('GetReplicaList("blog/example")', 'Resolve the request to tenant "default" + the full key.'),
    ('MetadataAccessorRO selects shard s', 'For this key: s = hash("blog/example") % 1024.'),
    ('shard.tenants.find(tenant_id)', 'Find this tenant’s state inside the selected shard.'),
    ('tenant.metadata.find("blog/example")', 'Find the ObjectMetadata created by PutStart.'),
    ('Visit ObjectMetadata::replicas_', 'PutEnd made replica 101 COMPLETE; check readability.'),
    ('Build Replica::Descriptor', '127.0.0.1:16001 · address 0x70002000 · 4096 bytes'),
    ('Caller reads from the owner', 'P2P resolves the data endpoint; TCP returns the bytes.'),
], BLUE)

d = Drawing('One owner pool, three places holding descriptions', 'TCP + P2PHANDSHAKE · the memory stays in the owner process', 1200, width=1200)
class_group(24, 126, 368, 711, 'OWNER', '#fff4e8', ORANGE)
d.box(48, 187, 320, 102, 'RealClient', ['segment_ptrs_: backing memory', 'Example: 64 MiB pool'], ORANGE)
d.box(48, 313, 320, 137, 'TransferEngineImpl', [], TEAL)
d.text(68, 375, 'registering_memory_regions_', 18)
d.text(68, 404, '       ↓ registration succeeds', 18, MUTED)
d.text(68, 433, 'local_memory_regions_', 18)
d.box(48, 475, 320, 229, 'TransferMetadata', [], PURPLE)
d.text(68, 537, 'segment_id_to_desc_map_[0]', 18)
d.text(68, 567, '→ local SegmentDesc', 20)
d.text(68, 598, '    buffers[] → BufferDesc', 19)
d.text(68, 629, '    addr = owner pool base', 18)
d.text(68, 660, '    length = registered size', 18)
d.box(48, 715, 320, 109, 'Client', ['mounted_segments_', 'UUID → Segment'], BLUE)

class_group(430, 126, 342, 711, 'MASTER', '#eaf3ff', BLUE)
d.box(454, 187, 294, 227, 'SegmentManager', [], BLUE)
d.text(474, 249, 'mounted_segments_[UUID]', 18)
d.text(474, 280, '→ MountedSegment', 20)
d.text(474, 311, '    segment: Store Segment', 18)
d.text(474, 342, '    status: OK', 18)
d.text(474, 373, '    buf_allocator', 18)
d.arrow(601, 419, 601, 448, TEAL)
d.box(454, 455, 294, 145, 'OffsetBufferAllocator', ['Free / reserved ranges', 'within the owner pool', 'Bookkeeping only'], TEAL)
d.text(454, 651, 'Store UUID identifies the pool.', 18, MUTED)
d.text(454, 680, 'No SegmentDesc in this record.', 18, MUTED)
d.text(454, 775, 'Also: client / name / host indexes', 18, MUTED)

class_group(810, 126, 366, 711, 'REQUESTING CLIENT', '#e4f4f0', TEAL)
d.box(834, 187, 318, 304, 'TransferMetadata', [], PURPLE)
d.text(854, 249, 'segment_name_to_id_map_', 18)
d.text(854, 280, 'owner endpoint → remote ID', 18)
d.text(854, 320, 'segment_id_to_desc_map_', 18)
d.text(854, 351, 'remote ID → SegmentDesc', 18)
d.text(854, 391, 'A decoded copy of the', 20)
d.text(854, 422, "owner's description", 20)
d.text(854, 461, 'Example remote ID: 1', 18, MUTED)
d.text(834, 547, 'Fetched on the first cache miss.', 18, MUTED)
d.text(834, 589, 'Not a local memory registration.', 18, MUTED)
d.text(834, 621, 'Not a Store mount by this client.', 18, MUTED)
d.text(834, 680, 'No copy of the whole pool.', 20, TEAL, True)
d.text(834, 775, 'Object range comes from master.', 18, MUTED)

for x in [208, 601, 993]:
    d.line(x, 853, x, 1110)
d.text(404, 886, '1  MountSegment: Store Segment', 19, BLUE, False, 'middle')
d.arrow(208, 904, 601, 904, BLUE)
d.text(797, 957, '2  PutStart reply: allocated range', 19, BLUE, False, 'middle')
d.arrow(601, 975, 993, 975, BLUE)
d.text(601, 1032, '3  Peer fetches via P2P; owner replies with encoded SegmentDesc', 20, PURPLE, False, 'middle')
d.arrow(208, 1050, 993, 1050, PURPLE, True)
d.text(600, 1131, 'Mounting announces capacity. Peer discovery caches metadata. A later WRITE moves bytes.', 22, INK, True, 'middle')
d.save('owner-memory-distribution')

d = Drawing('Start two different listeners', 'Startup runs top to bottom; both listeners remain active.', 1370)
listener_steps = [
    ('1  Client::InitTransferEngine()', 'Initialize the engine, then install the TCP transport.', TEAL),
    ('2  TransferEngineImpl::init()', 'Choose H; create TransferMetadata + MultiTransport.', TEAL),
    ('3  addRpcMetaEntry()', 'Save handshake address; register peer callbacks.', PURPLE),
    ('4  Start the handshake listener', 'SocketHandShakePlugin::startDaemon() listens on H.', PURPLE),
    ('5  TcpTransport::install()', 'Choose D; store the TCP endpoint in SegmentDesc.', ORANGE),
    ('6  Construct TcpContext', 'acceptor(io_context) binds and listens on D.', ORANGE),
    ('7  Start the TCP worker', 'doAccept() starts acceptance; io_context.run() runs I/O.', ORANGE),
]
for i, (title, detail, color) in enumerate(listener_steps):
    y = 108 + i * 122
    d.box(32, y, 656, 92, title, [detail], color)
    if i < len(listener_steps)-1:
        d.arrow(360, y+97, 360, y+116, color)
d.text(360, 985, 'RUNNING AFTER THIS STAGE', 19, MUTED, True, 'middle')
d.box(32, 1010, 656, 117, 'SocketHandShakePlugin listens on H', ['listen_fd_: listening socket for metadata / control', 'listener_: thread accepting peer connections'], PURPLE)
d.box(32, 1150, 656, 117, 'TcpContext::acceptor listens on D', ['TcpTransport owns the context and runs the worker.', 'ServerSession handles each accepted data connection.'], ORANGE)
d.text(360, 1319, 'Global memory is registered and mounted later.', 22, INK, True, 'middle')
d.save('owner-listeners')

d = Drawing('Mount a segment: owner → master', 'Register the range locally, then announce storage capacity.', 1180)
d.text(32, 123, 'OWNER PROCESS', 20, PURPLE, True)
d.text(382, 123, 'MASTER PROCESS', 20, BLUE, True)
d.line(360, 143, 360, 1119)
d.box(32, 153, 304, 89, '1  RealClient', ['Allocate the global pool.'], PURPLE)
d.arrow(184, 247, 184, 277, PURPLE)
d.box(32, 284, 304, 111, '2  Client', ['MountSegmentAndGetId()', 'Validate / check overlap.'], TEAL)
d.arrow(184, 400, 184, 430, TEAL)
d.box(32, 437, 304, 111, '3  Transfer Engine', ['Register the address range.', 'TCP updates BufferDesc.'], TEAL)
d.arrow(184, 553, 184, 587, TEAL)
d.box(32, 594, 304, 89, '4  MasterClient', ['Send Segment + client UUID.'], TEAL)
d.text(384, 241, 'The RPC carries metadata.', 21, BLUE, True)
d.text(384, 273, 'The pool stays in the owner.', 20, MUTED)
d.text(384, 329, 'Segment UUID: which pool?', 20, MUTED)
d.text(384, 361, 'Client UUID: whose pool?', 20, MUTED)
d.arrow(339, 639, 379, 639, BLUE)
d.box(382, 594, 306, 89, 'WrappedMasterService', ['RPC entry → service method'], BLUE)
d.arrow(536, 688, 536, 723, BLUE)
d.box(382, 730, 306, 111, 'MasterService', ['Acquire segment access.', 'Queue owner liveness ID.'], BLUE)
d.arrow(536, 846, 536, 877, BLUE)
d.box(382, 884, 306, 111, 'ScopedSegmentAccess', ['Create the allocator.', 'Insert record and indexes.'], BLUE)
d.box(32, 1020, 304, 111, '5  Client: finish mount', ['Save Segment in local map.', 'Start heartbeat / task poll.'], PURPLE)
d.parts.append(f'<path d="M 536 1000 L 536 1065 L 341 1065" fill="none" stroke="{BLUE}" stroke-width="2.5" stroke-dasharray="7 6" marker-end="url(#arrow)"/>')
d.text(554, 1045, 'Success', 20, BLUE)
d.save('segment-mount-flow')

d = Drawing('Where the mounted segment lives', 'Two processes • two maps • one payload pool', 1120)
d.box(32, 110, 656, 89, 'MASTER: SegmentManager', ['Records mounted capacity and controls allocation.'], BLUE)
d.arrow(184, 204, 184, 235, BLUE)
d.arrow(536, 204, 536, 235, BLUE)
d.box(32, 242, 304, 143, 'mounted_segments_[id]', ['MountedSegment record', 'segment + status OK', 'buf_allocator'], BLUE)
d.box(382, 242, 306, 143, 'allocator_manager_', ['AllocatorManager', 'name → allocator pointers', 'Used by allocation strategy'], BLUE)
d.arrow(184, 390, 268, 474, TEAL)
d.arrow(536, 390, 452, 474, TEAL)
d.text(360, 430, 'Same object', 19, TEAL, True, 'middle')
d.box(112, 481, 496, 143, 'OffsetBufferAllocator', ['Segment name + base + capacity + endpoint', 'OffsetAllocator tracks free / reserved ranges.', 'No owner payload is copied into the master.'], TEAL)
d.box(32, 656, 656, 116, 'Other indexes in SegmentManager', ['Client → segment IDs; name → client / segment ID', 'Host → names → IDs; capacity and usage tracking'], BLUE)
d.line(32, 810, 688, 810)
d.box(32, 845, 656, 143, 'OWNER: Client + RealClient', ['Client::mounted_segments_[id] stores a Segment.', 'RealClient keeps the real 64 MiB memory allocation.', 'The owner map has no master-side allocator field.'], PURPLE)
d.text(360, 1040, 'Mount: make a pool available.', 22, INK, True, 'middle')
d.text(360, 1072, 'Later Put: reserve a range inside that pool.', 22, INK, True, 'middle')
d.save('segment-mount-state')

d = Drawing('Same client stack, two roles', 'CPU memory · TCP + P2PHANDSHAKE · different memory settings', 1010, width=960)
for i, (title, detail) in enumerate([
    ('RealClient::create()', 'Create the same high-level client object in both processes.'),
    ('RealClient::setup_internal()', 'Owner calls directly; caller enters through setup_real().'),
    ('Client::Create()', 'Construct Client and connect to the Master service.'),
    ('Initialize transfers', 'Create Transfer Engine, TCP listeners, and TransferSubmitter.'),
]):
    y=110+i*120
    d.box(144,y,672,89,title,[detail],TEAL)
    if i<3:d.arrow(480,y+94,480,y+114,TEAL)
d.arrow(360,564,248,632,PURPLE)
d.arrow(600,564,712,632,TEAL)
d.box(32,639,432,222,'OWNER: contributes memory',[
    'global: 64 MiB · local: 0',
    'Register the global pool.',
    'MountSegment → Master service.',
    'Start heartbeat and task polling.',
],PURPLE)
d.box(496,639,432,222,'CALLER: Put / Get',[
    'global: 0 · local: 16 MiB',
    'Register local staging memory.',
    'No global pool to mount.',
    'Call put() and get_buffer().',
],TEAL)
d.text(480,909,'Both roles have a Transfer Engine and TCP listeners.',24,INK,True,'middle')
d.text(480,947,'The owner executable adds its client RPC server after setup.',21,MUTED,False,'middle')
d.save('client-role-workflow')

d = Drawing('Get reuses the same caller', 'One completed memory replica · TCP protocol v2', 775)
for x,label,color in [(111,'CALLER',TEAL),(360,'MASTER',BLUE),(609,'OWNER',PURPLE)]:
    d.box(x-79,108,158,56,label,color=color)
    d.line(x,177,x,655)
for y,x1,x2,label,color in [
    (220,111,360,'Query the key',BLUE),
    (300,360,111,'Replicas + lease',BLUE),
    (453,111,609,'READ header: owner address + length',ORANGE),
    (533,609,111,'Status response',ORANGE),
    (605,609,111,'Value bytes → caller local buffer',ORANGE),
]:
    d.text((x1+x2)/2,y-15,label,20,color,False,'middle')
    d.arrow(x1,y,x2,y,color,x2<x1)
d.text(360,365,'Choose a replica and allocate a local destination.',20,INK,False,'middle')
d.text(360,396,'Reuse peer metadata, or fetch it through P2P.',19,MUTED,False,'middle')
d.text(360,694,'get_buffer() returns a handle to the received bytes.',22,INK,True,'middle')
d.text(360,730,'No new client, no global allocation, and no PutEnd.',20,MUTED,False,'middle')
d.save('get-sequence')

d = Drawing('A Put has three milestones', 'One new key • one memory replica • first peer connection', 850)
xs = [111, 360, 609]
for x, label, color in zip(xs, ['CALLER', 'MASTER', 'OWNER'], [TEAL, BLUE, PURPLE]):
    d.box(x-79, 108, 158, 56, label, color=color)
    d.line(x, 177, x, 776)

def msg(y, a, b, label, color, dashed=False):
    d.text((xs[a]+xs[b])/2, y-14, label, 20, color, False, 'middle')
    d.arrow(xs[a], y, xs[b], y, color, dashed)

msg(220, 0, 1, '1  PutStart', BLUE)
msg(287, 1, 0, 'Reserved replica', BLUE, True)
msg(365, 0, 2, 'P2P handshake: request peer description', PURPLE)
msg(424, 2, 0, 'TCP endpoint + registered buffer ranges', PURPLE, True)
msg(503, 0, 2, '2  TCP WRITE: header + object bytes', ORANGE)
msg(575, 2, 0, 'v2 acknowledgement: body received', ORANGE, True)
msg(654, 0, 1, '3  PutEnd', BLUE)
msg(723, 1, 0, 'Replica COMPLETE', BLUE, True)
d.text(360, 803, 'The master never forwards the object payload.', 22, INK, True, 'middle')
d.save('put-sequence')

d = Drawing('Allocate an offset, not a new pool', 'Illustrative addresses • 4096-byte object • no extra rounding', 642)
d.box(32, 112, 656, 115, 'MASTER: allocation bookkeeping', ['Pick a free block; split it; record the replica.', 'Returned address = owner base + byte offset'], BLUE)
d.arrow(360, 232, 360, 274, BLUE)
d.text(360, 312, '0x70000000 + 0x2000 = 0x70002000', 25, INK, True, 'middle')
d.box(32, 347, 656, 194, 'OWNER: existing global memory pool', [], PURPLE)
for x, w, fill, label in [(53, 180, '#e6edf7', 'Earlier ranges'), (233, 207, '#dcd1ed', '4096 bytes'), (440, 228, '#e0f2eb', 'Remaining space')]:
    d.parts.append(f'<rect x="{x}" y="408" width="{w}" height="65" fill="{fill}" stroke="white" stroke-width="2"/>')
    d.text(x+w/2, 447, label, 18, INK, True, 'middle')
d.text(233, 505, '↑ chosen offset 0x2000', 20, PURPLE)
d.text(360, 590, 'Freeing a block can merge neighboring free ranges.', 21, MUTED, anchor='middle')
d.save('offset-allocation')

steps('asio-flow', 'From queued work to a callback', 'One TCP worker runs the event loop; lanes reuse sockets.', [
    ('Submitter queues a TcpWorkItem', 'post(group->executor, handler) makes work ready.'),
    ('TCP worker: io_context.run()', 'The worker executes the posted runGroupPump().'),
    ('Pump chooses a lane', 'Use its connection, or begin async_resolve().'),
    ('Resolution finishes', 'Completion handler starts async_connect().'),
    ('Connection finishes', 'Completion handler makes the lane usable.'),
    ('Start the session', 'Async header / body I/O advances through callbacks.'),
    ('Session finishes', 'Update the task, reuse the lane, pump more work.'),
], TEAL)

d = Drawing('TCP Write: two sessions', 'Protocol v2 • CPU memory • logical order of completion', 688)
d.box(32, 108, 306, 89, 'ClientSession', ['Runs in the caller'], TEAL)
d.box(382, 108, 306, 89, 'ServerSession', ['Runs in the owner'], PURPLE)
d.line(150, 209, 150, 590)
d.line(570, 209, 570, 590)
for y, label in [(263, 'WRITE header: address + length'), (349, 'Body: bytes from local staging buffer')]:
    d.text(360, y-17, label, 20, ORANGE, False, 'middle')
    d.arrow(150, y, 570, y, ORANGE)
d.box(341, 382, 347, 91, 'Owner memory', ['readBody() fills the target.'], PURPLE)
d.text(360, 514, 'Success status after the complete body', 20, PURPLE, False, 'middle')
d.arrow(570, 532, 150, 532, PURPLE, True)
d.text(360, 610, 'Complete when body write + acknowledgement succeed.', 21, INK, True, 'middle')
d.text(360, 640, 'Then the Store caller sends PutEnd to the master.', 20, MUTED, False, 'middle')
d.save('tcp-write')


d = Drawing('One peer group, several TCP connections',
            'Caller objects → TCP connections → owner sessions · two lanes shown',
            1200, width=960)
class_group(32, 110, 896, 715, 'CALLER: PeerConnectionGroup', '#eaf3ff', BLUE)
d.text(56, 178, 'key = owner host + data port D     |     lanes = vector of lane pointers', 20, INK)
d.box(192, 210, 576, 88, 'queue: waiting TcpWorkItem objects', ['Work C waits while A and B are active below.'], BLUE)
d.arrow(480, 303, 480, 329, BLUE)
d.text(480, 357, 'runGroupPump() assigns work to available lanes', 22, BLUE, True, 'middle')
d.arrow(365, 373, 269, 408, TEAL)
d.arrow(595, 373, 691, 408, TEAL)
for x, lane_id, work in [(64, 0, 'A'), (486, 1, 'B')]:
    center = x+205
    class_group(x, 415, 410, 379, f'ConnectionLane {lane_id}', '#e7f4f0', TEAL)
    d.text(x+22, 481, f'current = work {work}     state = BUSY', 20, INK)
    d.box(x+20, 504, 370, 88, 'session → ClientSession', ['Runs this work item’s transfer.'], TEAL)
    d.arrow(center, 597, center, 654, TEAL)
    d.text(center+16, 631, 'socket_', 18, TEAL)
    d.box(x+20, 661, 370, 108, f'socket → TCP socket {lane_id}',
          ['Same object as session.socket_', 'One reusable caller-side socket'], ORANGE)
    d.arrow(center, 774, center, 928, ORANGE)
    d.text(center+16, 869, f'Connection {lane_id}', 19, ORANGE, True)
    d.text(center+16, 896, 'to owner port D', 18, ORANGE)
class_group(32, 938, 896, 158, 'OWNER: TcpContext::acceptor listens on data port D', '#f1ebf8', PURPLE)
for x, lane_id in [(84, 0), (506, 1)]:
    d.box(x, 982, 370, 90, f'ServerSession {lane_id}',
          ['Uses its own accepted socket.'], PURPLE)
d.text(480, 1136, 'All caller lanes share one io_context and TCP worker.', 23, INK, True, 'middle')
d.text(480, 1166, 'Each lane is a connection slot; it does not create a thread.', 20, MUTED, False, 'middle')
d.save('tcp-lanes')
