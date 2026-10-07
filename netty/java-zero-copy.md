---
layout: default
article: true
topic: Netty
lang: en
title: "Understanding Java Zero-Copy with sendfile and mmap"
description: "Compare Java socket copying, FileChannel.transferTo, and memory-mapped file access."
order: 500
series_order: 10
---

# Understanding Java Zero-Copy with sendfile and mmap

Reading a file and sending it over the network usually moves the same bytes several times between kernel buffers and your application. **Zero-copy** techniques cut out some of those copies. This article compares an ordinary Java socket transfer, `FileChannel.transferTo` (`sendfile`) and memory-mapped files (`mmap`).

> **Source:** OpenJDK 8u272-b10 (October 2020). The figures are the author's original diagrams with English labels; the first one came from a third-party source and is redrawn in the same style.

"Zero-copy" does not mean no data moves. Devices still transfer bytes, usually by DMA. It means fewer **CPU copies**, which saves CPU time and the memory used by intermediate buffers.

## 1. The ordinary path

A blocking-I/O example: the server accepts a client, reads its bytes and writes a response; the client reads a file and sends it to the server.

### Server

```java
public class Server {

    private ServerSocket ss;

    public Server(int port) throws Exception {
        ss = new ServerSocket(port);
    }

    public void doAccept() throws Exception {

        while (true) {
            Socket client = ss.accept();
            System.out.println("get a conn " + client);
            new Worker(client).start();
        }
    }


    class Worker extends Thread {
        Socket client;
        byte[] buffer = new byte[1024];

        Worker(Socket socket) {
            client = socket;
        }

        public void run() {
            try {
                BufferedInputStream bis = new BufferedInputStream(client.getInputStream());
                BufferedOutputStream bos = new BufferedOutputStream(client.getOutputStream());
                int len = 0;
                while ((len = bis.read(buffer)) != -1) {
                    System.out.println(new String(buffer, 0, len));
                    bos.write(buffer, 0, len);
                }
            } catch (IOException e) {
                e.printStackTrace();
            }
        }
    }
    public static void main(String[] args) {
        try {
            Server server = new Server(6687);
            server.doAccept();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

}
```

### Client

```java
class Client {
    Socket socket;

    Client(String host, int port) throws Exception {
        socket = new Socket(host, port);
    }

    public void sendMessage() {
        File f = new File("a.txt");
        byte[] buffer = new byte[1024];
        try {
            OutputStream outputStream = socket.getOutputStream();
            FileInputStream fis = new FileInputStream(f);
            int len = 0;
            while ((len = fis.read(buffer)) != -1) {
                outputStream.write(buffer, 0, len);
            }
        } catch (FileNotFoundException e) {
            e.printStackTrace();
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    public static void main(String[] args) {
        try {
            Client client = new Client("127.0.0.1",6687);
            client.sendMessage();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
```

On the client, the file's bytes take four steps to reach the network:

1. **DMA:** disk → kernel page cache.
2. **CPU:** page cache → application buffer (`read`).
3. **CPU:** application buffer → kernel socket buffer (`write`).
4. **DMA:** socket buffer → network device.

[![Traditional copy path: disk, page cache, user buffer, socket buffer, network](assets/java-zero-copy-01.svg){: .diagram}](assets/java-zero-copy-01.svg)

## 2. `sendfile`: skip the application buffer

If the application does not need to look at or change the file, the two copies through the application buffer are wasted. Linux has `sendfile` for this. In Java, `FileChannel.transferTo` can use it:

```java
class ClientChannel {
    SocketChannel socketChannel;

    ClientChannel(String host, int port) throws Exception {
        socketChannel = SocketChannel.open();
        socketChannel.connect(new InetSocketAddress(host, port));
    }

    public void sendMessage() {
        File f = new File("a.txt");
        try {
            FileInputStream fis = new FileInputStream(f);
            FileChannel fileChannel = fis.getChannel();
            fileChannel.transferTo(0, f.length(), socketChannel);
        } catch (FileNotFoundException e) {
            e.printStackTrace();
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    public static void main(String[] args) {
        try {
            ClientChannel client = new ClientChannel("127.0.0.1", 6687);
            client.sendMessage();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
```

[![sendfile copies from the page cache to the socket buffer inside the kernel](assets/java-zero-copy-02.svg){: .diagram}](assets/java-zero-copy-02.svg)

Now the bytes stay in the kernel. A kernel-to-kernel CPU copy (page cache → socket buffer) can remain on some paths; with scatter/gather support the network card reads straight from the page cache and that copy disappears too. Which one you get depends on the platform. `transferTo` is an optimization, not a promise of zero CPU copies.

## 3. `mmap`: share the page cache

What if the application **does** need to process the file contents? Then it must read them, but it can still avoid the copy from the kernel into its own buffer.

### Without mapping

```java
public class FileReader {
    File f ;

    public void readFile(String fileName){

        f = new File(fileName);
        byte[] buffer = new byte[1024] ;
        try {
            BufferedInputStream bis = new BufferedInputStream(new FileInputStream(f));
            int len= 0;
            while((len =bis.read(buffer)) != -1){
                doBusiness(buffer,len);
            }

        } catch (IOException e) {
            e.printStackTrace();
        }

    }
    private void doBusiness(byte[] data,int len){
        System.out.println(new String(data,0,len));
    }

}
```

The data path:

[![Ordinary read: DMA into the kernel page cache, then a CPU copy to user memory](assets/java-zero-copy-03.svg){: .diagram}](assets/java-zero-copy-03.svg)

1. **DMA:** disk → kernel page cache.
2. **CPU:** page cache → application buffer.

### With mapping

```java
public class MmapFileReader {

    byte buffer[];
    File f ;

    public MmapFileReader(String fileName){
        f =  new File(fileName) ;
        buffer = new byte[(int)f.length()] ;
    }

    public void doMmap(){
        try {
            MappedByteBuffer mappedByteBuffer = new RandomAccessFile(f,"rw").getChannel().map(FileChannel.MapMode.READ_WRITE,0,f.length());
            ByteBuffer byteBuffer = mappedByteBuffer.get(buffer);
            System.out.println(new String(buffer,0,(int)f.length()));
        } catch (FileNotFoundException e) {
            e.printStackTrace();
        } catch (IOException e) {
            e.printStackTrace();
        }

    }
}
```

`FileChannel.map` uses the operating system's `mmap`. The mapping lets the process read and write the file's pages **directly in the page cache**, with no copy into a separate buffer.

- Writes through a shared read/write mapping mark those pages dirty, and the OS writes them back on its own schedule. Call `MappedByteBuffer.force()` when you need the data on disk, and remember the filesystem's and device's own durability guarantees.
- This example still calls `mappedByteBuffer.get(buffer)`, which **copies** the mapped bytes into a Java array. Mapping removed the `read` copy, but this one remains; process the mapped buffer directly to avoid it.

[![mmap: user memory shares the kernel page cache](assets/java-zero-copy-04.svg){: .diagram}](assets/java-zero-copy-04.svg)

## References

- [jianshu.com/p/fad3339e3448](https://www.jianshu.com/p/fad3339e3448)
- [zhuanlan.zhihu.com/p/66595734](https://zhuanlan.zhihu.com/p/66595734)

## Notes on the examples

The snippets are illustrations, not production code. If you reuse them:

- **Flush responses.** The server writes to a `BufferedOutputStream` without `flush()`, so a short reply can stay buffered.
- **Read the replies.** The clients never read the echoed response, so a large transfer can deadlock under backpressure. Give the protocol an explicit end (a length header or `shutdownOutput()`), read replies concurrently if needed, and close streams and channels.
- **Loop on `transferTo`.** One call can transfer fewer bytes than asked. Loop on the returned count and handle zero progress.
- **Map big files in windows.** The mmap example casts the file length to `int`, so it only works for one mapping and files that fit in a Java array.
- **TCP has no message boundaries** (see [framing](message-framing.html)).

The original article's blanket claims, that zero-copy removes every CPU copy and that mapped writes hit the disk immediately, are qualified above.

Source references:

- [FileChannel implementation (OpenJDK 8u272-b10)](https://github.com/openjdk/jdk8u/blob/c3b5603e949d6272d777ef57952833672a97b4e3/jdk/src/share/classes/sun/nio/ch/FileChannelImpl.java)
- [MappedByteBuffer (OpenJDK 8u272-b10)](https://github.com/openjdk/jdk8u/blob/c3b5603e949d6272d777ef57952833672a97b4e3/jdk/src/share/classes/java/nio/MappedByteBuffer.java)
- [Netty DefaultFileRegion](https://github.com/netty/netty/blob/d4a0050ef33cab2542a80e11489a4977a63859f8/transport/src/main/java/io/netty/channel/DefaultFileRegion.java)
