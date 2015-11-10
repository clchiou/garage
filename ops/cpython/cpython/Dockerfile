# Build cpython from source.

FROM ubuntu:15.10

MAINTAINER Che-Liang Chiou <clchiou@gmail.com>

# Location of cpython source repo.
ARG CPYTHON_REPO=https://hg.python.org/cpython

# Revision of cpython to build.
ARG CPYTHON_REV=v3.5.0

RUN apt-get update \
 && apt-get --yes install \
        # Generally useful tools.
        git \
        rsync \
        # For fetching cpython.
        mercurial \
        # Build dependencies for cpython:
        build-essential \
        libc6-dev \
        # Compression.
        libbz2-dev \
        liblzma-dev \
        zlib1g-dev \
        # Console.
        libncursesw5-dev \
        libreadline-dev \
        # Database.
        libdb-dev \
        libgdbm-dev \
        libsqlite3-dev \
        # Network.
        libssl-dev \
 && cd /home \
 && hg clone ${CPYTHON_REPO} cpython \
 && cd cpython \
 && hg update ${CPYTHON_REV} \
 && ./configure \
 && make \
 && make install
