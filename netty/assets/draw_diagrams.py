"""Regenerate the Netty diagrams drawn in the series style (not the author's drawio figures).

Run: python3 netty/assets/draw_diagrams.py
Reuses the toolkit in mooncake/assets/draw_diagrams.py so both series look the same.
Colours: main/application thread blue · event loop orange · pipeline/handlers purple · data green.
"""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mc", HERE.parent.parent / "mooncake/assets/draw_diagrams.py")
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)
mc.OUT = HERE
Diagram, ROLE, MUTED, FAINT, INK, LINE, PANEL = mc.Diagram, mc.ROLE, mc.MUTED, mc.FAINT, mc.INK, mc.LINE, mc.PANEL


def server_startup():
    d = Diagram("server-startup-01", 640, "How a Netty server starts",
                "serverBootstrap.bind(port): the main thread builds the channel, the boss event loop does the rest.")
    d.lifelines([(200, "main thread", "master"), (680, "boss event loop", "data")], 86, 600)
    y = 156
    rows = [
        ("bind(port) → initAndRegister()", None),
        ("new NioServerSocketChannel()", "Java ServerSocketChannel · readInterestOp = OP_ACCEPT · pipeline"),
        ("init(channel)", "adds a ChannelInitializer; its handlerAdded waits (not registered yet)"),
    ]
    for i, (s, note) in enumerate(rows):
        d.step(60, y, i + 1, "master")
        d.text(80, y + 5, s, 13.5, INK, 500, True)
        if note:
            d.text(80, y + 23, note, 12, MUTED)
        y += 54
    d.step(60, y, 4, "master")
    d.text(80, y + 5, "register(channel)", 13.5, INK, 500, True)
    d.arrow([(260, y), (600, y)], "data", None, "register task (starts the loop's thread)", 0.5, -8)
    d.text(700, y + 5, "register0()", 13.5, ROLE["data"][0], 600, True)
    for j, s in enumerate(["register with the selector", "pending handlerAdded → initChannel()", "  → task adds ServerBootstrapAcceptor", "fireChannelRegistered"]):
        d.text(700, y + 24 + j * 17, s, 12, MUTED, mono=s.startswith("  "))
    y += 104
    d.step(60, y, 5, "master")
    d.text(80, y + 5, "doBind0()", 13.5, INK, 500, True)
    d.arrow([(260, y), (600, y)], "data", None, "bind task", 0.5, -8)
    d.text(700, y + 5, "pipeline.bind", 13.5, ROLE["data"][0], 600, True)
    for j, s in enumerate(["tail → … → HeadContext", "unsafe.bind → doBind (Java bind)", "fireChannelActive"]):
        d.text(700, y + 24 + j * 17, s, 12, MUTED)
    y += 90
    d.text(700, y + 5, "HeadContext.read", 13.5, ROLE["data"][0], 600, True)
    for j, s in enumerate(["unsafe.beginRead → doBeginRead", "interestOps |= OP_ACCEPT"]):
        d.text(700, y + 24 + j * 17, s, 12, MUTED)
    d.text(480, 626, "From now on the boss loop's selector reports new connections; ServerBootstrapAcceptor hands each one to workerGroup.", 12.5, MUTED, anchor="middle")
    d.save()


def socket_write():
    d = Diagram("socket-write-01", 470, "ChannelOutboundBuffer: write queues, flush sends",
                "A linked list of Entry nodes. Three pointers split it into flushed and unflushed messages.")
    xs = [70, 230, 390, 550, 710]
    for i, x in enumerate(xs):
        flushed = i < 2
        role = "caller" if flushed else "owner"
        c, tint = ROLE[role]
        d.rect(x, 200, 130, 56, tint, c, 6, None, 1.4)
        d.text(x + 65, 224, f"Entry {i + 1}", 13.5, c, 700, True, "middle")
        d.text(x + 65, 243, "flushed" if flushed else "unflushed", 12, MUTED, anchor="middle")
        if i < 4:
            d.arrow([(x + 130, 228), (xs[i + 1], 228)], "neutral", None)
    for x, label, role in [(xs[0], "flushedEntry", "caller"), (xs[2], "unflushedEntry", "owner"), (xs[4], "tailEntry", "owner")]:
        d.text(x + 65, 150, label, 13, ROLE[role][0], 600, True, "middle")
        d.arrow([(x + 65, 158), (x + 65, 198)], role)
    d.text(xs[4] + 150, 222, "← write(msg)", 13, ROLE["master"][0], 600, True)
    d.text(xs[4] + 150, 240, "appends here", 12, MUTED)
    d.line([(xs[2] - 15, 120), (xs[2] - 15, 290)], ROLE["owner"][0], "5 4", 1.4)
    d.text(xs[2] - 15, 306, "flush() → addFlush(): this boundary moves to the tail", 12.5, ROLE["owner"][0], 600, False, "middle")
    d.text(70, 346, "doWrite():", 13, INK, 600, True)
    d.text(160, 346, "nioBuffers() turns flushed entries into ByteBuffer[] → SocketChannel.write() → removeBytes()", 12.5, MUTED)
    # watermark gauge
    d.text(70, 392, "totalPendingSize", 13, INK, 600, True)
    d.rect(230, 380, 600, 18, PANEL, LINE, 4)
    d.rect(230, 380, 430, 18, ROLE["data"][1], ROLE["data"][0], 4)
    for x, lab in [(470, "low watermark"), (650, "high watermark")]:
        d.line([(x, 372), (x, 406)], INK, None, 1.4)
        d.text(x, 424, lab, 12, MUTED, anchor="middle")
    d.text(230, 452, "above high → channel unwritable · back below low → writable again (channelWritabilityChanged)", 12.5, MUTED)
    d.save()


def message_framing():
    d = Diagram("message-framing-01", 520, "TCP keeps bytes, not boundaries",
                "Three writes can arrive as reads that split or merge them. A length field lets the decoder cut frames.")
    cols = {"M1": ("caller", 70, 260), "M2": ("master", 330, 150), "M3": ("owner", 480, 200)}
    d.text(32, 116, "writes", 12.5, MUTED, 600, True)
    for name, (role, x, w) in cols.items():
        c, tint = ROLE[role]
        d.rect(x + 40, 100, w - 8, 30, tint, c, 4, None, 1.3)
        d.text(x + 40 + (w - 8) / 2, 120, name, 13, c, 700, True, "middle")
    d.text(32, 186, "reads", 12.5, MUTED, 600, True)
    reads = [(110, 150, [("M1 (part)", "caller", 150)]),
             (270, 260, [("M1 (rest)", "caller", 102), ("M2", "master", 150)]),
             (540, 200, [("M3", "owner", 192)])]
    for i, (x, w, parts) in enumerate(reads):
        d.rect(x - 4, 162, w + 8, 44, "#ffffff", LINE, 6, "4 3")
        px = x
        for lab, role, pw in parts:
            c, tint = ROLE[role]
            d.rect(px, 170, pw - 4, 28, tint, c, 4, None, 1.2)
            d.text(px + (pw - 4) / 2, 189, lab, 12, c, 600, True, "middle")
            px += pw
        d.text(x + w / 2, 224, f"read {i + 1}", 12, MUTED, anchor="middle")
    d.text(800, 180, "fragmented", 12.5, MUTED)
    d.text(800, 198, "and coalesced", 12.5, MUTED)
    # frame layout
    d.text(32, 286, "LengthFieldBasedFrameDecoder", 14, INK, 700, True)
    d.text(32, 306, "example: lengthFieldOffset = 2, lengthFieldLength = 4, lengthAdjustment = 0, initialBytesToStrip = 6", 12.5, MUTED)
    segs = [("header", 2, "neutral"), ("length = 12", 4, "data"), ("body · 12 bytes", 12, "caller")]
    x, unit = 110, 38
    for lab, n, role in segs:
        c, tint = ROLE[role]
        w = n * unit if n > 2 else n * unit + 30
        d.rect(x, 330, w, 40, tint, c, 4, None, 1.4)
        d.text(x + w / 2, 355, lab, 12.5, c, 600, True, "middle")
        d.text(x + w / 2, 390, f"{n} bytes", 11.5, FAINT, 400, True, "middle")
        x += w
    d.line([(110, 410), (110, 440)], INK, None, 1)
    d.line([(216, 410), (216, 440)], INK, None, 1)
    d.arrow([(110, 428), (216, 428)], "neutral")
    d.text(163, 456, "lengthFieldOffset", 11.5, MUTED, 500, True, "middle")
    d.text(32, 494, "frame length = lengthFieldOffset + lengthFieldLength + length + lengthAdjustment = 18 · initialBytesToStrip only changes what is delivered (here: just the body)", 12, MUTED)
    d.save()


def handle_bits():
    d = Diagram("pooled-memory-13", 330, "Legacy subpage handle (Netty 4.1.50)",
                "One long identifies a subpage unit: which page in the chunk, and which unit in that page.")
    segs = [("63", "unused", 70, "neutral"), ("62", "subpage marker", 130, "data"),
            ("61 … 32", "bitmapIdx: unit inside the page", 330, "owner"), ("31 … 0", "memoryMapIdx: page in the buddy tree", 330, "master")]
    x = 50
    for bits, lab, w, role in segs:
        c, tint = ROLE[role]
        d.rect(x, 96, w, 76, tint, c, 4, None, 1.4)
        d.text(x + w / 2, 122, f"bits {bits}", 13, c, 700, True, "middle")
        words = lab.split(": ")
        d.text(x + w / 2, 146, words[0], 13, INK, 600, False, "middle")
        if len(words) > 1:
            d.text(x + w / 2, 163, words[1], 12, MUTED, 400, False, "middle")
        x += w
    d.text(50, 222, "handle = 0x4000000000000000L | (long) bitmapIdx << 32 | memoryMapIdx", 14, INK, 600, True)
    d.text(50, 252, "0x4000000000000000L is 2^62: it marks a subpage handle, so a handle is never 0 even for unit 0.", 12.5, MUTED)
    d.text(50, 274, "Offset of the unit = runOffset(memoryMapIdx) + (bitmapIdx & 0x3FFFFFFF) × elemSize + chunk offset.", 12.5, MUTED)
    d.text(50, 304, "4.1.53 replaced this layout: its handles encode run offset, page count, used/subpage flags and bitmap index.", 12, FAINT)
    d.save()


def reference_flow():
    d = Diagram("java-reference-processing-04", 470, "From the GC to your ReferenceQueue",
                "OpenJDK 8: the JVM builds the pending list; the Reference Handler thread empties it one reference at a time.")
    gc = d.node(40, 100, 230, 92, "GC (JVM)", ["discovers soft / weak /", "phantom references whose", "referent became unreachable"], "neutral")
    pl = d.node(330, 100, 300, 92, "Reference.pending", ["head of the pending list", "next ones linked via .discovered", "guarded by Reference.lock"], "data")
    rh = d.node(330, 240, 300, 92, "Reference Handler thread", ["loop: tryHandlePending(true)", "take one r, unlink it", "wait() when the list is empty"], "master")
    cl = d.node(690, 100, 240, 76, "Cleaner", ["c.clean() — e.g. frees", "DirectByteBuffer memory"], "owner")
    q = d.node(690, 220, 240, 76, "ReferenceQueue", ["q.enqueue(r)", "if r.queue != NULL"], "caller")
    app = d.node(690, 340, 240, 76, "application", ["queue.poll() / remove()", "gets the Reference object"], "caller")
    d.arrow([(gc["r"], gc["cy"]), (pl["l"], pl["cy"])], "neutral", None, "fills", 0.5, -8)
    d.arrow([(pl["cx"], pl["b"]), (rh["cx"], rh["t"])], "data", None, "take head", 0.5, 4, "start")
    d.arrow([(rh["r"], rh["cy"] - 20), (660, rh["cy"] - 20), (660, cl["cy"]), (cl["l"], cl["cy"])], "owner", None)
    d.text(642, 196, "Cleaner?", 12, ROLE["owner"][0], 600, False, "end")
    d.arrow([(rh["r"], q["cy"] + 10), (q["l"], q["cy"] + 10)], "caller", None)
    d.text(642, 300, "otherwise", 12, ROLE["caller"][0], 600, False, "end")
    d.arrow([(q["cx"], q["b"]), (app["cx"], app["t"])], "caller")
    d.text(40, 400, "With no queue (ReferenceQueue.NULL) the reference is simply dropped.", 12.5, MUTED)
    d.text(40, 420, "Cleared or enqueued does not mean the memory is already reclaimed.", 12.5, MUTED)
    d.save()


# ---------------------------------------------------------------------------
# Redraws of the author's original drawio figures (same content, series style).
# Roles here: thread/allocator blue · handler/chunk purple · queue/page/DMA orange · data/units green.
# ---------------------------------------------------------------------------
M, LH, NET, F, N = "master", "owner", "data", "caller", "neutral"


def two_way(d, pts, role, dash=None):
    d.line(pts, ROLE[role][0], dash, 1.6, True)
    d.parts[-1] = d.parts[-1].replace("marker-end=", 'marker-start="url(#a-%s)" marker-end=' % ROLE[role][0][1:])


def fields(d, x, y, w, title, names, role, note=None):
    """A record box: coloured title, then one mono row per field. Returns {name: (left, right, cy)} and the box."""
    c, tint = ROLE[role]
    h = 30 + len(names) * 26 + 6
    d.rect(x, y, w, h, tint, c, 6, None, 1.3)
    d.text(x + 10, y + 19, title, 13, c, 700, True)
    if note:
        d.text(x + w - 10, y + 19, note, 11.5, MUTED, 400, False, "end")
    rows = {}
    for i, n in enumerate(names):
        ry = y + 30 + i * 26
        d.rect(x + 8, ry, w - 16, 22, "#ffffff", LINE, 4)
        d.text(x + 18, ry + 15.5, n, 12.5, INK, 500, True)
        rows[n] = (x + 8, x + w - 8, ry + 11)
    return rows, dict(l=x, r=x + w, t=y, b=y + h, cx=x + w / 2, cy=y + h / 2)


def cells(d, x, y, n, cw, ch, role, filled):
    c, tint = ROLE[role]
    for i in range(n):
        d.rect(x + i * cw, y, cw, ch, tint if i < filled else "#ffffff", c, 2, None, 1)


def hchain(d, boxes, role, label=None):
    for a, b in zip(boxes, boxes[1:]):
        d.arrow([(a["r"], a["cy"]), (b["l"], b["cy"])], role, None, label)


# --- socket read --------------------------------------------------------------
def size_table():
    d = Diagram("socket-read-01", 330, "SIZE_TABLE: 53 candidate buffer sizes",
                "AdaptiveRecvByteBufAllocator chooses the next read buffer size from this table.")
    small = [("16", 0), ("32", 1), ("48", 2), ("…", None), ("496", 30)]
    large = [("512", 31), ("1024", 32), ("2048", 33), ("…", None), ("1073741824", 52)]
    d.group(32, 92, 380, 128, "multiples of 16 · 31 entries", F)
    d.group(432, 92, 496, 128, "powers of two · 22 entries", NET)
    for i, (v, idx) in enumerate(small):
        x = 46 + i * 72
        if idx is None:
            d.text(x + 30, 162, "…", 16, MUTED, 700, False, "middle")
            continue
        d.box(x, 136, 60, 40, [v], F, 13, True, False, "#ffffff")
        d.text(x + 30, 196, f"[{idx}]", 11.5, MUTED, 400, True, "middle")
    for i, (v, idx) in enumerate(large):
        w = 120 if idx == 52 else 72
        x = 446 + i * 84
        if idx is None:
            d.text(x + 36, 162, "…", 16, MUTED, 700, False, "middle")
            continue
        d.box(x, 136, w, 40, [v], NET, 13, True, False, "#ffffff")
        d.text(x + w / 2, 196, f"[{idx}]" + (" = 2^30" if idx == 52 else ""), 11.5, MUTED, 400, True, "middle")
    d.arrow([(60, 254), (240, 254)], F, None, None)
    d.text(252, 258, "the read filled the buffer → index + 4  (grow fast)", 13, INK)
    d.arrow([(240, 290), (60, 290)], NET, None, None)
    d.text(252, 294, "two small reads in a row → index − 1  (shrink slowly)", 13, INK)
    d.save()


# --- recycler -------------------------------------------------------------------
def recycler_map():
    d = Diagram("recycler-01", 640, "Where recycled objects wait",
                "Each thread owns a Stack. Other threads hand objects back through WeakOrderQueues linked from it.")
    t1 = d.box(32, 112, 120, 50, ["Thread 1", "owns the Stack"], M, 12.5)
    rows, st = fields(d, 196, 90, 250, "Stack", ["elements", "cursor", "prev", "head"], M, "thread 1")
    d.arrow([(t1["r"], t1["cy"]), (st["l"], t1["cy"])], M)
    l, r, y = rows["elements"]
    d.text(500, 112, "DefaultHandle[] elements", 12, ROLE[M][0], 600, True)
    cells(d, 500, 122, 8, 26, 22, M, 5)
    d.arrow([(r, y), (500, y)], M)
    d.text(500, 166, "handles ready for get()", 12, MUTED)
    d.group(744, 90, 184, 122, "Thread 2 … N", N)
    d.text(758, 136, "each has its own", 12.5, INK)
    d.text(758, 156, "Stack as well", 12.5, INK)
    cols = [(32, "thread n"), (350, "thread n−1"), (668, "thread 2")]
    woq = []
    for x, who in cols:
        rws, b = fields(d, x, 300, 260, "WeakOrderQueue", ["head", "tail", "next", "id"], F, "from " + who)
        woq.append((rws, b))
    l, r, hy = rows["head"]
    d.arrow([(l, hy), (176, hy), (176, 300)], M, None, "head", 0.5, -6, "end")
    for (ra, a), (rb, b) in zip(woq, woq[1:]):
        _, rr, ny = ra["next"]
        d.arrow([(rr, ny), (b["l"], ny)], F, None, "next", 0.5, -7)
    d.text(940, 0, "", 1)
    for (rws, b), (x, _) in zip(woq, cols):
        k1 = d.box(x, 486, 112, 74, [], NET)
        k2 = d.box(x + 148, 486, 112, 74, [], NET)
        for k in (k1, k2):
            d.text(k["l"] + 10, k["t"] + 19, "Link", 13, ROLE[NET][0], 700, True)
            cells(d, k["l"] + 10, k["t"] + 30, 6, 15, 16, NET, 4 if k is k1 else 2)
            d.text(k["l"] + 10, k["t"] + 64, "elements[16]", 11, MUTED, 400, True)
        d.arrow([(k1["r"], k1["cy"]), (k2["l"], k2["cy"])], NET, None, "next", 0.5, -6)
        d.arrow([(k1["cx"], b["b"]), (k1["cx"], k1["t"])], F, None, "head.link", 0.5, 4, "start")
        d.arrow([(k2["cx"], b["b"]), (k2["cx"], k2["t"])], F, None, "tail", 0.5, 4, "start")
    d.text(32, 600, "Thread 1 pops from elements[]. When it runs out, scavenge() moves handles from these Links back into elements[].", 12.5, MUTED)
    d.text(32, 620, "Each other thread appends to its own Link chain, so returning an object needs no lock on the Stack.", 12.5, MUTED)
    d.save()


def recycle_call():
    d = Diagram("recycler-05", 210, "Recycle an object", "The object goes back through its handle to the Stack it came from.")
    bs = [d.box(32 + i * 312, 100, 270, 54, [s, n], c, 13) for i, (s, n, c) in enumerate([
        ("`obj.recycle()`", "user code, any thread", F),
        ("`handle.recycle(obj)`", "DefaultHandle", NET),
        ("`stack.push(handle)`", "the Stack that created it", M)])]
    hchain(d, bs, N)
    d.save()


def push_choice():
    d = Diagram("recycler-06", 296, "Stack.push picks a path", "Same thread: store directly. Another thread: go through a WeakOrderQueue.")
    p = d.box(32, 140, 150, 50, ["`push(handle)`"], N)
    q = d.diamond(370, 165, 250, 92, ["threadRef.get() ==", "currentThread?"], N)
    a = d.box(640, 96, 288, 58, ["`pushNow()`", "owner thread: put in elements[]"], M, 12.5)
    b = d.box(640, 178, 288, 58, ["`pushLater()`", "other thread: add to its WeakOrderQueue"], F, 12.5)
    d.arrow([(p["r"], p["cy"]), (q["l"], q["cy"])], N)
    d.arrow([(q["r"], q["cy"]), (560, q["cy"]), (560, a["cy"]), (a["l"], a["cy"])], M)
    d.arrow([(q["r"], q["cy"]), (560, q["cy"]), (560, b["cy"]), (b["l"], b["cy"])], F)
    d.label(600, a["cy"] - 7, "yes", M)
    d.label(600, b["cy"] - 7, "no", F)
    d.text(32, 276, "pushLater() creates the queue for this (stack, thread) pair on first use and links it at stack.head.", 12.5, MUTED)
    d.save()


def get_call():
    d = Diagram("recycler-07", 250, "Get an object", "ObjectPool.get() delegates to Recycler.get(), which pops a handle or makes a new object.")
    a = d.box(32, 100, 190, 54, ["`ObjectPool.get()`", "RecyclerObjectPool"], LH)
    b = d.box(262, 100, 190, 54, ["`Recycler.get()`", "this thread's Stack"], M)
    c = d.box(492, 100, 190, 54, ["`stack.pop()`", "scavenge if empty"], M)
    e = d.box(722, 100, 206, 54, ["return handle.value"], F)
    n = d.box(492, 182, 436, 44, ["`newHandle() + newObject(handle)`"], N, 12.5)
    hchain(d, [a, b, c, e], N)
    d.arrow([(c["cx"], c["b"]), (c["cx"], n["t"])], N, None, "null", 0.5, 4, "start")
    d.arrow([(n["r"] - 103, n["t"]), (n["r"] - 103, e["b"])], N)
    d.save()


def scavenge_list():
    d = Diagram("recycler-08", 330, "Dead and live queues during scavenging",
                "Queues whose producer thread died stay linked if they sit before any live queue, because there is no prev to unlink through.")
    h = d.box(32, 160, 96, 44, ["stack.head"], M, 12.5)
    nodes = []
    for i, dead in enumerate([True, True, False, False, False]):
        x = 160 + i * 140
        lines = ["WeakOrderQueue", "producer dead" if dead else "producer alive"]
        nodes.append(d.box(x, 152, 116, 60, lines, N if dead else F, 12))
    d.text(890, 187, "…", 18, MUTED, 700, False, "middle")
    hchain(d, [h] + nodes, N)
    d.arrow([(nodes[-1]["r"], 182), (870, 182)], N)
    for k, name in [(2, "prev"), (3, "cursor")]:
        t = d.tag(nodes[k]["cx"] - 24, 104, name, M)
        d.arrow([(nodes[k]["cx"], 124), (nodes[k]["cx"], 152)], M)
    l, r = nodes[0]["l"], nodes[1]["r"]
    d.line([(l, 228), (l, 236), (r, 236), (r, 228)], MUTED, None, 1.2)
    d.text((l + r) / 2, 256, "no live queue before them:", 12, MUTED, 500, False, "middle")
    d.text((l + r) / 2, 273, "stay linked (head is never replaced)", 12, MUTED, 500, False, "middle")
    l, r = nodes[2]["l"], nodes[4]["r"]
    d.line([(l, 228), (l, 236), (r, 236), (r, 228)], ROLE[F][0], None, 1.2)
    d.text((l + r) / 2, 256, "a dead queue after a live one is drained", 12, ROLE[F][0], 500, False, "middle")
    d.text((l + r) / 2, 273, "and unlinked through prev", 12, ROLE[F][0], 500, False, "middle")
    d.save()


# --- thread model -----------------------------------------------------------------
def reactor():
    d = Diagram("thread-model-01", 450, "Reactor roles in a Netty NIO server",
                "One boss loop accepts connections. Each accepted channel is handed to one worker loop for its whole life.")
    xs = [120, 260, 400, 560, 840]
    for x in xs:
        d.circle(x, 112, 26, ["client"], N, 10.5)
        d.arrow([(x, 138), (x, 196)], N)
    d.text(700, 116, "…", 18, MUTED, 700, False, "middle")
    acc = d.box(32, 196, 896, 54, ["boss event loop · acceptor", "OP_ACCEPT → new NioSocketChannel"], M)
    d.tag(820, 212, "1 thread", M)
    d.arrow([(480, acc["b"]), (480, 300)], M, None, "register with a worker loop", 0.5, 4, "start")
    d.group(32, 300, 896, 130, "worker group", NET)
    for i in range(4):
        x = 56 + i * 212
        d.box(x, 336, 180, 60, ["NioSocketChannel", "bound to one loop"], NET, 12.5)
        d.tag(x + 46, 402, "worker thread", NET)
    d.save()


def event_loop_work():
    d = Diagram("thread-model-02", 290, "Three kinds of NioEventLoop work", "One thread runs all three, in turn, inside run().")
    d.group(32, 86, 896, 180, "NioEventLoop · one thread", NET)
    a = d.box(60, 126, 250, 60, ["selector", "I/O readiness events"], M)
    b = d.box(355, 126, 250, 60, ["taskQueue", "ordinary tasks"], LH)
    c = d.box(650, 126, 250, 60, ["scheduledTaskQueue", "tasks with a deadline"], F)
    hchain(d, [a, b, c], NET)
    d.arrow([(c["cx"], c["b"]), (c["cx"], 222), (a["cx"], 222), (a["cx"], a["b"])], NET, "5 4")
    d.label(480, 248, "loop: select() → processSelectedKeys() → runAllTasks()", NET, 12.5)
    d.save()


# --- pipeline ----------------------------------------------------------------------
def pipeline_directions():
    d = Diagram("pipeline-01", 320, "Inbound and outbound directions",
                "Contexts form a doubly linked list. Inbound events skip outbound handlers, and the reverse.")
    names = ["head", "In 1", "Out 1", "In 2", "Out 2", "In 3", "Out 3", "In 4", "tail"]
    bs = {}
    for i, n in enumerate(names):
        role = N if n in ("head", "tail") else (F if n.startswith("In") else LH)
        bs[n] = d.box(32 + i * 104, 160, 76, 44, [n], role, 13)
    for a, b in zip(names, names[1:]):
        two_way(d, [(bs[a]["r"] + 2, 182), (bs[b]["l"] - 2, 182)], N)
    inb = ["head", "In 1", "In 2", "In 3", "In 4", "tail"]
    for a, b in zip(inb, inb[1:]):
        d.arrow([(bs[a]["cx"], 160), (bs[a]["cx"], 132), (bs[b]["cx"], 132), (bs[b]["cx"], 160)], F)
    d.text(480, 116, "inbound (read): head → tail, InboundHandlers only", 13, ROLE[F][0], 600, False, "middle")
    out = ["tail", "Out 3", "Out 2", "Out 1", "head"]
    for a, b in zip(out, out[1:]):
        d.arrow([(bs[a]["cx"], 204), (bs[a]["cx"], 232), (bs[b]["cx"], 232), (bs[b]["cx"], 204)], LH)
    d.text(480, 258, "outbound (write): tail → head, OutboundHandlers only", 13, ROLE[LH][0], 600, False, "middle")
    d.text(32, 300, "HeadContext is both inbound and outbound: outbound operations end there and reach the socket.", 12.5, MUTED)
    d.save()


def pipeline_propagation():
    d = Diagram("pipeline-02", 420, "How an inbound event moves from context to context",
                "channelRead shown; every inbound event follows the same pattern.")
    start = d.box(32, 92, 250, 40, ["`pipeline.fireChannelRead(msg)`"], N, 12)
    prev = None
    for i, name in enumerate(["head", "ctx1", "ctx2"]):
        x = 32 + i * 320
        d.group(x, 156, 250, 196, name, LH)
        b1 = d.box(x + 14, 190, 222, 40, ["`invokeChannelRead(msg)`"], LH, 11.5, strong=False, fill="#ffffff")
        b2 = d.box(x + 14, 244, 222, 40, ["`handler.channelRead(ctx, msg)`"], LH, 11.5, strong=False, fill="#ffffff")
        b3 = d.box(x + 14, 298, 222, 40, ["`ctx.fireChannelRead(msg)`"], LH, 11.5, strong=False, fill="#ffffff")
        d.arrow([(b1["cx"], b1["b"]), (b2["cx"], b2["t"])], LH)
        d.arrow([(b2["cx"], b2["b"]), (b3["cx"], b3["t"])], LH)
        if prev is None:
            d.arrow([(start["cx"], start["b"]), (start["cx"], b1["t"])], N)
        else:
            gx = x - 40
            d.arrow([(prev["r"], prev["cy"]), (gx, prev["cy"]), (gx, b1["cy"]), (b1["l"], b1["cy"])], N)
        prev = b3
    d.arrow([(prev["r"], prev["cy"]), (944, prev["cy"])], N)
    d.text(32, 384, "Between contexts, findContextInbound() walks next and skips handlers that do not handle the event (executionMask).", 12.5, MUTED)
    d.text(32, 404, "The handler must call ctx.fireChannelRead() itself; otherwise the event stops at that handler.", 12.5, MUTED)
    d.save()


# --- zero copy ------------------------------------------------------------------------
def spaces(d, h):
    bands = [("user space", 90, 190), ("kernel space", 190, 330), ("hardware", 330, h - 40)]
    for i, (lab, y0, y1) in enumerate(bands):
        d.text(40, (y0 + y1) / 2 + 4, lab, 13, MUTED, 600, True)
        if i:
            d.line([(32, y0), (928, y0)], LINE, "6 5", 1.2)


def copy(d, a, b, kind, label, pts=None, at=0.5, anchor="start", dx=8):
    role = NET if kind == "DMA" else (M if kind == "CPU" else LH)
    pts = pts or [(a["cx"], a["t"] if a["cy"] > b["cy"] else a["b"]), (b["cx"], b["b"] if a["cy"] > b["cy"] else b["t"])]
    d.arrow(pts, role, "6 4" if kind == "shared" else None)
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    d.label(x1 + (x2 - x1) * at + dx, y1 + (y2 - y1) * at + 4, label, role, 12.5, anchor)


def zc_traditional():
    d = Diagram("java-zero-copy-01", 470, "Traditional read + write", "Sending a file with read() then write(): two CPU copies and two DMA copies.")
    spaces(d, 470)
    u = d.box(390, 112, 180, 50, ["user buffer"], N)
    pc = d.box(220, 236, 170, 50, ["page cache"], NET)
    sb = d.box(600, 236, 170, 50, ["socket buffer"], NET)
    disk = d.box(220, 364, 170, 50, ["disk"], N)
    net = d.box(600, 364, 170, 50, ["network card"], N)
    copy(d, disk, pc, "DMA", "① DMA copy")
    d.arrow([(pc["cx"], pc["t"]), (pc["cx"], u["cy"]), (u["l"], u["cy"])], M)
    d.label(pc["cx"] - 10, 204, "② CPU copy (read)", M, 12.5, "end")
    d.arrow([(u["r"], u["cy"]), (sb["cx"], u["cy"]), (sb["cx"], sb["t"])], M)
    d.label(sb["cx"] + 10, 204, "③ CPU copy (write)", M, 12.5, "start")
    copy(d, sb, net, "DMA", "④ DMA copy")
    d.save()


def zc_sendfile():
    d = Diagram("java-zero-copy-02", 470, "sendfile()", "The data stays in the kernel: one CPU copy between kernel buffers and two DMA copies.")
    spaces(d, 470)
    u = d.box(390, 112, 180, 50, ["user buffer", "not used"], N)
    d.parts[-3] = d.parts[-3].replace('stroke-width="1.3"', 'stroke-width="1.3" stroke-dasharray="5 4" opacity="0.6"')
    pc = d.box(220, 236, 170, 50, ["page cache"], NET)
    sb = d.box(600, 236, 170, 50, ["socket buffer"], NET)
    disk = d.box(220, 364, 170, 50, ["disk"], N)
    net = d.box(600, 364, 170, 50, ["network card"], N)
    copy(d, disk, pc, "DMA", "① DMA copy")
    d.arrow([(pc["r"], pc["cy"]), (sb["l"], sb["cy"])], M, None, "② CPU copy", 0.5, -8)
    copy(d, sb, net, "DMA", "③ DMA copy")
    d.text(32, 456, "Java: FileChannel.transferTo(). With scatter-gather DMA the CPU copy can shrink to file descriptors only.", 12.5, MUTED)
    d.save()


def zc_read():
    d = Diagram("java-zero-copy-03", 460, "Ordinary read()", "The kernel reads the file into the page cache, then the CPU copies it into user memory.")
    spaces(d, 460)
    u = d.box(380, 112, 200, 50, ["user memory"], N)
    pc = d.box(330, 236, 300, 50, ["page cache"], NET)
    disk = d.box(395, 364, 170, 50, ["disk"], N)
    copy(d, disk, pc, "DMA", "① DMA copy")
    copy(d, pc, u, "CPU", "② CPU copy")
    d.save()


def zc_mmap():
    d = Diagram("java-zero-copy-04", 460, "mmap()", "User memory is mapped onto the page cache: both sides see the same pages, no CPU copy.")
    spaces(d, 460)
    u = d.box(380, 112, 200, 50, ["user memory", "mapped region"], LH)
    pc = d.box(330, 236, 300, 50, [], NET)
    d.text(350, 266, "page cache", 13, ROLE[NET][0], 600)
    d.rect(470, 244, 140, 34, ROLE[LH][1], ROLE[LH][0], 5)
    d.text(540, 266, "shared pages", 12.5, ROLE[LH][0], 600, False, "middle")
    disk = d.box(395, 364, 170, 50, ["disk"], N)
    copy(d, disk, pc, "DMA", "① DMA copy")
    two_way(d, [(540, 244), (540, 162)], LH)
    d.label(552, 208, "same physical pages (no copy)", LH, 12.5, "start")
    d.text(32, 446, "Java: FileChannel.map() returns a MappedByteBuffer over these pages.", 12.5, MUTED)
    d.save()


# --- pooled memory ------------------------------------------------------------------------
def pm_hierarchy():
    d = Diagram("pooled-memory-01", 440, "Arena, chunk, page, memory unit",
                "Each level is cut from the one above it.")
    d.group(32, 86, 896, 316, "arena", M)
    for c in range(3):
        cx = 50 + c * 296
        d.group(cx, 118, 268, 270, "chunk · 16 MiB", LH)
        for p in range(3):
            py = 152 + p * 76
            if p == 2:
                d.text(cx + 134, py - 4, "⋮", 14, MUTED, 700, False, "middle")
                py += 8
            d.rect(cx + 12, py, 244, 58, ROLE[NET][1], ROLE[NET][0], 5, None, 1.2)
            d.text(cx + 22, py + 17, "page · 8 KiB", 11.5, ROLE[NET][0], 700, True)
            for u in range(3):
                ux = cx + 22 + u * 70
                if u == 2:
                    d.text(ux + 4, py + 42, "…", 13, MUTED, 700)
                    ux += 20
                d.rect(ux, py + 26, 58, 24, "#ffffff", ROLE[F][0], 4)
                d.text(ux + 29, py + 42, "unit", 11.5, ROLE[F][0], 600, True, "middle")
    d.text(32, 426, "A memory unit is one element of a subpage: a page split into equal pieces for small requests.", 12.5, MUTED)
    d.save()


def pm_arena_pool():
    d = Diagram("pooled-memory-02", 340, "Threads share a pool of arenas",
                "Several arenas reduce contention. Each thread is bound to one arena.")
    d.group(32, 86, 896, 100, "arena pool · directArenas[]", M)
    ar = [d.box(70 + i * 230, 122, 170, 46, [f"arena {n}"], M) for i, n in enumerate(["1", "2"])]
    ar.append(d.box(720, 122, 170, 46, ["arena N"], M))
    d.text(605, 150, "…", 18, MUTED, 700, False, "middle")
    th = [d.box(x, 254, 140, 44, [n], F) for x, n in [(40, "thread 1"), (240, "thread 2"), (440, "thread 3"), (760, "thread N")]]
    d.text(650, 282, "…", 18, MUTED, 700, False, "middle")
    for t, a in [(0, 0), (1, 0), (2, 1), (3, 2)]:
        d.arrow([(th[t]["cx"], th[t]["t"]), (ar[a]["cx"] + (t - 0.5) * 18 if a == 0 else ar[a]["cx"], ar[a]["b"])], F)
    d.text(32, 324, "A thread's PoolThreadCache picks the arena with the fewest threads (leastUsedArena) when it is created.", 12.5, MUTED)
    d.save()


def loop_box(d, x, y, w, lines, role):
    b = d.box(x, y, w, 48, lines, role, 12.5)
    c = ROLE[role][0]
    d.line([(b["l"] + 26, b["t"]), (b["l"] + 26, b["t"] - 20), (b["l"] - 14, b["t"] - 20), (b["l"] - 14, b["cy"]), (b["l"], b["cy"])], c, None, 1.4, True)
    d.line([(b["r"] - 26, b["t"]), (b["r"] - 26, b["t"] - 20), (b["r"] + 14, b["t"] - 20), (b["r"] + 14, b["cy"]), (b["r"], b["cy"])], c, None, 1.4, True)
    d.text(b["l"] - 18, b["t"] - 26, "prev", 11.5, c, 600, True, "start")
    d.text(b["r"] + 18, b["t"] - 26, "next", 11.5, c, 600, True, "end")
    return b


def pm_subpage_heads():
    d = Diagram("pooled-memory-03", 280, "Subpage pools start as empty circular lists",
                "Each slot of tinySubpagePools / smallSubpagePools holds a sentinel head whose prev and next point to itself.")
    d.group(32, 92, 896, 164, "PoolSubpage<T>[] subpagePools", NET)
    for i, n in enumerate(["[0]", "[1]", "[2]"]):
        x = 82 + i * 250
        loop_box(d, x, 176, 170, ["PoolSubpage", "head " + n], NET)
    d.text(840, 205, "…", 18, MUTED, 700, False, "middle")
    d.save()


def pm_chunk_pages():
    d = Diagram("pooled-memory-04", 210, "A chunk is divided into pages", "16 MiB chunk ÷ 8 KiB pages = 2048 pages.")
    d.group(32, 92, 896, 96, "chunk · 16 MiB", LH)
    for i, n in enumerate(["page 1", "page 2", "page 3", None, "page 2048"]):
        x = 52 + i * 176
        if n is None:
            d.text(x + 70, 150, "…", 18, MUTED, 700, False, "middle")
            continue
        d.box(x, 120, 150, 50, [n, "8 KiB"], NET, 12.5)
    d.save()


def pm_route():
    d = Diagram("pooled-memory-05", 300, "Pooled or not: decided by size", "Requests up to one chunk come from the pool; larger ones bypass it.")
    r = d.circle(80, 175, 40, ["request"], F, 12)
    q = d.diamond(330, 175, 250, 90, ["size ≤ chunk size", "(16 MiB)?"], N)
    a = d.box(600, 92, 328, 64, ["pooled", "arena → chunk → pages / subpage units"], LH, 12.5)
    b = d.box(600, 196, 328, 64, ["unpooled (huge)", "allocateHuge(): its own off-heap memory"], NET, 12.5)
    d.arrow([(r["r"], 175), (q["l"], 175)], F)
    d.arrow([(q["r"], 175), (500, 175), (500, a["cy"]), (a["l"], a["cy"])], LH)
    d.arrow([(q["r"], 175), (500, 175), (500, b["cy"]), (b["l"], b["cy"])], NET)
    d.label(550, a["cy"] - 7, "yes", LH)
    d.label(550, b["cy"] - 7, "no", NET)
    d.text(32, 286, "Huge allocations are not cached; their memory is released when the buffer is freed.", 12.5, MUTED)
    d.save()


def subpage_pools(name, title, sub, arr, sizes, shown):
    d = Diagram(name, 470, title, sub)
    d.group(32, 92, 896, 90, arr, NET)
    xs = {}
    n = len(sizes)
    step = 860 / n
    for i, s in enumerate(sizes):
        x = 50 + i * step
        if s is None:
            d.text(x + step / 2 - 10, 146, "…", 18, MUTED, 700, False, "middle")
            continue
        b = d.box(x, 120, step - 24, 44, [str(s), "head"], NET if s in shown else N, 12.5, fill=None if s in shown else "#ffffff")
        xs[s] = b
    for s in shown:
        h = xs[s]
        prev = h
        for j in range(2):
            b = d.box(h["cx"] - 70, 214 + j * 74, 140, 48, ["PoolSubpage", f"elemSize {s}"], F, 12)
            two_way(d, [(prev["cx"], prev["b"] + 2), (b["cx"], b["t"] - 2)], F)
            prev = b
        d.text(h["cx"], 378, "⋮", 16, MUTED, 700, False, "middle")
        d.text(h["cx"], 410, f"{s}-byte pages", 12, ROLE[F][0], 600, False, "middle")
    d.text(32, 452, "Every list is circular and doubly linked (prev ⇄ next). A page joins the list for its element size when it is split.", 12.5, MUTED)
    d.save()


def pm_chunk_lists():
    d = Diagram("pooled-memory-08", 420, "PoolChunkLists by usage",
                "Six lists linked by nextList (solid) and prevList (dashed). Each list holds a doubly linked list of chunks.")
    lists = [("qInit", "< 25 %"), ("q000", "1–50 %"), ("q025", "25–75 %"), ("q050", "50–100 %"), ("q075", "75–100 %"), ("q100", "100 %")]
    bs = []
    for i, (n, u) in enumerate(lists):
        bs.append(d.box(50 + i * 150, 130, 112, 54, [n, u + " used"], M, 12.5))
    for a, b in zip(bs, bs[1:]):
        d.arrow([(a["r"], a["cy"] - 10), (b["l"], b["cy"] - 10)], M)
    for i in range(2, 6):
        a, b = bs[i], bs[i - 1]
        d.arrow([(a["l"], a["cy"] + 12), (b["r"], b["cy"] + 12)], M, "4 3")
    q = bs[0]
    d.line([(q["l"] + 30, q["t"]), (q["l"] + 30, q["t"] - 20), (q["l"] - 12 + 0.1, q["t"] - 20), (q["l"] - 12, q["cy"]), (q["l"], q["cy"])], ROLE[M][0], "4 3", 1.4, True)
    d.text(q["l"] + 36, q["t"] - 12, "prevList = itself", 11.5, ROLE[M][0], 500)
    d.text(bs[1]["cx"], bs[1]["t"] - 12, "prevList = null", 11.5, ROLE[M][0], 500, False, "middle")
    for b in bs:
        c1 = d.box(b["cx"] - 52, 232, 104, 36, ["PoolChunk"], LH, 12)
        c2 = d.box(b["cx"] - 52, 296, 104, 36, ["PoolChunk"], LH, 12)
        d.arrow([(b["cx"], b["b"]), (b["cx"], c1["t"])], LH, None, None)
        two_way(d, [(c1["cx"], c1["b"] + 2), (c2["cx"], c2["t"] - 2)], LH)
        d.text(b["cx"], 356, "⋮", 16, MUTED, 700, False, "middle")
    d.text(32, 396, "A chunk moves forward when usage rises above the list's maxUsage, backward when it falls below minUsage.", 12.5, MUTED)
    d.save()


def pm_thresholds():
    d = Diagram("pooled-memory-10", 400, "Free-memory band of each PoolChunkList",
                "16 MiB chunks. A chunk moves to a fuller list at or below the left end, to an emptier list above the right end.")
    x0, x1 = 300, 900
    px = (x1 - x0) / 16
    y0 = 106
    for m in [0, 4, 8, 12, 16]:
        x = x0 + m * px
        d.line([(x, y0), (x, y0 + 6 * 40 + 10)], LINE, "3 4", 1)
        d.text(x, y0 + 6 * 40 + 30, f"{m} MiB", 11.5, MUTED, 400, True, "middle")
    d.text(x1, y0 + 6 * 40 + 48, "free bytes in the chunk →", 12, MUTED, 400, False, "end")
    rows = [("qInit", "< 25 % used", 12.16, None), ("q000", "1–50 %", 8.16, 16), ("q025", "25–75 %", 4.16, 12.16),
            ("q050", "50–100 %", 0, 8.16), ("q075", "75–100 %", 0, 4.16), ("q100", "100 %", None, 0)]
    for i, (n, u, lo, hi) in enumerate(rows):
        y = y0 + 8 + i * 40
        d.text(40, y + 17, n, 13.5, ROLE[M][0], 700, True)
        d.text(120, y + 17, u, 12.5, MUTED)
        if lo is None:
            d.parts.append(f'<circle cx="{x0}" cy="{y + 12}" r="6" fill="{ROLE[NET][0]}"/>')
            d.text(x0 + 14, y + 17, "0: completely full, never moves forward", 12, INK)
            continue
        right = x1 + 26 if hi is None else x0 + hi * px
        d.rect(x0 + lo * px, y + 2, right - (x0 + lo * px), 20, ROLE[NET][1], ROLE[NET][0], 4)
        if hi is None:
            d.text(x0 + lo * px - 8, y + 16.5, f"{lo} MiB – no upper limit", 11.5, ROLE[NET][0], 600, True, "end")
        else:
            d.text(x0 + lo * px + 8, y + 16.5, f"{lo} – {hi} MiB", 11.5, ROLE[NET][0], 600, True)
    d.save()


def pm_call_chain():
    d = Diagram("pooled-memory-11", 270, "From buffer(18) to PoolArena.allocate()",
                "The allocator forwards the request until the thread's arena takes over.")
    d.group(32, 92, 712, 120, "PooledByteBufAllocator", M)
    d.group(764, 92, 164, 120, "PoolArena", NET)
    steps = [("`buffer(18)`", "direct preferred"), ("`directBuffer(18)`", "max = MAX_VALUE"),
             ("`directBuffer(18, max)`", "validate"), ("`newDirectBuffer()`", "thread cache + arena")]
    bs = [d.box(42 + i * 172, 126, 164, 60, s, M, 11.5) for i, s in enumerate(steps)]
    bs.append(d.box(776, 126, 140, 60, ["`allocate()`", "get + fill a buf"], NET, 12))
    hchain(d, bs, N)
    d.text(32, 248, "newDirectBuffer() takes the caller's PoolThreadCache and its directArena, then calls directArena.allocate(cache, 18, max).", 12.5, MUTED)
    d.save()


def pm_buddy_tree():
    d = Diagram("pooled-memory-12", 520, "The buddy tree over one chunk",
                "Each node is a power-of-two run of pages. Depth 11 has 2048 leaves, one per 8 KiB page.")
    def node(x, y, s, role=LH):
        return d.circle(x, y, 20, [s], role, 11)
    lv = [(120, "depth 0", "1 node · 16 MiB"), (200, "depth 1", "2 nodes · 8 MiB"), (280, "depth 2", "4 nodes · 4 MiB"),
          (380, "depth 10", "1024 nodes · 16 KiB"), (460, "depth 11", "2048 pages · 8 KiB")]
    for y, a, b in lv:
        d.text(760, y - 2, a, 13, ROLE[M][0], 700, True)
        d.text(760, y + 16, b, 12, MUTED)
    root = node(350, 120, "16M")
    l1 = [node(x, 200, "8M") for x in (190, 510)]
    l2 = [node(x, 280, "4M") for x in (110, 270, 430, 590)]
    for c in l1:
        d.line([(root["cx"], root["b"]), (c["cx"], c["t"])], ROLE[LH][0], None, 1.3)
    for i, c in enumerate(l2):
        p = l1[i // 2]
        d.line([(p["cx"], p["b"]), (c["cx"], c["t"])], ROLE[LH][0], None, 1.3)
    d.text(350, 334, "⋮", 18, MUTED, 700, False, "middle")
    for gx in (110, 350, 590):
        p = node(gx, 380, "16K")
        for dx in (-50, 50):
            c = node(gx + dx, 460, "8K", NET)
            d.line([(p["cx"], p["b"]), (c["cx"], c["t"])], ROLE[LH][0], None, 1.3)
    d.text(230, 384, "…", 16, MUTED, 700, False, "middle")
    d.text(470, 384, "…", 16, MUTED, 700, False, "middle")
    d.text(32, 506, "A request for 2^k pages searches depth 11 − k. A 16 KiB request takes one free node at depth 10 (two pages).", 12.5, MUTED)
    d.save()


def pm_tiny():
    subpage_pools("pooled-memory-06", "tinySubpagePools", "Slot i holds pages split into 16 × i-byte elements (16 to 496 bytes).",
                  "PoolSubpage<T>[32] tinySubpagePools", [16, 32, 48, 64, None, 496], [16, 496])


def pm_small():
    subpage_pools("pooled-memory-07", "smallSubpagePools", "One slot per size: 512, 1024, 2048 and 4096 bytes.",
                  "PoolSubpage<T>[4] smallSubpagePools", [512, 1024, 2048, 4096], [512, 4096])


REDRAWS = [size_table, recycler_map, recycle_call, push_choice, get_call, scavenge_list, reactor, event_loop_work,
           pipeline_directions, pipeline_propagation, zc_traditional, zc_sendfile, zc_read, zc_mmap,
           pm_hierarchy, pm_arena_pool, pm_subpage_heads, pm_chunk_pages, pm_route, pm_tiny, pm_small,
           pm_chunk_lists, pm_thresholds, pm_call_chain, pm_buddy_tree]


ALL = [server_startup, socket_write, message_framing, handle_bits, reference_flow] + REDRAWS

if __name__ == "__main__":
    for f in ALL:
        f()
    for w in mc.WARN:
        print("overflow?", w)
    print(f"wrote {len(ALL)} diagrams")
