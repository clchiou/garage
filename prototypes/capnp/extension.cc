#include <exception>
#include <memory>
#include <type_traits>

template <typename T>
class ThrowingDtorHandler;

namespace boost {
template <typename T>
T* get_pointer(const ThrowingDtorHandler<T>& p) {
  return p.get();
}
}  // namespace boost

#include <boost/python.hpp>
#include <boost/type_index.hpp>

class Error : public std::exception {
 public:
  const char* what() const noexcept { return "An error message"; }
};

namespace bOom {
namespace boOm {
namespace booM {

class Boom {
 public:
  Boom() = default;
  ~Boom() noexcept(false) { throw Error(); }
};

}  // namespace booM
}  // namespace boOm
}  // namespace bOom

using bOom::boOm::booM::Boom;

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
  void _reset(void) {
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

namespace boost {
namespace python {

// Tag ThrowingDtorHandler type as a smart pointer
template <typename T>
struct pointee<ThrowingDtorHandler<T>> {
  typedef T type;
};

}  // namespace python
}  // namespace boost

BOOST_PYTHON_MODULE(extension) {
  boost::python::class_<Boom, ThrowingDtorHandler<Boom>>("Boom").def(
      "_reset", &ThrowingDtorHandler<Boom>::_reset);
}
