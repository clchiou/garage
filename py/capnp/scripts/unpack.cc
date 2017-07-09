//
// Read and unpack data from stdin.
//

#include <unistd.h>

#include <kj/io.h>

#include <capnp/serialize-packed.h>

int main() {
  kj::FdInputStream fistream(STDIN_FILENO);
  kj::BufferedInputStreamWrapper bistream(fistream);
  capnp::_::PackedInputStream input(bistream);

  kj::FdOutputStream output(STDOUT_FILENO);

  uint8_t buffer[1024];
  // I don't know why, but to prevent "Premature EOF" exception, I need
  // minSize be very small (like 1).
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
