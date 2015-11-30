# Default values.
#
# V8: Path to v8 repo.
# V8_OUT: Path to v8 build output (default to "$(V8)/out").
# V8_ARCH: v8 build arch (default to "x64").
# V8_MODE: v8 build mode (default to "release").

ifndef V8
$(error V8 is undefined)
endif

V8_OUT ?= $(V8)/out

V8_ARCH ?= x64
V8_MODE ?= release
