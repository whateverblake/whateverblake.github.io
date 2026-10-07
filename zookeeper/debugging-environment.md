---
layout: default
article: true
topic: ZooKeeper
lang: en
title: "Setting Up a ZooKeeper Source Debugging Environment"
order: 210
series_order: 1
description: "Check out ZooKeeper 3.6.2, import its Maven reactor, and configure a reproducible standalone debug launch."
---

# Setting Up a ZooKeeper Source Debugging Environment

This guide sets up IntelliJ IDEA for reading and debugging the ZooKeeper source. When you finish, you can run a standalone server from the IDE and stop at breakpoints in its startup code.

> **Source version:** ZooKeeper **3.6.2** (October 2020), commit `803c7f1a12f85978cb049af5e4ef23bd8b688715`. Every article in this series uses this commit, so line numbers and behavior match.

## 1. Get the source

Clone the Apache ZooKeeper repository. In IntelliJ IDEA this is **File → New → Project from Version Control → Git** (the menu wording changes between IDE versions). A plain Git clone is all you need; no GitHub plugin is required.

SSH and HTTPS URLs both work. With SSH, the IDE's Git needs your key and GitHub access. With HTTPS you can read the public source without a GitHub account.

Then switch to the pinned commit **before** you import or build. From a terminal:

```sh
git clone https://github.com/apache/zookeeper.git
cd zookeeper
git checkout --detach 803c7f1a12f85978cb049af5e4ef23bd8b688715
git rev-parse HEAD
```

The last command prints the commit, so you can confirm you are on `803c7f1`. Now open the **root** `pom.xml` as a Maven project. Do not import only `zookeeper-server`: the reactor also contains `zookeeper-jute`, which generates the protocol classes that the server and client need.

## 2. Build with Maven

This release builds with Maven (older releases used Ant). Use JDK 8 update 211 or newer, as the pinned README requires, and set it for both the project SDK and the Maven runner.

From the repository root:

```sh
mvn clean install -DskipTests
```

This compiles every module and packages the distribution without running tests (drop `-DskipTests` to run them). The results:

- the binary distribution in `zookeeper-assembly/target`,
- the server's dependency jars in `zookeeper-server/target/lib`,
- generated protocol classes in `zookeeper-jute/target/generated-sources/java`.

Reload the Maven project in the IDE afterwards so it marks the generated directory as a source root.

## 3. Run the standalone server

1. **Create the config.** Copy `conf/zoo_sample.cfg` to `conf/zoo.cfg`. Set `dataDir` to an absolute, writable directory made for this experiment, and pick a free `clientPort` such as 2181. `dataLogDir` is optional; without it, logs go into `dataDir`.
2. **Create a run configuration.** Main class `org.apache.zookeeper.server.ZooKeeperServerMain`, classpath of the `zookeeper-server` module **including `provided` dependencies**, working directory = repository root, program argument `conf/zoo.cfg`.
3. **Point logging at the checked-in file.** Add the VM option `-Dlog4j.configuration=file:conf/log4j.properties` (relative to the working directory). This leaves the Maven layout untouched; copying the file into a resource directory also works.
4. **Debug.** Run `ZooKeeperServerMain.main` in debug mode. Breakpoints in `initializeAndRun` and `runFromConfig` take you through config parsing and server startup. The [standalone startup article](standalone-server-startup.html) continues from there.

> **Note:** the original article called the template `zoo_example.cfg`. This checkout ships `zoo_sample.cfg`.

A minimal `zoo.cfg` (replace the path with a real directory):

```properties
tickTime=2000
dataDir=/absolute/path/to/zookeeper-debug-data
clientPort=2181
```

Or start the server from a terminal with the module build outputs:

```sh
java -cp 'conf:zookeeper-server/target/classes:zookeeper-jute/target/classes:zookeeper-server/target/lib/*' \
  org.apache.zookeeper.server.ZooKeeperServerMain conf/zoo.cfg
```

This uses the Unix classpath separator `:`; use `;` on Windows.

## Dependency errors from the original setup

The original article hit two startup errors with the 3.6 source. Both come from the IDE launch leaving out `provided` dependencies, not from wrong versions:

| Error | Original workaround | Better fix |
| --- | --- | --- |
| `NoClassDefFoundError: com/codahale/metrics/Reservoir` | Upgrade `metrics-core` from 3.2.5 to 4.1.10. | Keep 3.2.5: it contains `Reservoir`, and the POM pins it on purpose. The jar is `provided` in the server POM, so add provided dependencies to the run classpath. |
| `ClassNotFoundException: org.xerial.snappy.SnappyInputStream` | Remove the `provided` scope from `snappy-java`. | Leave the POM alone. The distribution already ships the library; include provided dependencies in the IDE launch or use the distribution's `lib` classpath. |

## Next

With this setup you can jump between configuration, generated wire records, server startup and client code on one consistent source tree. Continue with [setting up a three-node ensemble](ensemble-setup.html) or go straight to [standalone server startup](standalone-server-startup.html).

## Pinned references

- [ZooKeeper 3.6.2 README and Java requirements](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/README.md)
- [Packaging and Maven build instructions](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/README_packaging.md)
- [Server module POM and dependency scopes](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/pom.xml)
- [Root POM and dependency versions](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/pom.xml)
- [Sample configuration](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/conf/zoo_sample.cfg)
- [ZooKeeperServerMain](https://github.com/apache/zookeeper/blob/803c7f1a12f85978cb049af5e4ef23bd8b688715/zookeeper-server/src/main/java/org/apache/zookeeper/server/ZooKeeperServerMain.java)
