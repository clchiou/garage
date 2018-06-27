#
# Build test programs of libjpeg-turbo.
#

CFLAGS := -std=c11 -Wall -Wextra $(shell pkg-config --cflags libjpeg)
LDFLAGS := $(shell pkg-config --libs libjpeg)

include ../build.mk
