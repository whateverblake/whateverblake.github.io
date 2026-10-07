---
layout: default
title: Setting up a Mooncake debugging environment
article: true
topic: Mooncake
order: 10
series_order: 0
nav_title: "Set up the debugging environment"
description: "Build Mooncake in Linux on a Mac and connect CLion to a remote debugging session."
---

# Setting up a Mooncake debugging environment

This guide builds a Linux debugging environment for Mooncake on an Apple
Silicon Mac. When you finish, you will have:

- a Docker container with every build tool and dependency,
- Mooncake compiled with debug symbols,
- a working GDB breakpoint, and
- CLion building and debugging inside the container over SSH.

The source stays on your Mac; Docker shares it with Linux. Every setup file is
shown in full, and only the public Mooncake source is used.

## 1. Download the source

Install Git, Python 3, Docker Desktop, and CLion. Start Docker Desktop.
This guide uses ARM64 Linux for Apple Silicon. On an Intel or AMD machine,
change the Compose platform to `linux/amd64` and the image tag to
`mooncake-debug:amd64`. That platform is not covered by this ARM64 setup.

Run these commands **on the Mac**:

```bash
docker version
docker compose version
mkdir -p "$HOME/mooncake-debug-guide"
cd "$HOME/mooncake-debug-guide"
git clone https://github.com/kvcache-ai/Mooncake.git mooncake
cd mooncake
git checkout --detach 719735896c86b56fabec6cf3e825fb2ea640597a
git submodule update --init --recursive
mkdir -p debug-lab/.local
chmod 700 debug-lab/.local
printf '\n/debug-lab/\n' >> .git/info/exclude
```

This checks out `v0.3.13.post1` at a fixed commit, so you read the same source
as this series. Submodules are extra repositories the build needs. The last
line keeps your local setup files and credentials out of `git status`.

> **Where to run commands:** unless a step says otherwise, run everything
> **on the Mac, from this Mooncake source root**.

## 2. Create the Docker files

Create these files in your editor. The sections below provide their complete
contents and explain what they do.

```text
mooncake/
└── debug-lab/
    ├── Dockerfile
    ├── ccache.conf
    ├── entrypoint.sh
    ├── .dockerignore
    ├── compose.yaml
    └── .local/
```

### Dockerfile: install the build tools

Create `debug-lab/Dockerfile`:

```dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
# CPU build dependencies from this release's dependencies.sh; Go and accelerator
# SDKs are unnecessary with the lab's CMake options.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates build-essential cmake ninja-build ccache git wget curl unzip \
    libibverbs-dev libgoogle-glog-dev libgflags-dev libjsoncpp-dev libunwind-dev \
    libnuma-dev libpython3-dev python3-dev libboost-all-dev libssl-dev \
    libgrpc-dev libgrpc++-dev libprotobuf-dev libyaml-cpp-dev protobuf-compiler-grpc \
    libcurl4-openssl-dev libhiredis-dev liburing-dev libjemalloc-dev libmsgpack-dev \
    libzmq3-dev libzstd-dev libasio-dev libxxhash-dev pkg-config patchelf \
    gdb openssh-server rsync tcpdump iproute2 procps file binutils sudo \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -s /bin/bash debugger && \
    passwd -d debugger && \
    mkdir -p /run/sshd /workspace/build /home/debugger/.ssh && \
    chown -R debugger:debugger /workspace /home/debugger/.ssh && \
    chmod 700 /home/debugger/.ssh && \
    printf '%s\n' 'PasswordAuthentication yes' 'PermitEmptyPasswords no' \
      'KbdInteractiveAuthentication no' 'PermitRootLogin yes' \
      'PubkeyAuthentication yes' 'AllowUsers debugger root' \
      > /etc/ssh/sshd_config.d/mooncake.conf
COPY ccache.conf /etc/ccache.conf
# PAM imports /etc/environment for Remote Host SSH commands as well as shells.
RUN printf '%s\n' \
      'CMAKE_C_COMPILER_LAUNCHER=/usr/bin/ccache' \
      'CMAKE_CXX_COMPILER_LAUNCHER=/usr/bin/ccache' >> /etc/environment
COPY entrypoint.sh /usr/local/bin/lab-entrypoint
RUN chmod +x /usr/local/bin/lab-entrypoint
EXPOSE 22
ENTRYPOINT ["/usr/local/bin/lab-entrypoint"]
```

`FROM` selects Ubuntu 24.04. The package list installs GCC, CMake, Ninja, GDB,
SSH, and Mooncake's C/C++ dependencies. Some development libraries are needed
for compilation even though we will use CPU memory and TCP without an RDMA
network device.

The image creates the `debugger` user for builds and debugging. `COPY` uses the
files we create next. The image does not contain the Mooncake source or its
compiled programs; those are added through directory mounts at runtime.

### ccache.conf: save compiler results

Create `debug-lab/ccache.conf`:

```text
# One shared cache in the persistent Compose build volume.
cache_dir = /workspace/build/ccache
max_size = 10G
# Combined with the setgid cache directory, allow root and debugger to share it.
umask = 002
```

Ccache reuses previous compiler results to speed up later builds. Its directory
is inside the persistent build volume. The limit is 10 GB, and root and
`debugger` can share the cache.

### entrypoint.sh: prepare Linux at startup

Create `debug-lab/entrypoint.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
install -o debugger -g debugger -m 600 /run/lab-key.pub /home/debugger/.ssh/authorized_keys
root_password=$(cat /run/lab-root-password)
test -n "$root_password"
printf 'root:%s\n' "$root_password" | chpasswd
unset root_password
chown debugger:debugger /workspace/build
install -d -o debugger -g debugger -m 2775 /workspace/build/ccache
# Also persist the limit in the cache itself, overriding any older cache config.
sudo -u debugger ccache --max-size=10G
ssh-keygen -A
exec /usr/sbin/sshd -D -e
```

The startup script does five things:

1. Install the public SSH key for `debugger`.
2. Read the mounted root password file and apply it inside Linux.
3. Give `debugger` access to the build directory and cache.
4. Apply the 10 GB cache limit and create the SSH server's host keys.
5. Start SSH in the foreground to keep the container running.

The Dockerfile makes this program executable. CLion uses key authentication.
Root password login is also available in this local lab; its password is
supplied at startup and is not stored in the image.

### .dockerignore: exclude credentials from image builds

Create `debug-lab/.dockerignore`:

```text
.local
__pycache__
```

Docker excludes these directories from the files sent to the image builder.

### compose.yaml: define the running container

Create `debug-lab/compose.yaml`:

```yaml
name: mooncake-debug-lab
services:
  lab:
    container_name: mooncake-debug
    image: mooncake-debug:arm64
    platform: linux/arm64
    build:
      context: .
    init: true
    ports:
      - "127.0.0.1:33333:22"
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
    mem_limit: 8g
    shm_size: 256m
    volumes:
      - ..:/workspace/mooncake
      - build:/workspace/build
      - ./.local/id_ed25519.pub:/run/lab-key.pub:ro
      - ./.local/root_password:/run/lab-root-password:ro
    working_dir: /workspace/mooncake
volumes:
  build:
```

| Setting | Meaning |
| --- | --- |
| `build.context: .` | Build using the files in `debug-lab/` |
| `image` | Name the result `mooncake-debug:arm64` |
| `platform` | Use ARM64 Linux |
| `127.0.0.1:33333:22` | Forward local Mac port 33333 to SSH port 22 in Linux |
| `SYS_PTRACE` and `seccomp=unconfined` | Allow the debugger to inspect processes |
| `mem_limit: 8g` | Limit the container to 8 GiB of memory |
| `..:/workspace/mooncake` | Share the Mac's source directory with Linux |
| `build:/workspace/build` | Keep build output in a persistent Docker volume |
| Credential mounts ending in `:ro` | Make these files read-only inside Linux |

Relative paths start from the directory containing `compose.yaml`, so `..`
means the Mooncake source root. See the
[Docker Compose build reference](https://docs.docker.com/reference/compose-file/build/).

Only SSH is published to the Mac, on its loopback address. Port 2222 stays free
for other containers. Before starting, make sure no other container uses the
name `mooncake-debug` or port 33333.

## 3. Create the SSH credentials

Generate a key pair on the Mac:

```bash
ssh-keygen -t ed25519 -N '' -C mooncake-debug-lab \
  -f debug-lab/.local/id_ed25519
```

The `.pub` file is the public key installed in Linux. The other file is the
private key used by CLion. If these files already exist, keep them instead of
overwriting them.

Create the root password file with this command. Python asks for the password
without displaying it and gives the file permissions that allow only your user
to read and write it:

```bash
python3 - <<'PY'
import getpass
import os
from pathlib import Path

password_file = Path("debug-lab/.local/root_password")
if password_file.exists():
    raise SystemExit("Password file already exists; keep the existing credential.")
password = getpass.getpass("Choose a root SSH password: ")
if not password:
    raise SystemExit("Password must not be empty.")
fd = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write(password + "\n")
PY
```

Keep the password file and private key out of Git.

## 4. Build the Docker image and start Linux

Build the image:

```bash
docker compose -f debug-lab/compose.yaml build lab
```

This downloads Ubuntu, installs the packages and creates
`mooncake-debug:arm64`. The first build takes several minutes.

The same build without Compose is below. Run one or the other, not both:

```bash
docker build --platform linux/arm64 \
  -t mooncake-debug:arm64 \
  -f debug-lab/Dockerfile debug-lab
```

Start the container in the background and check its status:

```bash
docker compose -f debug-lab/compose.yaml up -d
docker compose -f debug-lab/compose.yaml ps
```

Test SSH by running one command inside Linux:

```bash
ssh -i debug-lab/.local/id_ed25519 -o IdentitiesOnly=yes \
  -p 33333 debugger@127.0.0.1 'uname -m'
```

On the first connection, accept the SSH host key for this local container.
The command should print `aarch64` and return to your Mac terminal.

If startup fails, inspect the output:

```bash
docker compose -f debug-lab/compose.yaml logs lab
```

Check that both mounted credential files exist as files, and that port 33333
is free.

## 5. Configure Mooncake with CMake

CMake creates the build rules. Ninja then uses those rules to compile the
source. Run this command on the Mac; `docker exec` runs CMake inside Linux:

```bash
docker exec -u debugger mooncake-debug \
  cmake -S /workspace/mooncake -B /workspace/build -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug -DENABLE_DEBUG_SYMBOLS=ON \
  -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF \
  -DENABLE_SCCACHE=OFF \
  -DCMAKE_C_COMPILER_LAUNCHER=/usr/bin/ccache \
  -DCMAKE_CXX_COMPILER_LAUNCHER=/usr/bin/ccache \
  -DWITH_STORE=ON -DWITH_TE=ON \
  -DUSE_TCP=ON -DUSE_CUDA=OFF -DUSE_TENT=OFF \
  -DUSE_ETCD=OFF -DUSE_HTTP=ON -DUSE_REDIS=OFF \
  -DSTORE_USE_ETCD=OFF -DSTORE_USE_REDIS=OFF -DSTORE_USE_K8S_LEASE=OFF \
  -DWITH_STORE_RUST=OFF -DWITH_STORE_GO=OFF \
  -DWITH_P2P_STORE=OFF -DWITH_EP=OFF \
  -DBUILD_UNIT_TESTS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_BENCHMARK=OFF
```

`-S` selects the source directory. `-B` selects the build directory. Each `-D`
sets a CMake option:

| Options | Reason |
| --- | --- |
| `Debug`, `ENABLE_DEBUG_SYMBOLS=ON` | Keep source information for stepping through C++ code |
| `CMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF` | Disable optimization across compiled files |
| C/C++ compiler launchers | Use ccache for both compilers |
| `ENABLE_SCCACHE=OFF` | Keep the separate sccache tool disabled |
| `WITH_STORE=ON`, `WITH_TE=ON`, `USE_TCP=ON` | Build Store and the TCP transfer path |
| `USE_CUDA=OFF`, `USE_TENT=OFF` | Use CPU memory and the original Transfer Engine |
| etcd, Redis, and Kubernetes options set to `OFF` | Leave these service backends out |
| Rust, Go, P2P Store, and EP options set to `OFF` | Leave these components out |
| Tests, examples, and benchmarks set to `OFF` | Limit the build to the components needed here |

Keep `USE_HTTP=ON` for this version. The master source needs a metadata plugin
header included under that option. The build option does not start an HTTP
server by itself.

CMake may download more source dependencies, so configuration also needs
internet access. We will build the existing `mooncake_master` and
`mooncake_client` targets from the public source.

## 6. Compile and test a breakpoint

For a terminal build, run:

```bash
docker exec -u debugger mooncake-debug \
  cmake --build /workspace/build --parallel 2 \
  --target mooncake_master mooncake_client
```

Two jobs limit memory use during compilation. Check the resulting programs:

```bash
docker exec -u debugger mooncake-debug \
  ls -lh /workspace/build/mooncake-store/src/mooncake_master \
         /workspace/build/mooncake-store/src/mooncake_client
```

Test GDB with a new process that stops at the start of `main`:

```bash
docker exec -u debugger mooncake-debug \
  gdb -q -batch \
  -ex 'set confirm off' \
  -ex 'break main' \
  -ex run \
  -ex bt \
  -ex quit \
  --args /workspace/build/mooncake-store/src/mooncake_master
```

GDB starts the master and stops at `main`. `bt` prints the call stack and
`quit` ends the process. You should see a breakpoint hit with a source location
in `mooncake-store/src/master.cpp`.

This proves that symbols and source mapping work. It does not test Put or Get;
those need running services, which the next articles start.

## 7. Connect CLion

Open the Mooncake source folder in CLion. In **Settings → Build, Execution,
Deployment → Toolchains**, create a **Remote Host (SSH)** toolchain named
**Mooncake Docker**:

| Setting | Value |
| --- | --- |
| SSH host and port | `127.0.0.1:33333` |
| User | `debugger` |
| Private key | The absolute Mac path to `debug-lab/.local/id_ed25519` |
| CMake | `/usr/bin/cmake` |
| Build tool | `/usr/bin/ninja` |
| C compiler | `/usr/bin/gcc` |
| C++ compiler | `/usr/bin/g++` |
| Debugger | `/usr/bin/gdb` |

Let CLion check the connection and detect the tools. Map the local Mooncake
source folder to `/workspace/mooncake`. Use the deployment type **Local or
mounted folder** because Docker already shares the source. Avoid uploading it
to a second remote directory. See
[CLion's remote development guide](https://www.jetbrains.com/help/clion/remote-projects-support.html).

In **Settings → Build, Execution, Deployment → CMake**, create this profile:

| Setting | Value |
| --- | --- |
| Name | `Mooncake Debug` |
| Toolchain | `Mooncake Docker` |
| Build type | `Debug` |
| Generator | `Ninja` |
| Build directory | `/workspace/build` |
| Build options | `--parallel 2` |

In **CMake options**, paste the `-D...` options from step 5, separated by spaces.
Do not paste `docker exec`, `cmake`, `-S`, `-B`, `-G`, or the trailing shell
backslashes. CLion supplies the other arguments from its settings.

Reload CMake. Select or create a **CMake Application** run configuration for
`mooncake_master` using this profile. Keep **Before launch → Build** enabled.
Set a breakpoint in `main` in `mooncake-store/src/master.cpp`, then press Debug.
Stop the session after it reaches the breakpoint.

From now on CLion configures, builds and debugs. The terminal commands above
are only an alternative that shows what the IDE does for you.

## 8. Rebuild and stop the environment

After changing C++ source, build in CLion or repeat the build command from
step 6. Restart any running Mooncake process that needs the new executable.

After changing the Dockerfile, startup program, or cache configuration, run:

```bash
docker compose -f debug-lab/compose.yaml build lab
docker compose -f debug-lab/compose.yaml up -d
```

For Compose-only changes, the `up -d` command is enough. Container replacement
ends the SSH sessions and processes inside it; connect again before debugging.

Stop the container while keeping it for later:

```bash
docker compose -f debug-lab/compose.yaml stop
```

Start it again with `docker compose -f debug-lab/compose.yaml up -d`.
To remove the container while keeping its build volume, run:

```bash
docker compose -f debug-lab/compose.yaml down
```

The volume keeps compiled files and `/workspace/build/ccache` across container
replacement. Do not add `--volumes` to `down` if you want to keep them.
