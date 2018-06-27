#
# Build rules for sample programs (one .c file per executable).
#

SOURCES := $(wildcard *.c)
EXECUTABLES := $(patsubst %.c,%,$(SOURCES))

all: $(EXECUTABLES)

clean:
	rm -f $(EXECUTABLES)

.PHONY: all clean

% : %.c ../common.c
	$(CC) $(CFLAGS) -I.. $^ $(LDFLAGS) -o $@
