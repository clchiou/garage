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

LIBS := -lev

ROT13 := rot13-copy rot13-nocopy
ROT13_SRCS := $(wildcard rot13/*.c)
ROT13_OBJS := $(ROT13_SRCS:.c=.o)

LIB_SRCS := $(wildcard lib/*.c)
LIB_OBJS := $(LIB_SRCS:.c=.o)

OBJS := $(ROT13_OBJS) $(LIB_OBJS)
DEPS := $(ROT13_SRCS:.c=.d) $(LIB_SRCS:.c=.d)


all: $(ROT13)

clean:
	rm -f $(ROT13) $(OBJS) $(DEPS)

.PHONY: all clean

$(ROT13): %: rot13/%.o rot13/rot13.o $(LIB_OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LIBS)

%.o: %.c
	$(CC) $(CFLAGS) -MT $@ -MMD -MP -MF $*.d -c -o $@ $<

-include $(DEPS)
