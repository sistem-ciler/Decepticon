# BitNet Inference Server Dockerfile
# Builds bitnet.cpp with optimized kernels and starts llama-server
FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git wget curl \
    python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy BitNet source
COPY . /build/

# Build bitnet.cpp with optimal settings for the target platform
# Auto-detect architecture and select appropriate kernel
RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=gcc \
    -DCMAKE_CXX_COMPILER=g++ \
    -DGGML_AVX2=ON \
    -DGGML_FMA=ON \
    -DGGML_F16C=ON \
    -DGGML_AVX512=OFF \
    && cmake --build build -j$(nproc) --config Release

# Runtime image
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip curl wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/bitnet

# Copy build artifacts
COPY --from=builder /build/build/bin/llama-server /opt/bitnet/bin/llama-server
COPY --from=builder /build/build/bin/llama-cli /opt/bitnet/bin/llama-cli
COPY --from=builder /build/build/bin/llama-quantize /opt/bitnet/bin/llama-quantize
COPY --from=builder /build/*.py /opt/bitnet/
COPY --from=builder /build/utils /opt/bitnet/utils
COPY --from=builder /build/include /opt/bitnet/include

# Copy our service wrapper
COPY bitnet_service.py /opt/bitnet/

# Create directories
RUN mkdir -p /opt/bitnet/models /opt/bitnet/logs

ENV PATH="/opt/bin:${PATH}"
ENV BITNET_PORT=8080
ENV BITNET_MODEL=bitnet-2b
ENV BITNET_THREADS=4
ENV BITNET_CTX_SIZE=4096

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["python3", "/opt/bitnet/bitnet_service.py"]
CMD ["--model", "bitnet-2b", "--host", "0.0.0.0", "--port", "8080"]
