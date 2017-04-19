#ifndef CAPNP_PYTHON_HACK_H_
#define CAPNP_PYTHON_HACK_H_

// This header must be the first included

namespace capnp_python {
template <typename T>
class ThrowingDtorHandler;
}  // namespace capnp_python

// Add ThrowingDtorHandler to boost::get_pointer
namespace boost {
template <typename T>
T* get_pointer(const capnp_python::ThrowingDtorHandler<T>& p) {
  return p.get();
}
}  // namespace boost

#endif  // CAPNP_PYTHON_HACK_H_
