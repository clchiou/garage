BIN_SRCS := icmp.c udp.c
BINS := $(BIN_SRCS:.c=)
HEADERS := common.h
LIBS := common.c

CFLAGS := -std=c99 -Wall -Wextra -Werror

.PHONY: all clean

all: $(BINS)

clean:
	rm -f $(BINS)

$(BINS): %: %.c $(HEADERS) $(LIBS)
	$(CC) $(CFLAGS) -o $@ $< $(LIBS)
