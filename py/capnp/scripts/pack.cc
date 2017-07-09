//
// Read and pack data from stdin.
//

#include <unistd.h>

#include <kj/io.h>

#include <capnp/serialize-packed.h>

int main() {
  // I don't know why, but to prevent "Premature EOF" exception, I can
  // not use kj::BufferedInputStreamWrapper here.
  kj::FdInputStream input(STDIN_FILENO);

  kj::FdOutputStream fostream(STDOUT_FILENO);
  kj::BufferedOutputStreamWrapper bostream(fostream);
  capnp::_::PackedOutputStream output(bostream);

  uint8_t buffer[1024];
  constexpr size_t minSize = 1;
  constexpr size_t maxSize = sizeof(buffer);
  size_t size = 0;
  do {
    size = input.tryRead(buffer, minSize, maxSize);
    if (size > 0) {
      output.write(buffer, size);
    }
  } while (size >= minSize);

  return 0;
}
