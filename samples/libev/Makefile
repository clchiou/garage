CC ?= gcc

CFLAGS := -std=gnu11 \
	-Wall \
	-Wextra \
	-Werror \
	-Wno-unused-parameter \
	-g

LDFLAGS := -lev

PROGS := rot13

SRCS := $(wildcard lib/*.c)
OBJS := $(SRCS:.c=.o)
DEPS := $(SRCS:.c=.d)


all: $(PROGS)

clean:
	rm -f $(PROGS) *.o *.d $(OBJS) $(DEPS)

.PHONY: all clean

$(PROGS) : % : %.o $(OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -MT $@ -MMD -MP -MF $*.d -c -o $@ $<

-include $(DEPS)
