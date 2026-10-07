"""Redraw the ZooKeeper series figures in the shared diagram style.

Run: python3 zookeeper/assets/draw_diagrams.py
The originals are the author's drawio diagrams (kept, translated, in
_migration/drawio/zookeeper/); these redraws keep their content.
Roles: follower green · LearnerHandler purple · leader / main thread blue ·
network messages and queues orange · everything else grey.
"""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("mc", HERE.parent.parent / "mooncake/assets/draw_diagrams.py")
mc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mc)
mc.OUT = HERE
Diagram, ROLE, INK, MUTED, FAINT, LINE, PANEL = mc.Diagram, mc.ROLE, mc.INK, mc.MUTED, mc.FAINT, mc.LINE, mc.PANEL
F, LH, M, NET, N = "caller", "owner", "master", "data", "neutral"


def down(d, a, b, role=N, label=None):
    d.arrow([(a["cx"], a["b"]), (b["cx"], b["t"])], role, None, label, 0.5, 4, "start")


def across(d, a, b, role=NET, label=None, dash=None, y=None):
    y = y if y is not None else a["cy"]
    if a["cx"] < b["cx"]:
        d.arrow([(a["r"], y), (b["l"], y)], role, dash, label, 0.5, -7)
    else:
        d.arrow([(a["l"], y), (b["r"], y)], role, dash, label, 0.5, -7)


LANES3 = [(20, 300, "follower", F), (330, 300, "leader · LearnerHandler", LH), (640, 300, "leader · main thread", M)]
CX = [170, 480, 790]


def lbox(d, lane, y, lines, role, h=50, w=210, size=13):
    return d.box(CX[lane] - w / 2, y, w, h, lines, role, size)


# ---------------------------------------------------------------------------
def lfi_connect():
    d = Diagram("leader-follower-initialization-01", 390, "Followers connect to the leader",
                "The leader accepts on its quorum port; every connected follower gets its own LearnerHandler thread.")
    lead = d.box(60, 96, 280, 50, ["Leader", "`Leader.lead()`"], M)
    acc = d.box(60, 196, 280, 56, ["LearnerCnxAcceptorHandler", "accepts follower sockets"], M)
    lh = d.box(60, 306, 280, 56, ["LearnerHandler", "one thread per follower"], LH)
    fol = d.box(620, 96, 280, 50, ["Follower", "`Follower.followLeader()`"], F)
    con = d.box(620, 196, 280, 56, ["LeaderConnector", "opens the connection"], F)
    down(d, lead, acc, M)
    down(d, acc, lh, M, "per accepted socket")
    down(d, fol, con, F)
    across(d, con, acc, NET, "TCP connect · quorum port (e.g. 2888)")
    d.arrow([(con["cx"], con["b"]), (con["cx"], lh["cy"]), (lh["r"], lh["cy"])], LH, "6 4")
    d.label(560, lh["cy"] - 8, "protocol packets: FOLLOWERINFO, LEADERINFO, …", LH)
    d.save()


def lfi_epoch():
    d = Diagram("leader-follower-initialization-02", 720, "Agree on a new epoch",
                "FOLLOWERINFO → LEADERINFO → ACKEPOCH. The leader's main thread waits for a quorum twice.")
    d.lanes(LANES3, 80, 700)
    f1 = lbox(d, 0, 120, ["send FOLLOWERINFO", "acceptedEpoch, sid"], F)
    h1 = lbox(d, 1, 120, ["parse FOLLOWERINFO"], LH)
    m1 = lbox(d, 2, 120, ["`getEpochToPropose()`", "collect follower epochs"], M)
    across(d, f1, h1, NET, "FOLLOWERINFO")
    across(d, h1, m1, N)
    q1 = d.diamond(CX[2], 250, 170, 66, ["quorum of sids", "for a new epoch?"], M)
    down(d, m1, q1, M)
    d.text(q1["r"] - 6, q1["t"] + 6, "no: wait()", 12, MUTED, 500, False, "start")
    m2 = lbox(d, 2, 320, ["notifyAll()", "newEpoch = max(epochs) + 1"], M)
    d.arrow([(q1["cx"], q1["b"]), (m2["cx"], m2["t"])], M, None, "yes", 0.5, 4, "start")
    h2 = lbox(d, 1, 320, ["newEpoch is ready"], LH)
    across(d, m2, h2, M, "notify")
    down(d, h1, h2, LH)
    h3 = lbox(d, 1, 400, ["send LEADERINFO", "newLeaderZxid = (newEpoch, 0)"], LH)
    down(d, h2, h3, LH)
    f2 = lbox(d, 0, 400, ["read LEADERINFO"], F)
    across(d, h3, f2, NET, "LEADERINFO")
    down(d, f1, f2, F)
    q2 = d.diamond(CX[0], 520, 180, 70, ["newEpoch ≥", "acceptedEpoch?"], F)
    down(d, f2, q2, F)
    d.text(q2["r"] + 4, q2["cy"] + 4, "no: throw", 12, MUTED, 500, False, "start")
    f3 = lbox(d, 0, 590, ["send ACKEPOCH", "currentEpoch + last zxid"], F)
    d.arrow([(q2["cx"], q2["b"]), (f3["cx"], f3["t"])], F, None, "yes", 0.5, 2, "start")
    h4 = lbox(d, 1, 590, ["parse ACKEPOCH", "→ waitForEpochAck()"], LH)
    across(d, f3, h4, NET, "ACKEPOCH")
    down(d, h3, h4, LH)
    m3 = lbox(d, 2, 470, ["`waitForEpochAck()`", "until a quorum has acked"], M)
    down(d, m2, m3, M)
    d.arrow([(h4["r"], h4["cy"]), (652, h4["cy"]), (652, m3["cy"]), (m3["l"], m3["cy"])], N, "4 4")
    d.label(626, h4["cy"] - 8, "ack", N)
    m4 = d.box(CX[2] - 105, 590, 210, 50, ["quorum reached", "ZAB → SYNCHRONIZATION"], M)
    down(d, m3, m4, M)
    d.text(CX[1], 672, "next: syncFollower()", 12, ROLE[LH][0], 600, False, "middle")
    d.text(CX[0], 672, "next: SYNCHRONIZATION", 12, ROLE[F][0], 600, False, "middle")
    d.save()


def lfi_sync():
    d = Diagram("leader-follower-initialization-03", 830, "Synchronize data, then start serving",
                "The handler picks DIFF, TRUNC or SNAP; NEWLEADER and UPTODATE close the synchronization phase.")
    d.lanes(LANES3, 80, 780)
    # strategy panel across handler + main lanes
    d.rect(340, 120, 590, 186, "#ffffff", ROLE[LH][0], 8)
    d.text(356, 142, "syncFollower(): compare the follower's f_zxid with the leader's history", 12.5, ROLE[LH][0], 700)
    cases = [(["f_zxid ==", "l_zxid"], "DIFF", "(nothing to send)"),
             (["f_zxid >", "maxCommittedLog"], "TRUNC", "drop extra history"),
             (["min ≤ f_zxid", "≤ maxCommittedLog"], "DIFF", "+ missing proposals"),
             (["f_zxid <", "minCommittedLog"], "SNAP", "or DIFF from txn log*")]
    for i, (cond, act, note) in enumerate(cases):
        x = 352 + i * 144
        d.rect(x, 154, 136, 56, PANEL, LINE, 5)
        d.text(x + 68, 177, cond[0], 11.5, INK, 500, True, "middle")
        d.text(x + 68, 194, cond[1], 11.5, INK, 500, True, "middle")
        d.arrow([(x + 68, 210), (x + 68, 232)], LH)
        d.text(x + 68, 252, act, 14, ROLE[LH][0], 700, True, "middle")
        d.text(x + 68, 270, note, 11.5, MUTED, 400, False, "middle")
    d.text(352, 296, "* if the needed proposals are no longer in committedLog, the on-disk log can still bridge the gap; otherwise SNAP", 11, FAINT)
    # follower side handling
    d.text(CX[0], 140, "syncWithLeader() handles the command", 12, ROLE[F][0], 700, False, "middle")
    for i, (h, body) in enumerate([("DIFF", "apply each proposal + COMMIT"), ("TRUNC", "truncate log to zxid, reload DB"), ("SNAP", "deserialize snapshot from stream")]):
        d.box(CX[0] - 130, 152 + i * 52, 260, 44, [h, body], F, 12.5)
    h1 = lbox(d, 1, 340, ["send NEWLEADER"], LH)
    f1 = lbox(d, 0, 340, ["read NEWLEADER", "persist synced state"], F)
    across(d, h1, f1, NET, "NEWLEADER")
    f2 = lbox(d, 0, 420, ["send ACK for NEWLEADER"], F)
    down(d, f1, f2, F)
    h2 = lbox(d, 1, 420, ["parse the ACK"], LH)
    across(d, f2, h2, NET, "ACK")
    down(d, h1, h2, LH)
    m1 = lbox(d, 2, 340, ["`waitForNewLeaderAck()`", "quorum confirms the leader"], M, h=56)
    d.arrow([(h2["r"], h2["cy"]), (700, h2["cy"]), (700, m1["b"])], N, "4 4")
    d.label(650, h2["cy"] - 8, "ack", N)
    q = d.diamond(CX[2], 520, 140, 64, ["quorum?"], M)
    d.arrow([(m1["cx"], m1["b"]), (q["cx"], q["t"])], M)
    d.text(q["r"] + 4, q["cy"] + 4, "no: wait", 12, MUTED, 500, False, "start")
    h3 = lbox(d, 1, 495, ["send UPTODATE"], LH)
    across(d, q, h3, M, "yes: notify")
    down(d, h2, h3, LH)
    f3 = lbox(d, 0, 495, ["read UPTODATE"], F)
    across(d, h3, f3, NET, "UPTODATE")
    down(d, f2, f3, F)
    m2 = lbox(d, 2, 610, ["`startZkServer()`", "sessions + processor chain"], M, h=56)
    d.arrow([(q["cx"], q["b"]), (m2["cx"], m2["t"])], M, None, "yes", 0.5, 4, "start")
    f4 = lbox(d, 0, 590, ["syncMode = NONE", "start the follower's server"], F, h=56)
    down(d, f3, f4, F)
    f5 = d.box(CX[0] - 105, 700, 210, 46, ["ZAB → BROADCAST"], F)
    down(d, f4, f5, F)
    m3 = d.box(CX[2] - 105, 700, 210, 46, ["ZAB → BROADCAST"], M)
    down(d, m2, m3, M)
    h4 = lbox(d, 1, 700, ["normal packet loop", "proposals, commits, pings"], LH, h=46)
    down(d, h3, h4, LH)
    d.text(480, 810, "From here on, client writes go leader → followers as proposals and commits (ZAB broadcast).", 12.5, MUTED, anchor="middle")
    d.save()


# ---------------------------------------------------------------------------
def le_threads():
    d = Diagram("leader-election-01", 520, "Votes cross threads and queues",
                "Boxes are threads, cylinders are queues. Top row sends a vote; bottom row receives one.")
    d.group(170, 86, 300, 390, "FastLeaderElection", M)
    d.group(480, 86, 300, 390, "QuorumCnxManager", LH)
    qp = d.box(30, 150, 120, 270, ["QuorumPeer", "", "lookForLeader()", "makes and", "judges votes"], M)
    peer = d.box(810, 150, 130, 270, ["other peers", "", "one TCP", "connection", "per peer"], N)
    ys, yr = 170, 340
    s1 = d.cyl(185, ys, 130, 50, ["sendqueue", "<ToSend>"], NET)
    s2 = d.box(330, ys, 130, 50, ["WorkerSender", "serialize"], M)
    s3 = d.cyl(495, ys, 130, 50, ["queueSendMap", "<ByteBuffer>"], NET)
    s4 = d.box(640, ys, 130, 50, ["SendWorker", "write socket"], LH)
    r4 = d.box(640, yr, 130, 50, ["RecvWorker", "read socket"], LH)
    r3 = d.cyl(495, yr, 130, 50, ["recvQueue", "<Message>"], NET)
    r2 = d.box(330, yr, 130, 50, ["WorkerReceiver", "decode"], M)
    r1 = d.cyl(185, yr, 130, 50, ["recvqueue", "<Notification>"], NET)
    for a, b in [(qp, s1), (s1, s2), (s2, s3), (s3, s4), (s4, peer)]:
        d.arrow([(a["r"], ys + 25), (b["l"], ys + 25)], NET)
    for a, b in [(peer, r4), (r4, r3), (r3, r2), (r2, r1), (r1, qp)]:
        d.arrow([(a["l"], yr + 25), (b["r"], yr + 25)], NET)
    d.text(32, 502, "queueSendMap holds one queue per peer sid. recvQueue is shared by all RecvWorkers.", 12.5, MUTED)
    d.save()


def le_loop():
    d = Diagram("leader-election-02", 600, "The election loop",
                "Each peer votes for itself, then keeps comparing and re-broadcasting until one candidate has a quorum.")
    a = d.box(330, 86, 300, 40, ["ZAB state = ELECTION"], M)
    b = d.box(330, 146, 300, 48, ["vote for itself", "(sid, zxid, peerEpoch)"], M)
    c = d.box(330, 214, 300, 48, ["`sendNotifications()`", "to all voters"], M)
    down(d, a, b, M)
    down(d, b, c, M)
    d.group(40, 284, 880, 282, "lookForLeader() loop", M)
    r = d.box(70, 350, 220, 54, ["take r_vote", "from recvqueue"], M)
    bt = d.diamond(480, 377, 220, 76, ["r_vote better?", "(peerEpoch, zxid, sid)"], M)
    ad = d.box(670, 350, 220, 54, ["adopt r_vote", "and broadcast again"], M)
    rs = d.box(670, 470, 220, 54, ["put r_vote in recvset"], M)
    q = d.diamond(480, 497, 220, 76, ["voteTracker:", "quorum on our vote?"], M)
    end = d.box(70, 470, 220, 54, ["leave the loop", "LEADING / FOLLOWING"], F)
    d.arrow([(c["cx"], c["b"]), (c["cx"], 330), (r["cx"], 330), (r["cx"], r["t"])], M)
    d.arrow([(r["r"], r["cy"]), (bt["l"], bt["cy"])], M)
    d.arrow([(bt["r"], bt["cy"]), (ad["l"], ad["cy"])], M, None, "yes", 0.5, -7)
    d.arrow([(ad["cx"], ad["b"]), (rs["cx"], rs["t"])], M)
    d.arrow([(bt["cx"], bt["b"]), (bt["cx"], 430), (rs["cx"] - 60, 430), (rs["cx"] - 60, rs["t"])], M, None, "no", 0.3, -6)
    d.arrow([(rs["l"], rs["cy"]), (q["r"], q["cy"])], M)
    d.arrow([(q["l"], q["cy"]), (end["r"], end["cy"])], F, None, "yes", 0.5, -7)
    d.arrow([(q["cx"], q["b"]), (q["cx"], 552), (54, 552), (54, r["cy"]), (r["l"], r["cy"])], M, "5 4")
    d.text(300, 548, "no: read the next vote", 12, MUTED, 500, False, "start")
    d.save()


def le_topology():
    d = Diagram("leader-election-03", 560, "Election connections in a three-peer ensemble",
                "Every pair of peers keeps one TCP connection. Each side has a send queue and a SendWorker/RecvWorker pair per peer.")

    def host(x, y, name, others):
        d.group(x, y, 340, 140, name, M)
        for i, o in enumerate(others):
            yy = y + 38 + i * 48
            d.cyl(x + 16, yy, 150, 38, [f"queueSendMap[{o}]"], NET, 11.5)
            d.box(x + 184, yy, 140, 38, [f"Send/RecvWorker {o}"], LH, 11.5, strong=False)
            d.arrow([(x + 166, yy + 19), (x + 184, yy + 19)], NET)
        return dict(l=x, r=x + 340, t=y, b=y + 140, cx=x + 170, cy=y + 70)
    h1 = host(310, 86, "host1 · sid 1", [2, 3])
    h2 = host(40, 380, "host2 · sid 2", [1, 3])
    h3 = host(580, 380, "host3 · sid 3", [1, 2])
    for pts, lab, dx, anc in [([(h2["cx"], h2["t"]), (h1["l"] + 40, h1["b"])], "TCP 1 ⇄ 2", -10, "end"),
                              ([(h3["cx"], h3["t"]), (h1["r"] - 40, h1["b"])], "TCP 1 ⇄ 3", 10, "start"),
                              ([(h3["l"], h3["cy"]), (h2["r"], h2["cy"])], "TCP 2 ⇄ 3", 0, "middle")]:
        d.line(pts, ROLE[LH][0], None, 1.6, True)
        d.parts[-1] = d.parts[-1].replace("marker-end=", 'marker-start="url(#a-%s)" marker-end=' % ROLE[LH][0][1:])
        (x1, y1), (x2, y2) = pts
        d.label((x1 + x2) / 2 + dx, (y1 + y2) / 2 - 6, lab, LH, 12.5, anc)
    d.text(480, 300, "If both peers dial each other, the connection opened", 12.5, MUTED, anchor="middle")
    d.text(480, 318, "by the smaller sid is closed; the larger sid's is kept.", 12.5, MUTED, anchor="middle")
    d.save()


# ---------------------------------------------------------------------------
def standalone_nio():
    d = Diagram("standalone-server-startup-03", 470, "How the NIO server accepts and dispatches I/O",
                "One AcceptThread, several SelectorThreads, a worker pool. A channel never has two I/O tasks at once.")
    cl = d.circle(62, 190, 30, ["clients"], N)
    at = d.box(122, 150, 196, 80, ["AcceptThread", "`doAccept()`", "accept a SocketChannel"], M)
    aq = d.cyl(340, 165, 150, 50, ["acceptedQueue", "<SocketChannel>"], NET)
    d.group(510, 96, 250, 280, "SelectorThread", M)
    p1 = d.box(524, 128, 222, 64, ["processAcceptedConnections", "register channel,", "create NIOServerCnxn"], M, 12)
    p2 = d.box(524, 208, 222, 64, ["select()", "ready key → IOWorkRequest", "(interest cleared)"], M, 12)
    p3 = d.box(524, 290, 222, 70, ["processInterestOps…", "re-register OP_READ /", "OP_WRITE for the key"], M, 12)
    pool = d.box(790, 190, 150, 92, ["IOWorkThreadPool", "`doWork()`", "doIO on the", "connection"], LH, 12)
    uq = d.cyl(560, 400, 160, 46, ["updateQueue", "<SelectionKey>"], NET)
    d.arrow([(cl["r"], 190), (at["l"], 190)], N)
    d.arrow([(at["r"], 190), (aq["l"], 190)], NET)
    d.arrow([(aq["r"], 190), (510, 190), (510, 160), (524, 160)], NET)
    d.arrow([(p2["r"], p2["cy"]), (pool["l"], p2["cy"])], LH, None, "submit", 0.5, -7)
    d.arrow([(pool["cx"], pool["b"]), (pool["cx"], uq["cy"]), (uq["r"], uq["cy"])], NET, None, "queue the key", 0.5, -7)
    d.arrow([(uq["cx"], uq["t"]), (uq["cx"], p3["b"])], NET)
    d.save()


def expiry_buckets():
    d = Diagram("expiry-queue-01", 370, "Deadlines rounded into buckets",
                "Each connection has its own deadline. ExpiryQueue rounds it up to the next multiple of expirationInterval.")
    x0, x1, y = 60, 900, 210
    d.line([(x0, y), (x1, y)], INK, None, 1.5, True)
    d.text(x1, y + 22, "time", 12, MUTED, anchor="end")
    bx = [200, 420, 640, 860]
    for i, x in enumerate(bx):
        d.line([(x, y - 74), (x, y + 64)], ROLE[M][0], "4 4", 1.3)
        d.text(x, y - 84, f"bucket {i + 1}", 12.5, ROLE[M][0], 700, True, "middle")
    d.line([(200, y + 88), (420, y + 88)], MUTED, None, 1.2, True)
    d.parts[-1] = d.parts[-1].replace("marker-end=", 'marker-start="url(#a-%s)" marker-end=' % MUTED[1:]) if MUTED in [v[0] for v in ROLE.values()] else d.parts[-1]
    d.label(310, y + 82, "expirationInterval", N, 12, "middle", True)
    conns = [(110, "c1", True), (160, "c2", False), (290, "c3", True), (380, "c4", False), (560, "c5", True), (600, "c6", False)]
    for x, name, above in conns:
        cy = y - 42 if above else y + 42
        d.circle(x, cy, 17, [name], F, 11.5)
        d.line([(x, cy + (17 if above else -17)), (x, y)], ROLE[F][0], None, 1.2)
        nxt = min(b for b in bx if b > x)
        d.arrow([(x + 6, y + (-4 if above else 4)), (nxt - 4, y + (-4 if above else 4))], F, "3 3", sw=1.1)
    d.text(32, 346, "When a bucket's time arrives, every connection in it expires together; activity moves a connection to a later bucket.", 12.5, MUTED)
    d.save()


# ---------------------------------------------------------------------------
def packet_fields():
    d = Diagram("client-startup-04", 470, "Packet: one request and its reply",
                "Every client call becomes a Packet. The reply is written back into the same object.")
    rows = [("RequestHeader", "requestHeader", "xid, type"),
            ("ReplyHeader", "replyHeader", "xid, zxid, err"),
            ("Record", "request", "request body"),
            ("Record", "response", "response body"),
            ("ByteBuffer", "bb", "the serialized request"),
            ("String", "clientPath", "path as the client sees it"),
            ("String", "serverPath", "path on the server (after chroot)"),
            ("boolean", "finished", "set when the reply arrives"),
            ("AsyncCallback", "cb", "called with the result (async API)"),
            ("Object", "ctx", "user-supplied context for cb")]
    d.rect(32, 86, 896, 370, PANEL, LINE, 8)
    d.text(56, 116, "static class", 13.5, ROLE[LH][0], 600, True)
    d.text(166, 116, "Packet {", 13.5, INK, 700, True)
    for i, (t, n, note) in enumerate(rows):
        y = 148 + i * 28
        d.text(88, y, t, 13.5, MUTED, 400, True)
        d.text(232, y, n + ";", 13.5, ROLE[M][0], 700, True)
        d.text(420, y, "// " + note, 13, ROLE[F][0], 400, True)
    d.text(56, 148 + len(rows) * 28, "}", 13.5, INK, 700, True)
    d.save()


def client_session():
    d = Diagram("client-startup-05", 470, "Socket first, then session",
                "The client connects TCP, then runs the ZooKeeper session handshake; the EventThread reports the result.")
    act = [(110, "EventThread", F), (310, "SendThread", F), (640, "AcceptThread", M), (840, "SelectorThread", M)]
    d.lifelines(act, 86, 430)
    y = 156
    d.msg(310, 640, y, "TCP connect", NET); y += 40
    d.msg(640, 310, y, "accepted", NET, "4 4"); y += 34
    d.rect(330, y - 14, 520, 24, ROLE[NET][1], ROLE[NET][0], 4)
    d.text(590, y + 2, "socket established", 12, ROLE[NET][0], 600, False, "middle"); y += 44
    d.msg(310, 840, y, "ConnectRequest: timeout, last zxid, session id/passwd", M); y += 40
    d.msg(840, 310, y, "ConnectResponse: session id, negotiated timeout", M, "4 4"); y += 34
    d.rect(330, y - 14, 520, 24, ROLE[M][1], ROLE[M][0], 4)
    d.text(590, y + 2, "session established", 12, ROLE[M][0], 600, False, "middle"); y += 46
    d.msg(310, 110, y, "SyncConnected event", F)
    d.text(110, y + 40, "watcher.process()", 12, MUTED, 500, True, "middle")
    d.save()


def node_client():
    d = Diagram("node-creation-01", 440, "The client side of create()",
                "The application thread only queues a Packet; SendThread serializes and writes it.")
    d.lanes([(20, 440, "application thread", M), (480, 460, "ClientCnxn · SendThread", F)], 80, 420)
    a = d.box(50, 120, 380, 54, ["`ZooKeeper.create(path, data, acl, mode)`", "builds RequestHeader, CreateRequest, ReplyHeader"], M, 12.5)
    b = d.box(50, 210, 380, 54, ["`submitRequest() → queuePacket()`", "wraps everything in a new Packet"], M, 12.5)
    c = d.cyl(90, 300, 300, 46, ["outgoingQueue.add(packet)"], NET)
    down(d, a, b, M)
    down(d, b, c, M)
    s1 = d.box(510, 210, 400, 54, ["`SendThread.doIO()`", "socket writable: set xid, createBB(), write"], F, 12.5)
    s2 = d.box(510, 300, 400, 54, ["move Packet to pendingQueue", "wait for the reply with the same xid"], F, 12.5)
    d.arrow([(c["r"], c["cy"]), (470, c["cy"]), (470, s1["cy"]), (s1["l"], s1["cy"])], NET, None, "taken by", 0.5, -7)
    down(d, s1, s2, F)
    d.text(50, 392, "sync API: blocks until packet.finished", 12, MUTED)
    d.text(510, 392, "async API: cb is called on the EventThread", 12, MUTED)
    d.save()


def server_path(name, title, sub, highlight_watch=False):
    d = Diagram(name, 540, title, sub)
    d.lanes([(20, 290, "SelectorThread", M), (320, 300, "IO worker thread", LH), (630, 310, "processor threads", NET)], 80, 524)
    a = d.box(40, 120, 250, 56, ["`handleIO()`", "read-ready SelectionKey"], M, 12.5)
    b = d.box(40, 210, 250, 56, ["`IOWorkerPool.schedule()`", "submit an IOWorkRequest"], M, 12.5)
    down(d, a, b, M)
    c = d.box(340, 120, 260, 56, ["`IOWorkRequest.doWork()`", "→ NIOServerCnxn.doIO()"], LH, 12.5)
    e = d.box(340, 200, 260, 56, ["read 4-byte length", "into a ByteBuffer"], LH, 12.5)
    f = d.box(340, 280, 260, 56, ["`readPayload()`", "read the body"], LH, 12.5)
    g = d.box(340, 360, 260, 56, ["`ZooKeeperServer.readRequest()`"], LH, 12.5)
    h = d.box(340, 440, 260, 64, ["`processPacket()`", "decode header, then body", "→ submitRequest"], LH, 12.5)
    d.arrow([(b["r"], b["cy"]), (310, b["cy"]), (310, c["cy"]), (c["l"], c["cy"])], LH)
    for x, y in [(c, e), (e, f), (f, g), (g, h)]:
        down(d, x, y, LH)
    procs = [("RequestThrottler", "admission limit"), ("PrepRequestProcessor", "build the txn"),
             ("SyncRequestProcessor", "log + flush"), ("FinalRequestProcessor", "apply + reply")]
    boxes = []
    for i, (p, note) in enumerate(procs):
        role = LH if (highlight_watch and i == 3) else NET
        lines = [p, note] if not (highlight_watch and i == 3) else [p, "addWatch → DataTree.addWatch"]
        bx = d.box(650, 120 + i * 100, 270, 56, lines, role, 12.5)
        if boxes:
            down(d, boxes[-1], bx, NET)
        boxes.append(bx)
    d.arrow([(h["r"], h["cy"]), (625, h["cy"]), (625, boxes[0]["cy"]), (boxes[0]["l"], boxes[0]["cy"])], NET)
    d.save()


def processor_chain():
    d = Diagram("node-creation-03", 270, "The standalone request processor chain",
                "Three of the four processors run their own thread; FinalRequestProcessor runs on SyncRequestProcessor's.")
    procs = [("RequestThrottler", ["limits requests", "in flight"], True),
             ("PrepRequestProcessor", ["checks, builds txn,", "outstandingChanges"], True),
             ("SyncRequestProcessor", ["appends to the log,", "flush, snapshots"], True),
             ("FinalRequestProcessor", ["applies to DataTree,", "sends the reply"], False)]
    prev = None
    for i, (p, lines, thread) in enumerate(procs):
        x = 32 + i * 232
        b = d.box(x, 110, 200, 96, [p] + lines, NET, 12.5)
        d.tag(x + 8, 220, "own thread" if thread else "caller's thread", NET if thread else N)
        if prev:
            d.arrow([(prev["r"], prev["cy"]), (b["l"], b["cy"])], NET)
        prev = b
    d.save()


# ---------------------------------------------------------------------------
def record(d, x, y, w, title, fields, role, size=12.5):
    """Draw a record layout: title strip, then rows (name, type) or nested ('>', title, fields, role)."""
    c, tint = ROLE[role]
    start, mark = y, len(d.parts)
    d.text(x + 10, y + 18, title, 13, c, 700, True)
    y += 28
    for f in fields:
        if f[0] == ">":
            y = record(d, x + 14, y, w - 28, f[1], f[2], f[3] if len(f) > 3 else role, size) + 6
        else:
            name, typ = f
            d.rect(x + 8, y, w - 16, 24, "#ffffff", LINE, 4)
            d.text(x + 18, y + 16.5, name, size, INK, 500, True)
            d.text(x + w - 18, y + 16.5, typ, size - 0.5, MUTED, 400, True, "end")
            y += 28
    y += 4
    d.rect(x, start, w, y - start, tint, c, 6, None, 1.2)
    d.parts.insert(mark, d.parts.pop())
    return y


def log_format():
    d = Diagram("data-recovery-02", 580, "Transaction log: format and replay",
                "Left: what one log entry holds. Right: how recovery replays the logs after a snapshot.")
    record(d, 32, 90, 420, "one log entry", [
        ("crc", "long (Adler32)"), ("txnEntry", "byte[]"),
        (">", "TxnLogEntry  ← deserializeTxn()", [
            (">", "TxnHeader", [("clientId", "long"), ("cxid", "int"), ("zxid", "long"), ("time", "long"), ("type", "int")], M),
            (">", "Record", [("parsed by type", "e.g. CreateTxn")], LH),
            (">", "TxnDigest", [("version", "int"), ("treeDigest", "long")], N)], NET)], N)
    steps = ["log_zxid = largest zxid in the snapshot + 1",
             "sort log.<zxid> files by suffix, newest first",
             "keep logs above log_zxid + the first one below it",
             "goToNextLog(): open a stream from the oldest kept",
             "next(): read crc + entry, deserialize",
             "skip entries with zxid < log_zxid",
             "processTransaction() for every later entry"]
    d.text(492, 112, "replay", 13, ROLE[M][0], 700, True)
    for i, st in enumerate(steps):
        y = 134 + i * 58
        if i < len(steps) - 1:
            d.line([(506, y + 15), (506, y + 73)], LINE, None, 1.2)
        d.step(506, y + 15, i + 1, M)
        d.rect(528, y, 400, 30, "#ffffff", LINE, 5)
        d.text(542, y + 19.5, st, 12.5, INK)
    d.save()


def snapshot_tree():
    d = Diagram("data-recovery-03", 600, "Snapshot file: the DataTree section",
                "After the header and sessions comes the tree: ACL cache, every node, then checksums and the digest.")
    record(d, 32, 90, 440, "DataTree", [
        (">", "aclCache", [("map size", "int"), (">", "entry × size", [("id", "long"), (">", "List<ACL>", [("perms", "int"), ("scheme", "String"), ("id", "String")], N)], N)], LH),
        (">", "nodes (until path \"/\")", [("path", "String"), (">", "DataNode", [("data", "byte[]"), ("acl", "long → aclCache"), ("stat", "StatPersisted →")], F)], F)], M)
    y = record(d, 500, 90, 428, "StatPersisted", [("czxid", "long"), ("mzxid", "long"), ("ctime", "long"), ("mtime", "long"),
                                                  ("version", "int"), ("cversion", "int"), ("aversion", "int"),
                                                  ("ephemeralOwner", "long"), ("pzxid", "long")], F)
    record(d, 500, y + 14, 428, "after the tree", [("checksum + \"/\"", "long, String"),
                                                   (">", "ZxidDigest", [("zxid", "long"), ("digestVersion", "int"), ("digest", "long")], N),
                                                   ("checksum + \"/\"", "long, String")], N)
    d.save()


def snapshot_header():
    d = Diagram("data-recovery-04", 280, "Snapshot file: header and sessions",
                "The file starts with a header, then the session table. The DataTree section follows.")
    record(d, 32, 90, 420, "FileHeader", [("magic", "int \"ZKSN\""), ("version", "int"), ("dbid", "long")], N)
    record(d, 500, 90, 428, "sessions", [("count", "int"), (">", "entry × count", [("session id", "long"), ("timeout", "int")], M)], M)
    d.text(32, 262, "→ then the DataTree section (next figure)", 12.5, MUTED)
    d.save()


ALL = [lfi_connect, lfi_epoch, lfi_sync, le_threads, le_loop, le_topology, standalone_nio, expiry_buckets,
       packet_fields, client_session, node_client, processor_chain, log_format, snapshot_tree, snapshot_header]

if __name__ == "__main__":
    for f in ALL:
        f()
    server_path("node-creation-02", "The server reads a request", "From a ready socket to the processor chain: selector, I/O worker, processors.")
    server_path("watch-processing-01", "An addWatch request on the server",
                "The same path as any request; FinalRequestProcessor registers the watch.", True)
    for w in mc.WARN:
        print("overflow?", w)
    print("wrote", len(ALL) + 2, "diagrams")
