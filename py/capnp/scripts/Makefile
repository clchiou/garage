all: pack unpack

clean:
	rm -f pack unpack

%: %.cc
	g++ -std=c++11 -Wall -Wextra -Wno-unused-parameter -o $@ $< $$(pkg-config --libs --cflags capnp)

.PHONY: all clean
