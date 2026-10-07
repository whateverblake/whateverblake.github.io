"""Regenerate the Mooncake series diagrams as dependency-free SVG files.

Run: python3 mooncake/assets/draw_diagrams.py
Output is written beside this file. All diagrams share one canvas width,
one type scale and one colour per role, so they scale identically on the page:

  master  blue    owner  purple    caller  green    TCP data  orange
"""

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parent
W = 960
SANS = "IBM Plex Sans, -apple-system, Helvetica Neue, Helvetica, Arial, sans-serif"
MONO = "JetBrains Mono, SFMono-Regular, Menlo, Consolas, monospace"
INK, MUTED, FAINT, LINE, PANEL = "#1f2328", "#59636e", "#818b98", "#d1d9e0", "#f6f8fa"
ROLE = {  # stroke/text colour, tint
    "master": ("#0969da", "#ddf4ff"),
    "owner": ("#8250df", "#fbefff"),
    "caller": ("#1a7f37", "#dafbe1"),
    "data": ("#bc4c00", "#fff1e5"),
    "neutral": ("#59636e", "#f6f8fa"),
}
WARN = []


def width_of(text, size, mono=False):
    return len(text) * size * (0.61 if mono else 0.53)


class Diagram:
    def __init__(self, name, height, title, subtitle=""):
        self.name, self.h, self.parts = name, height, []
        self.title, self.subtitle = title, subtitle
        self.text(32, 40, title, 20, INK, 600)
        if subtitle:
            self.text(32, 64, subtitle, 13.5, MUTED)

    # primitives -----------------------------------------------------------
    def text(self, x, y, s, size=13.5, color=INK, weight=400, mono=False, anchor="start", halo=False):
        fam = MONO if mono else SANS
        extra = ' paint-order="stroke" stroke="#ffffff" stroke-width="5" stroke-linejoin="round"' if halo else ""
        self.parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{fam}" font-size="{size}" fill="{color}" '
            f'font-weight="{weight}" text-anchor="{anchor}"{extra}>{escape(s)}</text>')

    def rect(self, x, y, w, h, fill="#ffffff", stroke=LINE, rx=6, dash=None, sw=1):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
                          f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def line(self, pts, color=LINE, dash=None, sw=1.5, arrow=False):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        m = f' marker-end="url(#a-{color[1:]})"' if arrow else ""
        path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        self.parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{sw}"{d}{m}/>')

    # building blocks --------------------------------------------------------
    def node(self, x, y, w, h, head, lines=(), role="neutral", head_mono=True, tag=None, size=13):
        """A white box with a coloured header line and optional body lines."""
        color, _ = ROLE[role]
        self.rect(x, y, w, h)
        self.parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="4" height="{h:.1f}" rx="2" fill="{color}"/>')
        self.text(x + 16, y + 22, head, 14 if head_mono else 14.5, color, 600, mono=head_mono)
        self._check(head, 14, head_mono, w - 24 - (width_of(tag, 11, True) + 18 if tag else 0))
        if tag:
            tw = width_of(tag, 11, True) + 12
            self.rect(x + w - tw - 8, y + 8, tw, 18, PANEL, LINE, 4)
            self.text(x + w - 8 - tw / 2, y + 21, tag, 11, MUTED, 500, True, "middle")
        for i, s in enumerate(lines):
            mono = s.startswith("`")
            s = s.strip("`")
            self.text(x + 16, y + 44 + i * 19, s, size - (0.5 if mono else 0), INK if not mono else MUTED, mono=mono)
            self._check(s, size, mono, w - 24)
        return dict(x=x, y=y, w=w, h=h, cx=x + w / 2, cy=y + h / 2, l=x, r=x + w, t=y, b=y + h)

    def group(self, x, y, w, h, label, role="neutral", note=None):
        color, tint = ROLE[role]
        self.rect(x, y, w, h, tint, color, 8, None, 1)
        self.text(x + 14, y + 22, label, 12, color, 700, True)
        if note:
            self.text(x + w - 14, y + 22, note, 12, MUTED, 400, False, "end")

    def arrow(self, pts, role="neutral", dash=None, label=None, at=0.5, dy=-7, anchor="middle", sw=1.6, lsize=12.5):
        color = ROLE[role][0]
        self.line(pts, color, dash, sw, True)
        if label:
            (x1, y1), (x2, y2) = pts[0], pts[-1]
            if len(pts) > 2:
                (x1, y1), (x2, y2) = pts[len(pts) // 2 - 1], pts[len(pts) // 2]
            self.text(x1 + (x2 - x1) * at, y1 + (y2 - y1) * at + dy, label, lsize, color, 500, False, anchor, True)

    def tag(self, x, y, s, role="neutral"):
        color, tint = ROLE[role]
        tw = width_of(s, 11.5, True) + 14
        self.rect(x, y, tw, 20, tint, color, 4)
        self.text(x + tw / 2, y + 14, s, 11.5, color, 600, True, "middle")
        return tw

    def legend(self, items, y):
        x = 32
        for label, role, dash in items:
            color = ROLE[role][0]
            self.line([(x, y), (x + 34, y)], color, dash, 1.8, True)
            self.text(x + 44, y + 4.5, label, 12.5, MUTED)
            x += 60 + width_of(label, 12.5)

    def lifelines(self, actors, top, bottom):
        """Sequence-diagram columns: [(x, label, role), ...]."""
        for x, label, role in actors:
            color, tint = ROLE[role]
            w = max(120, width_of(label, 13.5, True) + 28)
            self.rect(x - w / 2, top, w, 32, tint, color, 6)
            self.text(x, top + 21, label, 13.5, color, 600, True, "middle")
            self.line([(x, top + 32), (x, bottom)], LINE, "4 4", 1.2)

    def msg(self, x1, x2, y, label, role="neutral", dash=None, note=None):
        self.arrow([(x1, y), (x2, y)], role, dash, label, 0.5, -8)
        if note:
            self.text((x1 + x2) / 2, y + 17, note, 11.5, FAINT, 400, False, "middle")

    def step(self, x, y, n, role="neutral"):
        color, _ = ROLE[role]
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="10" fill="{color}"/>')
        self.text(x, y + 4.2, str(n), 11.5, "#ffffff", 700, True, "middle")

    def _check(self, s, size, mono, room):
        if width_of(s, size, mono) > room + 2:
            WARN.append(f"{self.name}: '{s}' ({width_of(s, size, mono):.0f}px > {room:.0f}px)")

    def save(self):
        markers = "".join(
            f'<marker id="a-{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            f'orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{c}"/></marker>'
            for c in [v[0] for v in ROLE.values()] + [LINE])
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{self.h}" viewBox="0 0 {W} {self.h}" '
               f'role="img" aria-labelledby="t d"><title id="t">{escape(self.title)}</title>'
               f'<desc id="d">{escape(self.subtitle)}</desc><defs>{markers}</defs>'
               f'<rect width="{W}" height="{self.h}" fill="#ffffff"/>' + "\n".join(self.parts) + "</svg>\n")
        (OUT / f"{self.name}.svg").write_text(svg)


# ---------------------------------------------------------------------------
# Series overview
# ---------------------------------------------------------------------------
def cluster():
    d = Diagram("cluster", 470, "One cluster, three processes",
                "The master decides where an object goes. Clients move the bytes themselves.")
    m = d.node(330, 96, 300, 86, "mooncake_master", ["keys → replica locations", "mounted segments, free space"], "master", tag=":50051")
    c = d.node(40, 268, 270, 86, "caller · RealClient", ["Put / Get API", "16 MiB staging buffer"], "caller")
    o = d.node(650, 268, 270, 86, "owner · mooncake_client", ["64 MiB mounted pool", "holds the object bytes"], "owner", tag=":H :D")
    d.arrow([(c["cx"] - 40, c["t"]), (m["l"] + 30, m["b"])], "master", "6 4", "PutStart · PutEnd · GetReplicaList", 0.5, -14, "end")
    d.arrow([(o["cx"] + 40, o["t"]), (m["r"] - 30, m["b"])], "master", "6 4", "MountSegment · heartbeat", 0.5, -14, "start")
    d.arrow([(c["r"], 292), (o["l"], 292)], "owner", "6 4", "P2P on :H — SegmentDesc", 0.5, -8)
    d.arrow([(c["r"], 334), (o["l"], 334)], "data", None, "TCP on :D — object bytes", 0.5, -8, sw=2.6)
    d.text(480, 392, "The object payload never passes through the master.", 13.5, INK, 600, anchor="middle")
    d.legend([("control RPC", "master", "6 4"), ("peer metadata", "owner", "6 4"), ("object bytes", "data", None)], 440)
    d.save()


# ---------------------------------------------------------------------------
# Part 1 — Master
# ---------------------------------------------------------------------------
def master_startup():
    d = Diagram("master-startup", 560, "How mooncake_master starts",
                "main() builds everything, then hands the RPC listener to its own thread.")
    d.group(32, 86, 470, 440, "main()  ·  master.cpp", "master")
    rows = [
        ("1  load config", "flags + optional --config_path → MasterConfig"),
        ("2  coro_rpc_server", "address, port, worker count — not serving yet"),
        ("3  WrappedMasterService", "constructs MasterService: state + workers"),
        ("4  MasterAdminServer::Start()", "HTTP admin routes on :9003"),
        ("5  RegisterRpcService()", "bind PutStart, MountSegment, Ping, …"),
        ("6  start serving thread", "main() then waits for a shutdown signal"),
    ]
    ys = []
    for i, (h, b) in enumerate(rows):
        y = 112 + i * 68
        d.node(50, y, 434, 54, h, [b], "master")
        ys.append(y)
        if i:
            d.line([(267, y - 14), (267, y)], ROLE["master"][0], None, 1.4, True)
    w = d.node(560, 112, 368, 172, "MasterService workers", [
        "`EvictionThreadFunc`", "`ClientMonitorFunc`", "`TaskCleanupThreadFunc`",
        "`JobDispatchThreadFunc`", "`replica_cleanup_worker_`", "`DynamicReplicationAdmissionThreadFunc`"], "neutral", size=12.5)
    d.arrow([(484, ys[2] + 27), (522, ys[2] + 27), (522, 230), (560, 230)], "neutral", None)
    d.text(492, ys[2] + 20, "start", 12.5, MUTED, 500, False, "start", True)
    a = d.node(560, 318, 368, 54, "HTTP admin  :9003", ["/health · /metrics/summary · /get_all_segments"], "neutral")
    d.arrow([(484, ys[3] + 27), (560, ys[3] + 27)], "neutral")
    r = d.node(560, ys[5], 368, 54, "server.start()  :50051", ["RPC listener — the master is now usable"], "master")
    d.arrow([(484, ys[5] + 27), (560, ys[5] + 27)], "master", None, "thread", 0.5, -7)
    d.save()


def master_class_map():
    d = Diagram("master-class-map", 660, "MasterService keeps two indexes",
                "Left: where are this key's replicas?   Right: where can a new replica be placed?")
    top = d.node(330, 86, 300, 48, "MasterService", [], "master")
    left = [
        ("metadata_shards_[s]", "1024 MetadataShard, one mutex each"),
        ("tenants[tenant_id]", "TenantState: metadata, processing_keys"),
        ("metadata[key]", "ObjectMetadata: size, writer id, lease"),
        ("replicas_[i]", "Replica: id_, status_, data_"),
        ("data_ → buffer", "MemoryReplicaData → AllocatedBuffer"),
        ("AllocatedBuffer", "buffer_ptr_ (owner address), size_"),
    ]
    right = [
        ("segment_manager_", "SegmentManager"),
        ("mounted_segments_[uuid]", "MountedSegment: segment, status"),
        ("buf_allocator", "shared_ptr to the segment's allocator"),
        ("OffsetBufferAllocator", "base, size, te_endpoint"),
        ("OffsetAllocator", "free blocks and size bins"),
    ]
    d.text(40, 172, "find a key", 12, ROLE["master"][0], 700, True)
    d.text(540, 172, "find free space", 12, ROLE["owner"][0], 700, True)
    L = []
    for i, (h, b) in enumerate(left):
        n = d.node(40, 184 + i * 72, 380, 56, h, [b], "master")
        if i:
            d.line([(230, n["t"] - 16), (230, n["t"])], ROLE["master"][0], None, 1.4, True)
        L.append(n)
    R = []
    for i, (h, b) in enumerate(right):
        n = d.node(540, 184 + i * 72, 380, 56, h, [b], "owner")
        if i:
            d.line([(730, n["t"] - 16), (730, n["t"])], ROLE["owner"][0], None, 1.4, True)
        R.append(n)
    d.line([(top["cx"] - 60, top["b"]), (top["cx"] - 60, 150), (230, 150), (230, 184)], ROLE["master"][0], None, 1.4, True)
    d.line([(top["cx"] + 60, top["b"]), (top["cx"] + 60, 150), (730, 150), (730, 184)], ROLE["owner"][0], None, 1.4, True)
    d.arrow([(L[5]["r"], L[5]["cy"]), (455, L[5]["cy"]), (455, R[3]["cy"]), (R[3]["l"], R[3]["cy"])], "neutral", "5 4")
    d.text(462, (L[5]["cy"] + R[3]["cy"]) / 2 + 4, "allocator_", 11.5, MUTED, 500, True)
    d.text(462, (L[5]["cy"] + R[3]["cy"]) / 2 + 20, "weak_ptr", 11.5, FAINT, 400, True)
    d.text(480, 640, "The master stores addresses and sizes only. The object bytes stay in the owner.", 12.5, MUTED, anchor="middle")
    d.save()


def master_key_lookup():
    d = Diagram("master-key-lookup", 560, "Put writes the record, Get follows it",
                "Example: key \"blog/example\", default tenant, one 4096-byte memory replica.")
    chain = [
        ("\"default\" + \"blog/example\"", "object identity: tenant + full key"),
        ("shard s = hash(key) % 1024", "the hash picks a shard, not an owner"),
        ("tenants[\"default\"]", "TenantState inside shard s"),
        ("metadata[\"blog/example\"]", "ObjectMetadata — full key compared"),
        ("replicas_[0]  id 101", "status PROCESSING → COMPLETE"),
        ("127.0.0.1:16001 · 0x70002000 · 4096", "Replica::Descriptor sent to the reader"),
    ]
    for i, (h, b) in enumerate(chain):
        n = d.node(250, 92 + i * 72, 460, 56, h, [b], "master")
        if i:
            d.line([(480, n["t"] - 16), (480, n["t"])], ROLE["master"][0], None, 1.4, True)
    put = d.node(32, 92, 186, 200, "PutStart", ["inserts metadata", "reserves 4096 bytes", "replica PROCESSING", "key in processing_keys"], "caller", head_mono=True)
    end = d.node(32, 310, 186, 92, "PutEnd", ["replica COMPLETE", "key leaves processing"], "caller")
    get = d.node(742, 92, 186, 310, "GetReplicaList", ["same identity", "same shard", "same tenant map", "same key", "readable replicas only", "builds descriptors", "grants a read lease"], "data")
    d.arrow([(put["r"], 120), (250, 120)], "caller")
    d.arrow([(end["r"], 412 - 48), (250, 412 - 48)], "caller")
    d.arrow([(get["l"], 120), (710, 120)], "data")
    d.arrow([(get["l"], 484), (710, 484)], "data")
    d.text(480, 536, "Different keys can share a shard; they never share an ObjectMetadata.", 12.5, MUTED, anchor="middle")
    d.save()


# ---------------------------------------------------------------------------
# Part 2 — Owner
# ---------------------------------------------------------------------------
def owner_class_map():
    rows = [
        (0, "RealClient", "Store API · owns the pool in segment_ptrs_", "owner"),
        (1, "client_buffer_allocator_", "ClientBufferAllocator — local staging", "owner"),
        (1, "client_  :  Client", "the Store client", "owner"),
        (2, "master_client_  :  MasterClient", "RPCs to the master", "master"),
        (2, "transfer_submitter_", "TransferSubmitter — uses the same engine", "neutral"),
        (2, "mounted_segments_", "UUID → Segment (owner side)", "neutral"),
        (2, "transfer_engine_  :  TransferEngine", "public transfer API", "neutral"),
        (3, "impl_  :  TransferEngineImpl", "memory regions · transports · metadata", "neutral"),
        (4, "multi_transports_  :  MultiTransport", "transport_map_[\"tcp\"]", "neutral"),
        (5, "TcpTransport", "thread_ runs the TCP event loop", "data"),
        (6, "context_  :  TcpContext", "io_context · acceptor on port D", "data"),
        (4, "metadata_  :  TransferMetadata", "shared · local + peer SegmentDesc", "owner"),
        (5, "handshake_plugin_", "SocketHandShakePlugin · listen_fd_ on port H", "owner"),
    ]
    top, step, ind = 92, 40, 34
    d = Diagram("owner-class-map", top + len(rows) * step + 64, "Inside one owner process",
                "Member names as they appear in the debugger. Indentation = \"holds\".")
    pos = []
    for i, (lvl, name, note, role) in enumerate(rows):
        y = top + i * step
        x = 40 + lvl * ind
        color = ROLE[role][0]
        w = width_of(name, 13.5, True) + 30
        d.rect(x, y, w, 28, "#ffffff", color, 5)
        d.text(x + 14, y + 19, name, 13.5, color, 600, True)
        d.text(x + w + 14, y + 19, note, 13, MUTED)
        pos.append((lvl, x, y))
    # tree connectors
    for i, (lvl, x, y) in enumerate(pos):
        if lvl == 0:
            continue
        j = max(k for k in range(i) if pos[k][0] == lvl - 1)
        px, py = pos[j][1] + 14, pos[j][2] + 28
        d.line([(px, py), (px, y + 14), (x, y + 14)], LINE, None, 1.3)
    # shared metadata
    def row_end(i):
        lvl, x, y = pos[i]
        return x + width_of(rows[i][1], 13.5, True) + 30 + 14 + width_of(rows[i][2], 13) + 12
    ty = pos[11][2]
    d.arrow([(row_end(9), pos[9][2] + 14), (800, pos[9][2] + 14), (800, ty + 14), (row_end(11), ty + 14)], "owner", "5 4")
    d.text(810, (pos[9][2] + ty) / 2 + 10, "same object", 11.5, ROLE["owner"][0], 600, True)
    d.text(810, (pos[9][2] + ty) / 2 + 25, "(shared_ptr)", 11.5, MUTED, 400, True)
    d.text(40, top + len(rows) * step + 30, "Boxes are members, not threads. Only TcpTransport::thread_ and the plugin's listener_ are extra threads.", 12.5, MUTED)
    d.save()


def owner_startup():
    d = Diagram("owner-startup", 600, "How an owner starts",
                "mooncake_client --global_segment_size='64 MB' --local_buffer_size=0 --protocol=tcp")
    d.lifelines([(110, "owner · main thread", "owner"), (820, "mooncake_master", "master")], 86, 560)
    steps = [
        ("RealClient::create()", None),
        ("Client::Create() → MasterClient::Connect()", ("ServiceReady → version", "master")),
        ("TransferEngineImpl::init()", None),
        ("TcpTransport::install()", None),
        ("allocate 64 MiB · registerLocalMemory()", None),
        ("Client::MountSegment()", ("MountSegment(Segment, client UUID)", "master")),
        ("EnsureStorageControlPlaneStarted()", ("heartbeat + task poll · every 1 s", "master")),
        ("client RPC server on :50052", None),
    ]
    notes = {2: "handshake listener on port H", 3: "TCP data listener on port D", 4: "BufferDesc added to SegmentDesc"}
    for i, (s, rpc) in enumerate(steps):
        y = 150 + i * 52
        d.step(110, y, i + 1, "owner")
        d.text(132, y + 5, s, 13.5, INK, 500, True)
        if i in notes:
            d.text(132, y + 22, notes[i], 12, MUTED)
        if rpc:
            d.arrow([(500, y), (820, y)], rpc[1], "6 4" if i != 6 else "2 3", rpc[0], 0.5, -8)
    d.text(32, 586, "Steps 1–7 run inside setup_internal(); the RPC server starts only after the pool is mounted.", 12.5, MUTED)
    d.save()


def owner_listeners():
    d = Diagram("owner-listeners", 430, "Two listeners, two ports",
                "A peer asks port H where the memory is, then sends bytes to port D.")
    d.group(32, 86, 580, 300, "owner process", "owner")
    h = d.node(56, 122, 470, 104, "SocketHandShakePlugin", ["socket: listen_fd_  ·  thread: listener_ (accept loop)",
                                                          "answers with TransferMetadata::receivePeerMetadata()",
                                                          "replies: SegmentDesc — data endpoint + buffers"], "owner")
    t = d.node(56, 252, 470, 104, "TcpContext  (owned by TcpTransport)", ["socket: acceptor  ·  thread: TcpTransport::thread_",
                                                                       "io_context.run() drives every session",
                                                                       "each connection → one ServerSession"], "data")
    for n, lab, role in [(h, "H", "owner"), (t, "D", "data")]:
        c, tint = ROLE[role]
        d.rect(592, n["cy"] - 18, 40, 36, tint, c, 6, None, 1.5)
        d.text(612, n["cy"] + 5, lab, 15, c, 700, True, "middle")
        d.line([(n["r"], n["cy"]), (592, n["cy"])], c, None, 1.4)
    p = d.node(790, 150, 140, 180, "peer client", ["Transfer Engine", "+ TCP"], "caller")
    d.arrow([(790, h["cy"]), (632, h["cy"])], "owner", "6 4", "1  get SegmentDesc", 0.5, -8)
    d.arrow([(790, t["cy"]), (632, t["cy"])], "data", None, "2  WRITE / READ", 0.5, -8, sw=2.2)
    d.text(32, 412, "H and D are chosen automatically at startup; read them from the logs.", 12.5, MUTED)
    d.save()


def owner_memory():
    d = Diagram("owner-memory", 420, "One pool, three descriptions",
                "The 64 MiB allocation exists once. Three records describe it for three audiences.")
    color, tint = ROLE["owner"]
    d.rect(80, 92, 800, 54, tint, color, 6, None, 1.5)
    d.text(100, 116, "64 MiB pool  @ 0x70000000", 15, color, 700, True)
    d.text(100, 136, "RealClient::segment_ptrs_ keeps the allocation alive", 12.5, MUTED)
    cols = [
        ("MemoryRegion", "TransferEngineImpl", ["local_memory_regions_[addr]", "lets transports touch it"], "neutral"),
        ("BufferDesc in SegmentDesc", "TransferMetadata", ["SegmentDesc::buffers", "tells peers how to reach it"], "owner"),
        ("Store Segment", "Client  →  master", ["uuid · name · base · size", "offers it as storage"], "master"),
    ]
    for i, (h, where, lines, role) in enumerate(cols):
        x = 80 + i * 280
        n = d.node(x, 220, 240, 110, h, [where] + lines, role, head_mono=True)
        d.arrow([(n["cx"], n["t"]), (n["cx"], 146)], role, "5 4")
        d.text(n["cx"] + 6, 190, f"{i + 1}", 12, ROLE[role][0], 700, True)
    d.text(480, 372, "Registering, mounting and describing never copy the pool. Only a later WRITE moves bytes.", 12.5, MUTED, anchor="middle")
    d.save()


def segment_mount_flow():
    actors = [(110, "RealClient", "owner"), (290, "Client", "owner"), (470, "TransferEngine", "owner"),
              (650, "MasterClient", "owner"), (850, "MasterService", "master")]
    d = Diagram("segment-mount-flow", 690, "Mounting a segment",
                "Register the range locally first, then announce it to the master.")
    d.lifelines(actors, 86, 660)
    y = 150
    d.msg(110, 290, y, "MountSegment(ptr, 64 MiB)", "owner"); y += 40
    d.text(298, y, "check overlap with mounted_segments_", 12, MUTED); y += 40
    d.msg(290, 470, y, "registerLocalMemory()", "owner"); y += 30
    d.text(478, y, "MemoryRegion: pending → committed", 12, MUTED); y += 18
    d.text(478, y, "TCP adds BufferDesc to SegmentDesc", 12, MUTED); y += 30
    d.msg(470, 290, y, "ok", "owner", "4 4"); y += 40
    d.text(298, y, "build Segment{uuid, name, base, size, te_endpoint}", 12, MUTED); y += 40
    d.msg(290, 650, y, "MountSegment(segment)", "owner"); y += 46
    d.msg(650, 850, y, "RPC: Segment + client UUID", "master"); y += 30
    for s in ["client UUID → client_ping_queue_", "ScopedSegmentAccess::MountSegment()",
              "  new OffsetBufferAllocator", "  insert MountedSegment + indexes"]:
        d.text(660, y, s, 12, MUTED, mono=s.startswith("  ")); y += 18
    y += 14
    d.msg(850, 290, y, "OK", "master", "4 4"); y += 44
    d.text(298, y - 6, "mounted_segments_[uuid] = segment", 12, MUTED, mono=True); y += 18
    d.text(298, y, "start heartbeat + task polling (once)", 12, MUTED)
    d.save()


def segment_mount_state():
    d = Diagram("segment-mount-state", 560, "Where a mounted segment is recorded",
                "The master keeps bookkeeping for the pool. The owner keeps the pool itself.")
    d.group(32, 86, 560, 440, "master · SegmentManager", "master")
    ms = d.node(52, 122, 300, 92, "mounted_segments_[uuid]", ["MountedSegment", "segment · status = OK", "buf_allocator"], "master")
    am = d.node(372, 122, 200, 92, "allocator_manager_", ["name →", "vector of allocators"], "master")
    oa = d.node(160, 262, 300, 76, "OffsetBufferAllocator", ["one per segment · free / reserved", "ranges inside the owner pool"], "master")
    d.arrow([(ms["cx"], ms["b"]), (ms["cx"], oa["t"])], "master")
    d.arrow([(am["cx"], am["b"]), (am["cx"], 240), (oa["r"] - 40, 240), (oa["r"] - 40, oa["t"])], "master")
    d.text(380, 234, "same object", 11.5, ROLE["master"][0], 600, True)
    d.node(52, 368, 520, 136, "other indexes", [
        "`client_segments_      client UUID → segment UUIDs`",
        "`client_by_name_       name → client UUID`",
        "`segment_id_by_name_   name → one segment UUID`",
        "`segments_by_host_     host → names → segment UUIDs`"], "neutral", size=13)
    d.group(620, 86, 308, 440, "owner process", "owner")
    p = d.node(640, 122, 268, 92, "RealClient", ["segment_ptrs_", "→ the real 64 MiB pool"], "owner")
    c = d.node(640, 262, 268, 92, "Client", ["mounted_segments_[uuid]", "→ Segment (no allocator)"], "owner")
    d.text(640, 400, "A member named mounted_segments_", 12.5, MUTED)
    d.text(640, 418, "exists on both sides with", 12.5, MUTED)
    d.text(640, 436, "different value types.", 12.5, MUTED)
    d.save()


def owner_memory_distribution():
    d = Diagram("owner-memory-distribution", 560, "Who learns about the owner's memory, and when",
                "Three processes. Only the owner holds the bytes; the others hold descriptions.")
    cols = [(40, "owner", "owner"), (360, "master", "master"), (680, "requesting client", "caller")]
    for x, label, role in cols:
        d.group(x, 86, 240, 300, label, role)
    d.node(56, 118, 208, 74, "RealClient", ["segment_ptrs_ — 64 MiB"], "owner")
    d.node(56, 204, 208, 74, "TransferEngineImpl", ["local_memory_regions_"], "owner")
    d.node(56, 290, 208, 80, "TransferMetadata", ["SegmentDesc at ID 0", "buffers[0] = the pool"], "owner")
    d.node(376, 118, 208, 74, "SegmentManager", ["MountedSegment + status"], "master")
    d.node(376, 204, 208, 90, "OffsetBufferAllocator", ["free / reserved ranges", "bookkeeping only"], "master")
    d.node(696, 118, 208, 92, "AllocatedBuffer", ["Descriptor from PutStart", "0x70002000 · 4096 bytes"], "caller")
    d.node(696, 222, 208, 92, "TransferMetadata", ["decoded owner SegmentDesc", "under a local ID, e.g. 1"], "caller")
    for x in (160, 480, 800):
        d.line([(x, 386), (x, 540)], LINE, "4 4", 1.2)
    y = 420
    d.arrow([(160, y), (480, y)], "master", "6 4", "1  MountSegment: Segment + client UUID", 0.5, -8)
    d.arrow([(480, y + 36), (800, y + 36)], "master", "6 4", "2  PutStart reply: one 4096-byte range", 0.5, -8)
    d.arrow([(800, y + 72), (160, y + 72)], "owner", "6 4", "3  P2P fetch: owner replies with its SegmentDesc", 0.5, -8)
    d.arrow([(800, y + 108), (160, y + 108)], "data", None, "4  TCP WRITE moves the bytes", 0.5, -8, sw=2.2)
    d.save()


# ---------------------------------------------------------------------------
# Part 3 — Put and Get
# ---------------------------------------------------------------------------
def client_role_workflow():
    d = Diagram("client-role-workflow", 440, "Same client stack, two roles",
                "Owner and caller run the same setup; only the memory sizes differ.")
    shared = d.node(250, 86, 460, 128, "shared setup · RealClient::setup_internal()", [
        "Client::Create() — connect to the master",
        "TransferEngineImpl::init() — handshake listener",
        "TcpTransport::install() — data listener + worker",
        "TransferSubmitter + ClientBufferAllocator",
    ], "neutral", head_mono=True)
    o = d.node(60, 280, 380, 130, "owner", ["global 64 MiB · local 0", "register + mount the global pool", "heartbeat + task polling", "then: client RPC server :50052"], "owner")
    c = d.node(520, 280, 380, 130, "caller", ["global 0 · local 16 MiB", "register the staging buffer only", "no mount, no heartbeat thread", "then: put() and get_buffer()"], "caller")
    d.arrow([(shared["cx"] - 80, shared["b"]), (o["cx"], o["t"])], "owner")
    d.arrow([(shared["cx"] + 80, shared["b"]), (c["cx"], c["t"])], "caller")
    d.save()


def put_sequence():
    d = Diagram("put-sequence", 600, "One Put, three milestones",
                "New key · one memory replica · first contact with this owner")
    xs = dict(caller=140, master=480, owner=820)
    d.lifelines([(xs["caller"], "caller", "caller"), (xs["master"], "master", "master"), (xs["owner"], "owner", "owner")], 86, 560)
    y = 160
    d.text(32, y - 16, "1", 13, ROLE["master"][0], 700, True)
    d.msg(xs["caller"], xs["master"], y, "PutStart(key, 4096 bytes)", "master"); y += 44
    d.msg(xs["master"], xs["caller"], y, "replica: 127.0.0.1:16001 · 0x70002000 · 4096", "master", "5 4"); y += 56
    d.msg(xs["caller"], xs["owner"], y, "P2P handshake on port H (first time only)", "owner"); y += 44
    d.msg(xs["owner"], xs["caller"], y, "SegmentDesc: data port D + registered buffers", "owner", "5 4"); y += 56
    d.text(32, y - 16, "2", 13, ROLE["data"][0], 700, True)
    d.msg(xs["caller"], xs["owner"], y, "TCP WRITE: header (addr, len) + 4096 bytes", "data"); y += 44
    d.msg(xs["owner"], xs["caller"], y, "v2 status: whole body received", "data", "5 4"); y += 56
    d.text(32, y - 16, "3", 13, ROLE["master"][0], 700, True)
    d.msg(xs["caller"], xs["master"], y, "PutEnd(key)", "master"); y += 44
    d.msg(xs["master"], xs["caller"], y, "OK — replica COMPLETE", "master", "5 4")
    d.text(480, 586, "1 reserve space  ·  2 move the bytes  ·  3 make the object readable", 13, INK, 600, anchor="middle")
    d.save()


def get_sequence():
    d = Diagram("get-sequence", 480, "Get for the same key",
                "Same caller, cached owner SegmentDesc, reusable TCP connection")
    xs = dict(caller=140, master=480, owner=820)
    d.lifelines([(xs["caller"], "caller", "caller"), (xs["master"], "master", "master"), (xs["owner"], "owner", "owner")], 86, 440)
    y = 160
    d.msg(xs["caller"], xs["master"], y, "GetReplicaList(key)", "master"); y += 44
    d.msg(xs["master"], xs["caller"], y, "readable replicas + lease", "master", "5 4"); y += 50
    d.text(xs["caller"] + 10, y, "SelectBestReplica() · allocate a local destination", 12, MUTED); y += 40
    d.msg(xs["caller"], xs["owner"], y, "TCP READ: header (0x70002000, 4096)", "data"); y += 44
    d.msg(xs["owner"], xs["caller"], y, "v2 status, then 4096 bytes", "data", "5 4"); y += 50
    d.text(480, y + 6, "get_buffer() returns a handle. No allocation on the owner, no PutEnd.", 13, INK, 600, anchor="middle")
    d.save()


def tcp_lanes():
    d = Diagram("tcp-lanes", 600, "One peer group, several connections",
                "Caller side: work queue and lanes.  Owner side: one listening port, one session per connection.")
    d.group(32, 86, 896, 300, "caller · PeerConnectionGroup  (key: owner host + data port D)", "caller")
    q = d.node(56, 122, 260, 92, "queue", ["work C waits", "lanes 0 and 1 are busy"], "caller")
    pump = d.node(56, 240, 260, 72, "runGroupPump()", ["assigns work to free lanes"], "caller")
    d.arrow([(q["cx"], q["b"]), (q["cx"], pump["t"])], "caller")
    for i, (x, work, op) in enumerate([(360, "A", "WRITE 4096 → 0x70002000"), (650, "B", "READ 4096 ← 0x70008000")]):
        d.rect(x, 116, 260, 250, "#ffffff", ROLE["caller"][0], 6)
        d.text(x + 14, 138, f"ConnectionLane {i}", 13.5, ROLE["caller"][0], 700, True)
        d.text(x + 14, 158, f"current = work {work} · BUSY", 12.5, MUTED)
        d.node(x + 14, 172, 232, 72, "session", ["ClientSession", op], "caller", size=12.5)
        d.node(x + 14, 262, 232, 62, f"socket  (TCP {i})", ["same object as session.socket_"], "data", size=12.5)
        d.line([(x + 130, 244), (x + 130, 262)], ROLE["caller"][0], None, 1.3, True)
        d.arrow([(x + 130, 386), (x + 130, 444)], "data", None, f"connection {i}", 0.5, 6, "start", 2.2)
    d.arrow([(pump["r"], pump["cy"]), (360, pump["cy"])], "caller", None, "assign", 0.5, -7)
    d.group(32, 444, 896, 112, "owner · TcpContext::acceptor on data port D", "owner")
    d.node(374, 478, 232, 58, "ServerSession 0", ["its own accepted socket"], "owner", size=12.5)
    d.node(664, 478, 232, 58, "ServerSession 1", ["its own accepted socket"], "owner", size=12.5)
    d.text(56, 512, "lanes_per_peer = 4 by default", 12.5, MUTED)
    d.text(56, 530, "a lane is a connection slot, not a thread", 12.5, MUTED)
    d.text(480, 584, "All lanes share the caller's single TCP worker thread and io_context.", 12.5, MUTED, anchor="middle")
    d.save()


def asio_flow():
    d = Diagram("asio-flow", 610, "From posted work to a running session",
                "Everything on the right runs on one thread: TcpTransport::worker() inside io_context.run().")
    d.lifelines([(150, "submitting thread", "caller"), (520, "TCP worker · io_context", "data"), (840, "OS / resolver", "neutral")], 86, 576)
    y = 156
    d.msg(150, 520, y, "asio::post(group->executor, runGroupPump)", "caller"); y += 40
    rows = [
        ("runGroupPump()", "lane needs a connection → startLaneConnect()", "async_resolve()", True),
        ("handleLaneResolved()", "", "async_connect()", True),
        ("handleLaneConnected()", "lane is usable", None, False),
        ("startLaneSession()", "ClientSession: async header + body I/O", "socket I/O", True),
        ("handleLaneTerminal()", "update task · reuse lane · pump again", None, False),
    ]
    for head, note, out, back in rows:
        c, tint = ROLE["data"]
        w = width_of(head, 13, True) + 24
        d.rect(520 - w / 2, y - 16, w, 26, tint, c, 5)
        d.text(520, y + 1.5, head, 13, c, 600, True, "middle")
        if note:
            d.text(520, y + 26, note, 12, MUTED, anchor="middle")
        if out:
            d.arrow([(520 + w / 2, y - 3), (840, y - 3)], "neutral", None, out, 0.5, -7)
            d.arrow([(840, y + 52), (520, y + 52)], "neutral", "4 4", "completion handler", 0.5, -7)
            y += 92
        else:
            y += 62
    d.text(32, 596, "post() only queues a handler. Callbacks run later on the worker; \"step into\" cannot follow them.", 12.5, MUTED)
    d.save()


def tcp_write():
    d = Diagram("tcp-write", 470, "A TCP WRITE between two sessions",
                "Protocol v2 · CPU memory · the order the caller waits for")
    d.lifelines([(180, "ClientSession · caller", "caller"), (620, "ServerSession · owner", "owner")], 86, 400)
    y = 160
    d.msg(180, 620, y, "header: WRITE · 0x70002000 · 4096", "data"); y += 32
    d.text(628, y, "readHeader() · check range is registered", 12, MUTED); y += 40
    d.msg(180, 620, y, "body: 4096 bytes from the staging buffer", "data"); y += 32
    d.text(628, y, "readBody() → owner memory 0x70002000", 12, MUTED); y += 40
    d.msg(620, 180, y, "status: success (after the full body)", "owner", "5 4"); y += 32
    d.text(628, y, "wait for the next header on this socket", 12, MUTED)
    d.text(480, 424, "Done = body written AND status received. Then the caller sends PutEnd to the master.", 13, INK, 600, anchor="middle")
    d.save()


ALL = [cluster, master_startup, master_class_map, master_key_lookup, owner_class_map, owner_startup,
       owner_listeners, owner_memory, segment_mount_flow, segment_mount_state, owner_memory_distribution,
       client_role_workflow, put_sequence, get_sequence, tcp_lanes, asio_flow, tcp_write]

if __name__ == "__main__":
    for f in ALL:
        f()
    for w in WARN:
        print("overflow?", w)
    print(f"wrote {len(ALL)} diagrams")
