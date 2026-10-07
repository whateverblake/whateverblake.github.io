INF = 1e9
ALL = (-INF, -INF, INF, INF)
Z = 'zookeeper/'
N = 'netty/'
DB = 'zookeeper_source_code_drawio/zookeeper_DB_init.drawio'
SNAP = 'GwyQWO2RPQr_w0LrGCnW-19'  # green 'snap file format' container
# target asset (topic/assets/name.svg) -> (source drawio, crop box in absolute diagram coords[, ids to clip])
FIGS = {
    'zookeeper/leader-follower-initialization-01': (Z + 'leader_follower_init.drawio', (-100, 90, 700, 440)),
    'zookeeper/leader-follower-initialization-02': (Z + 'leader_follower_init.drawio', (-560, 660, 560, 1580)),
    'zookeeper/leader-follower-initialization-03': (Z + 'leader_follower_init.drawio', (-1000, 1900, 900, 2730)),
    'zookeeper/leader-election-01': (Z + 'ZAB_elect_message_exchange.drawio', (90, -270, 640, 420)),
    'zookeeper/leader-election-02': (Z + 'ZAB_elect_message_exchange.drawio', (-80, 580, 540, 1130)),
    'zookeeper/leader-election-03': (Z + 'ZAB_elect_message_exchange.drawio', (-570, 1180, 820, 1950)),
    'zookeeper/standalone-server-startup-03': (Z + 'zookeeper_io_model.drawio', (100, -20, 1460, 570)),
    'zookeeper/expiry-queue-01': (Z + 'zookeeper_io_model.drawio', (100, 870, 760, 1160)),
    # The snapshot/log screenshots are lost; the author's file-format diagrams show the same structures.
    'zookeeper/data-recovery-02': (Z + DB, (1020, 745, 1600, 2260)),
    'zookeeper/data-recovery-03': (Z + DB, (530, 1095, 920, 2390), (SNAP,)),
    'zookeeper/data-recovery-04': (Z + DB, (530, 745, 920, 1090), (SNAP,)),
    'zookeeper/client-startup-05': (Z + 'zookeeper_client_connect_server.drawio', ALL),
    'zookeeper/node-creation-01': (Z + 'zookeeper_create_node.drawio', ALL),
    'zookeeper/node-creation-02': (Z + 'zookeeper_request_processor.drawio', (120, 120, 1030, 640)),
    'zookeeper/node-creation-03': (Z + 'zookeeper_request_processor.drawio', (1090, 590, 1300, 920)),
    'zookeeper/watch-processing-01': (Z + 'zookeeper_request_processor.drawio', ALL),
    'netty/socket-read-01': (N + 'size_table.drawio', ALL),
    'netty/recycler-01': (N + 'Recycler.drawio', (-620, 130, 1000, 1100)),
    'netty/recycler-05': (N + 'Recycler.drawio', (1280, 270, 1480, 480)),
    'netty/recycler-06': (N + 'Recycler.drawio', (1300, 530, 1650, 820)),
    'netty/recycler-07': (N + 'Recycler.drawio', (1260, 900, 1420, 1040)),
    'netty/recycler-08': (N + 'Recycler.drawio', (1030, 1110, 1660, 1610)),
    'netty/pooled-memory-01': (N + 'memory_allocation_jemalloc.drawio', (-1640, 40, -770, 470)),
    'netty/pooled-memory-02': (N + 'memory_allocation_jemalloc.drawio', (1840, 5380, 2430, 5660)),
    'netty/pooled-memory-03': (N + 'memory_allocation_jemalloc.drawio', (-1650, 1715, -1040, 1835)),
    'netty/pooled-memory-04': (N + 'memory_allocation_jemalloc.drawio', (-1625, 2120, -1205, 2200)),
    'netty/pooled-memory-05': (N + 'memory_allocation_jemalloc.drawio', (-1625, 2120, -1020, 2385)),
    'netty/pooled-memory-06': (N + 'memory_allocation_jemalloc.drawio', (2880, 50, 3560, 480)),
    'netty/pooled-memory-07': (N + 'memory_allocation_jemalloc.drawio', (2880, 520, 3560, 980)),
    'netty/pooled-memory-08': (N + 'memory_allocation_jemalloc.drawio', (-410, 2215, 660, 2525)),
    'netty/pooled-memory-10': (N + 'memory_allocation_jemalloc.drawio', (-295, 2600, 820, 2770)),
    'netty/pooled-memory-11': (N + 'memory_allocation_jemalloc.drawio', (2670, 1715, 3020, 2070)),
    'netty/pooled-memory-12': (N + 'memory_allocation_jemalloc.drawio', (3460, 3270, 3975, 3720)),
    'netty/thread-model-01': (N + 'netty_thread_model.drawio', (170, 20, 640, 680)),
    'netty/thread-model-02': (N + 'netty_thread_model.drawio', (170, 820, 640, 945)),
    'netty/pipeline-01': (N + 'pipeLine_add_handler_prcocess.drawio', (-220, 1380, 740, 1670)),
    'netty/pipeline-02': (N + 'pipeline事件触发.drawio', ALL),
    'netty/java-zero-copy-02': (N + '内核-内核-copy.drawio', ALL),
    'netty/java-zero-copy-03': (N + '非MMAP_复制.drawio', ALL),
    'netty/java-zero-copy-04': (N + 'mmap_内存复制.drawio', ALL),
}
