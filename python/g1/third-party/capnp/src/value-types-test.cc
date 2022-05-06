#include <boost/python/class.hpp>

#include <kj/debug.h>

#include "value-types.h"

namespace capnp_python {
namespace test {

namespace {

class ThrowingDtorValue {
 public:
  static int numCtor;
  static int numCopy;
  static int numMove;
  static int numDtor;

  ThrowingDtorValue() : moved(false) { numCtor++; }

  ThrowingDtorValue(const ThrowingDtorValue& other) : moved(false) {
    numCopy++;
    KJ_REQUIRE(!other.moved, "Copy from moved value");
  }
  ThrowingDtorValue& operator=(const ThrowingDtorValue& other) {
    numCopy++;
    KJ_REQUIRE(!other.moved, "Copy from moved value");
    return *this;
  }

  ThrowingDtorValue(ThrowingDtorValue&& other) : moved(false) {
    other.moved = true;
    numMove++;
  }

  ~ThrowingDtorValue() noexcept(false) {
    numDtor++;
    KJ_REQUIRE(moved, "Test dtor throw");
  }

  bool moved;
};

int ThrowingDtorValue::numCtor = 0;
int ThrowingDtorValue::numCopy = 0;
int ThrowingDtorValue::numMove = 0;
int ThrowingDtorValue::numDtor = 0;

}  // namespace

void defineValueTypesForTesting(void) {
  boost::python::class_<ThrowingDtorValue, ValueHolder<ThrowingDtorValue>>("ThrowingDtorValue")
      .def_readonly("numCtor", &ThrowingDtorValue::numCtor)
      .def_readonly("numCopy", &ThrowingDtorValue::numCopy)
      .def_readonly("numMove", &ThrowingDtorValue::numMove)
      .def_readonly("numDtor", &ThrowingDtorValue::numDtor);
}

}  // namespace test
}  // namespace capnp_python
