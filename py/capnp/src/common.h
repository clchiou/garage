#ifndef CAPNP_PYTHON_COMMON_H_
#define CAPNP_PYTHON_COMMON_H_

#include <exception>
#include <memory>

#include <boost/noncopyable.hpp>
#include <boost/python/bases.hpp>
#include <boost/python/class_fwd.hpp>
#include <boost/python/pointee.hpp>

namespace capnp_python {

template <typename T, typename Bases = boost::python::bases<>>
using AbstractType = boost::python::class_<T, Bases, boost::noncopyable>;

// Cap'n Proto allows throwing destructors (and resource types are not
// copyable); so we need shared_ptr with a custom deleter to expose
// them to Boost.Python.
template <typename T>
class ThrowingDtorHandler : public std::shared_ptr<T> {
 public:
  // Boost.Python pointer_holder class uses this constructor only
  ThrowingDtorHandler(T* obj)
      : std::shared_ptr<T>(obj, ThrowingDtorHandler::deleter) {}

 private:
  // Handle resource types' throwing destructor
  static void deleter(T* resource) {
    try {
      delete resource;
    } catch (const std::exception& exc) {
      // TODO: Define a Python exception class
      PyErr_SetString(PyExc_RuntimeError, exc.what());
    }
  }
};

template <typename T, typename Bases = boost::python::bases<>>
using ResourceType =
    boost::python::class_<T, Bases, ThrowingDtorHandler<T>, boost::noncopyable>;

// At the moment we don't use smart pointer for value types
template <typename T, typename Bases = boost::python::bases<>>
using ValueType = boost::python::class_<T, Bases>;

void defineSchemaCapnp(void);

void defineResourceTypes(void);
void defineValueTypes(void);

}  // namespace capnp_python

namespace boost {
namespace python {

// Tag capnp_python::ThrowingDtorHandler type as a smart pointer
template <typename T>
struct pointee<capnp_python::ThrowingDtorHandler<T>> {
  typedef T type;
};

}  // namespace python
}  // namespace boost

// Helper for selecting from overloaded (member) functions
#define DEF_FUNC(NS, F, R, ARGS...) \
  boost::python::def(#F, static_cast<R (*)(ARGS)>(NS::F))
#define DEF_MF(M, R, T, ARGS...) def(#M, static_cast<R (T::*)(ARGS)>(&T::M))
#define DEF_MF_CONST(M, R, T, ARGS...) \
  def(#M, static_cast<R (T::*)(ARGS) const>(&T::M))

#endif  // CAPNP_PYTHON_COMMON_H_
