CC ?= gcc

CFLAGS := -std=gnu11 \
	-Wall \
	-Wextra \
	-Werror \
	-Wno-unused-parameter \
	-I.
ifdef DEBUG
CFLAGS += -g
else
CFLAGS += -DNDEBUG
endif
ifdef INCLUDE_DIRS
CFLAGS += $(INCLUDE_DIRS)
endif

ifdef LIBRARY_DIRS
LDFLAGS += $(LIBRARY_DIRS)
else
LDFLAGS :=
endif

HTTP2D := http2d/http2d
HTTP2D_SRCS := $(wildcard http2d/*.c)
HTTP2D_OBJS := $(HTTP2D_SRCS:.c=.o)

ROT13 := rot13/rot13-copy rot13/rot13-nocopy
ROT13_SRCS := $(wildcard rot13/*.c)
ROT13_OBJS := $(ROT13_SRCS:.c=.o)

LIB_SRCS := $(wildcard lib/*.c)
LIB_OBJS := $(LIB_SRCS:.c=.o)

OBJS := $(HTTP2D_OBJS) $(ROT13_OBJS) $(LIB_OBJS)
DEPS := $(OBJS:.o=.d)


all: $(HTTP2D) $(ROT13)

clean:
	rm -f $(HTTP2D) $(ROT13) $(OBJS) $(DEPS)

.PHONY: all clean

$(HTTP2D): $(HTTP2D_OBJS) $(LIB_OBJS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^ -lev -lnghttp2

$(ROT13): %: %.o rot13/rot13.o $(LIB_OBJS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^ -lev

%.o: %.c
	$(CC) $(CFLAGS) -MT $@ -MMD -MP -MF $*.d -c -o $@ $<

-include $(DEPS)
