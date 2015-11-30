# Build samples.

include ../common.mk

V8CABI_OUT ?= ../out

CC ?= gcc
CXX ?= g++
CFLAGS := \
	-I../include \
	-std=c99 \
	-pthread \
	-Wall \
	-Wextra \
	-Wpedantic \
	-Werror \
	-O3 \
	-L$(V8_OUT)/$(V8_ARCH).$(V8_MODE)/lib.target \
	-L$(V8_OUT)/$(V8_ARCH).$(V8_MODE)/obj.target/tools/gyp \
	-L$(V8CABI_OUT) \
	-fPIC

DIRS := $(V8CABI_OUT) $(V8CABI_OUT)/samples
SRCS := hello_world.c
LIBS := -licui18n -licuuc -lv8 -lv8_libbase -lv8_libplatform -lv8_cabi
OBJS := $(patsubst %.c,$(V8CABI_OUT)/samples/%.o,$(SRCS))
BINS := $(patsubst %.c,$(V8CABI_OUT)/samples/%,$(SRCS))
DEPS := $(addsuffix .d,$(OBJS))

# Meta rules.

all: $(BINS)

clean:
	rm -rf $(V8CABI_OUT)

.PHONY: all clean

# Build rules.

include $(DEPS)

$(DEPS) : %.d : %

$(OBJS) : $(V8CABI_OUT)/samples/%.o : %.c | $(DIRS)
	$(CC) $(CFLAGS) -MMD -MF $@.d -c -o $@ $<

$(BINS) : % : %.o | $(DIRS)
	$(CXX) $(CFLAGS) -o $@ -Wl,--start-group $< $(LIBS) -Wl,--end-group -ldl -lrt

$(DIRS):
	mkdir -p $@
