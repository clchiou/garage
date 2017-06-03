#ifndef CAPNP_PYTHON_COMMON_H_
#define CAPNP_PYTHON_COMMON_H_

#include <exception>
#include <memory>
#include <type_traits>

#include <boost/noncopyable.hpp>
#include <boost/python/bases.hpp>
#include <boost/python/class_fwd.hpp>
#include <boost/python/errors.hpp>
#include <boost/python/pointee.hpp>
#include <boost/type_index.hpp>

namespace capnp_python {

template <typename T, typename Bases = boost::python::bases<>>
using AbstractType = boost::python::class_<T, Bases, boost::noncopyable>;

// Cap'n Proto allows throwing destructors (and resource types are not
// copyable); so we need shared_ptr with a custom deleter to expose
// them to Boost.Python.
template <typename T>
class ThrowingDtorHandler {
 public:
  // Boost.Python pointer_holder class uses this constructor only
  ThrowingDtorHandler(T* ptr) : ptr_(ptr, ThrowingDtorHandler::deleter) {}

  //
  // This is called by boost::python::objects::instance_dealloc.  Since
  // it doesn't expect an exception to be thrown (i.e., wrapping this is
  // call inside boost::python::handle_exception), we cannot call
  // throw_error_already_set, or the Python process will be terminated.
  //
  // On the other hand, we can't set a Python exception either (i.e.,
  // calling PyErr_SetString) because Python doesn't expect nor check if
  // an exception is raised by tp_dealloc (plus, if there is already an
  // active exception, you will override it - although to be honest, I
  // can't trigger this error case).  I guess the only action we may
  // take here is to log it, just like __del__.
  //
  ~ThrowingDtorHandler() {
    PyObject *type, *value, *traceback;
    PyErr_Fetch(&type, &value, &traceback);
    ptr_.reset();
    if (PyErr_Occurred()) {
      PySys_WriteStderr("Exception was thrown from destructor of %.200s\n",
                        boost::typeindex::type_id<T>().pretty_name().c_str());
      PyErr_Print();
    }
    PyErr_Restore(type, value, traceback);
  }

  // Give user the ability to call destructor explicitly and handle any
  // exception it may throw
  void reset(void) {
    ptr_.reset();
    if (PyErr_Occurred()) {
      boost::python::throw_error_already_set();
    }
  }

  T* get() const noexcept { return ptr_.get(); }
  T* operator->() const noexcept { return get(); }
  typename std::add_lvalue_reference<T>::type operator*() const noexcept { return *get(); }

 private:
  std::shared_ptr<T> ptr_;

  // Handle resource types' throwing destructor.  Because shared_ptr's
  // disposer is noexcept, if the exception leaves the deleter, the
  // Python process will be terminated immediately.
  static void deleter(T* resource) noexcept {
    try {
      delete resource;
    } catch (const std::exception& exc) {
      PyErr_SetString(PyExc_RuntimeError, exc.what());
    }
  }
};

template <typename T, typename Bases = boost::python::bases<>>
using ResourceType = boost::python::class_<T, Bases, ThrowingDtorHandler<T>, boost::noncopyable>;

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
#define DEF_FUNC(NS, F, R, ARGS...) boost::python::def(#F, static_cast<R (*)(ARGS)>(NS::F))
#define DEF_MF(M, R, T, ARGS...) def(#M, static_cast<R (T::*)(ARGS)>(&T::M))
#define DEF_MF_CONST(M, R, T, ARGS...) def(#M, static_cast<R (T::*)(ARGS) const>(&T::M))

#define DEF_RESET(T) def("_reset", &capnp_python::ThrowingDtorHandler<T>::reset)

#endif  // CAPNP_PYTHON_COMMON_H_
