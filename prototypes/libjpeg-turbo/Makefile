#
# Build test programs of libjpeg-turbo.
#

CC := gcc
CFLAGS := -std=c11 -Wall -Wextra $(shell pkg-config --cflags libjpeg)
LDFLAGS := $(shell pkg-config --libs libjpeg)

SOURCES := $(wildcard *.c)
EXECUTABLES := $(patsubst %.c,%,$(SOURCES))

all: $(EXECUTABLES)

clean:
	rm -f $(EXECUTABLES)

.PHONY: all clean

% : %.c
	$(CC) $(CFLAGS) $^ $(LDFLAGS) -o $@
