ARG XMRIG_VERSION=6.26.0
FROM debian:bookworm-slim AS build
ARG XMRIG_VERSION
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git cmake make g++ gcc libuv1-dev libssl-dev libhwloc-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 --branch "v${XMRIG_VERSION}" https://github.com/xmrig/xmrig.git . \
    && mkdir build && cd build \
    && cmake .. -DWITH_OPENCL=OFF -DWITH_CUDA=OFF \
    && make -j"$(nproc)"

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libuv1 libhwloc15 libssl3 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/build/xmrig /usr/local/bin/xmrig
COPY miner/entrypoint.sh /usr/local/bin/xmrig-entrypoint
RUN chmod +x /usr/local/bin/xmrig-entrypoint
ENV XMRIG_THREADS=auto
ENTRYPOINT ["/usr/local/bin/xmrig-entrypoint"]
