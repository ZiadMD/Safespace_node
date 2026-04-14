FROM ubuntu:22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    libopencv-dev \
    qt6-base-dev \
    libgl1-mesa-dev \
    libboost-system-dev \
    libboost-thread-dev \
    libssl-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Uncomment when SRC files are ready to compile:
# RUN mkdir build && cd build && \
#    cmake .. -DCMAKE_BUILD_TYPE=Release && \
#    make -j$(nproc)

CMD ["/bin/bash"]
