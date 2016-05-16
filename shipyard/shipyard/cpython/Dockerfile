FROM scratch

ADD rootfs.tar /

ENV LD_LIBRARY_PATH=/usr/local/lib PYTHONIOENCODING=UTF-8

USER nobody

ENTRYPOINT ["/usr/local/bin/python3"]
