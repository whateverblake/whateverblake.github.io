---
layout: default
title: Linux 零拷贝：sendfile 与 mmap
article: true
topic: Linux
order: 100
lang: zh-CN
description: "通过 Java Socket、sendfile 和 mmap 示例，理解数据复制的开销与零拷贝的工作方式。"
---

# Linux 零拷贝：sendfile 与 mmap

### 零copy的意义
应用程序在使用请求网络数据或者硬盘数据的时候，这些数据往往需要在用户程序缓存区，内核缓存区中来回的copy，零拷贝主要是为了减少数据在用户缓存空间和内核缓存空间之间的copy，以及数据在内核缓存之间的copy操作，而并不是表示真的没有数据copy的发送，通过零copy可以给cpu减负，使其更有效率的运行，减少用户缓存区和内核缓存区的内存占用。

### sendfile
下面是一段基于BIO的java socket 程序，server接受客户的连接请求，然后读取用户发来的数据然后在把数据发送给用户。client代码表示连接服务端之后从文件读取数据然后发送给服务端

#####  server
```
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
##### Client
```
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
从客户端来看数据在磁盘，内核缓存，用户缓存，socket缓存会经过如下图的copy过程
1. 磁盘文件通过DMA的方式copy到内核缓存区（DMA负责 copy）
2. 内核缓存区的数据copy到用户缓存区（cpu负责copy）
3. 用户缓存区的数据copy到socket缓存区（内核缓存区）（cpu负责copy）
4. socket缓存区的数据通过DMA发送给网卡（DMA负责 copy）

![用户态-内核态-数据copy.jpg](https://upload-images.jianshu.io/upload_images/23114405-9bae43b3d6d4bf57.jpg?imageMogr2/auto-orient/strip%7CimageView2/2/w/1240)
从上面的图中可以看出来两次cpu的copy在特定的场景是可以省略的（应用不需要处理这些数据），linux 提供了sendfile系统调用，通过这个系统调用可以避免两次用户内存缓存区和内核缓存区的数据copy。现在我们把client代码修改如下。这个时候上图中的两次cpu copy就可以被规避,入下图就是这种情况下数据copy的过程
```
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
![内核-内核_copy.jpg](https://upload-images.jianshu.io/upload_images/23114405-92aa5d681d82cf7f.jpg?imageMogr2/auto-orient/strip%7CimageView2/2/w/1240)

### mmap
对于哪些需要读取磁盘文件然后做一些业务逻辑的应用程序，如何有效减少文件在内核缓存和用户缓存之间的复制呢？

###### 非MMap代码块
```
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
上面这段代码涉及到的数据copy入下图
![非MMAP_复制.jpg](https://upload-images.jianshu.io/upload_images/23114405-0f0d7f39f1f84631.jpg?imageMogr2/auto-orient/strip%7CimageView2/2/w/1240)

1. 数据通过DMA copy 到内核缓存区
2. 内核缓存区copy 到用户缓存区

###### Mmap代码块
```
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
上面代码使用了file channel 然后映射了底层操作系统的mmap系统调用
这段代码涉及到的数据copy入下图。可以发现通过mmap，在用户空间对文件的读操作会直接映射到内核空间的缓存中，对文件的写操作也会直接修改内核缓存页的数据，保存之后数据会通过DMA刷入磁盘

![mmap_内存复制.jpg](https://upload-images.jianshu.io/upload_images/23114405-8db68ff7590b2a7c.jpg?imageMogr2/auto-orient/strip%7CimageView2/2/w/1240)



#### 参考文档
[https://www.jianshu.com/p/fad3339e3448](https://www.jianshu.com/p/fad3339e3448)
[https://zhuanlan.zhihu.com/p/66595734](https://zhuanlan.zhihu.com/p/66595734)












