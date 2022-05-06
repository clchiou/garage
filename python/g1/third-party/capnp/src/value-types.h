#ifndef CAPNP_PYTHON_VALUE_TYPES_H_
#define CAPNP_PYTHON_VALUE_TYPES_H_

#include <exception>
#include <utility>

#include <Python.h>

#include <boost/type_index.hpp>

namespace capnp_python {

// Some value type's destructor is declared noexcept(false), and
// Boost.Python hates that; let's work around this.
template <typename T>
class ValueHolder : public T {
 public:
  ValueHolder(PyObject*) {}
  ValueHolder(PyObject*, const T& value) : T(const_cast<T&>(value)) {}
  ~ValueHolder() noexcept(true) {
    try {
      // Move this object into a temporary object so that we may catch
      // any potential exception from destructor here.  After std::move,
      // this object is "dead", and its destructor is basically a no-op
      // (given that its move constructor is properly written).
      T(std::move(*this));
    } catch (const std::exception& exc) {
      PySys_WriteStderr(
          "Exception was thrown from destructor of %.200s\n%.200s\n",
          boost::typeindex::type_id<T>().pretty_name().c_str(),
          exc.what()  //
      );
    }
  }
};

}  // namespace capnp_python

#endif  // CAPNP_PYTHON_VALUE_TYPES_H_
