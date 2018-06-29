#
# Build test program of libpng.
#

CFLAGS := -std=c11 -Wall -Wextra $(shell pkg-config --cflags libjpeg libpng)
LDFLAGS := $(shell pkg-config --libs libjpeg libpng)

include ../build.mk
