# C ABI for V8.

include common.mk

V8_CABI_OUT ?= out

CXX ?= g++
CXXFLAGS ?= \
	-I. \
	-I$(V8) \
	-std=c++11 \
	-pthread \
	-Wall \
	-Wextra \
	-Wnon-virtual-dtor \
	-Wpedantic \
	-Wno-long-long \
	-Wno-missing-field-initializers \
	-Wno-unused-parameter \
	-Werror \
	-O3 \
	-L$(V8_OUT)/$(V8_ARCH).$(V8_MODE)/lib.target \
	-fPIC \
	-fno-exceptions \
	-fno-rtti

SONAME := libv8_cabi.so

DIRS := $(V8_CABI_OUT) $(V8_CABI_OUT)/src
HDRS := $(wildcard include/*.h) $(wildcard src/*.h)
SRCS := $(wildcard src/*.cc)
OBJS := $(patsubst %.cc,$(V8_CABI_OUT)/%.o,$(SRCS))
DEPS := $(addsuffix .d,$(OBJS))

### Meta rules.

all: $(V8_CABI_OUT)/$(SONAME)

clean:
	rm -rf $(V8_CABI_OUT)

.PHONY: all clean

### Build rules.

$(V8_CABI_OUT)/$(SONAME): $(OBJS) | $(DIRS)
	$(CXX) $(CXXFLAGS) -shared -Wl,-soname,$(SONAME) -o $@ $< -lc -lv8

include $(DEPS)

$(DEPS) : %.d : %

$(OBJS) : $(V8_CABI_OUT)/%.o : %.cc | $(DIRS)
	$(CXX) $(CXXFLAGS) -MMD -MF $@.d -c -o $@ $<

$(DIRS):
	mkdir -p $@
