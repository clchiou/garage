#ifndef CAPNP_PYTHON_RESOURCE_TYPES_FWD_H_
#define CAPNP_PYTHON_RESOURCE_TYPES_FWD_H_

//
// NOTE: I don't know why, but this header must be included before Boost
// headers so that boost::get_pointer overload is added first.
//

namespace capnp_python {

template <typename T>
class ResourceSharedPtr;

}  // namespace capnp_python

namespace boost {

// Add ResourceSharedPtr to boost::get_pointer overloads.
template <typename T>
T* get_pointer(const capnp_python::ResourceSharedPtr<T>& p) {
  return p.get();
}

}  // namespace boost

#endif  // CAPNP_PYTHON_RESOURCE_TYPES_FWD_H_
