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


ALL = [server_startup, socket_write, message_framing, handle_bits, reference_flow]

if __name__ == "__main__":
    for f in ALL:
        f()
    for w in mc.WARN:
        print("overflow?", w)
    print(f"wrote {len(ALL)} diagrams")
