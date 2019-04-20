#ifndef CAPNP_PYTHON_RESOURCE_TYPES_H_
#define CAPNP_PYTHON_RESOURCE_TYPES_H_

#include <exception>
#include <memory>
#include <type_traits>
#include <utility>

#include <Python.h>

#include <boost/noncopyable.hpp>
#include <boost/python/class_fwd.hpp>
#include <boost/python/errors.hpp>
#include <boost/python/pointee.hpp>
#include <boost/type_index.hpp>

namespace capnp_python {

// Cap'n Proto allows throwing destructors.  In addition, its resource
// types are only movable and not copyable.  So we need a custom shared
// pointer to manage these types in to Boost.Python.
template <typename T>
class ResourceSharedPtr {
 public:
  // Boost.Python pointer_holder class uses this constructor only.
  ResourceSharedPtr(T* ptr) : ptr_(ptr, ResourceSharedPtr::deleter) {}

  // This is called by boost::python::objects::instance_dealloc.  Since
  // it doesn't expect an exception to be thrown (i.e., wrapping this is
  // call inside boost::python::handle_exception), we cannot call
  // throw_error_already_set, or the Python process will be terminated.
  //
  // On the other hand, we can't set a Python exception either (i.e.,
  // calling PyErr_SetString) because Python doesn't expect nor check if
  // an exception is raised by tp_dealloc.
  ~ResourceSharedPtr() {
    PyObject *type, *value, *traceback;
    PyErr_Fetch(&type, &value, &traceback);
    {
      PyObject *type, *value, *traceback;
      PyErr_GetExcInfo(&type, &value, &traceback);
      PyErr_SetExcInfo(NULL, NULL, NULL);

      // NOTE: I think it is okay to call ptr_.reset as it only resets
      // this shared_ptr object, not all other share_ptr objects that
      // points to the same underlying resource, and only when it is the
      // last shared_object, ptr_.reset will call the deleter.
      ptr_.reset();
      if (PyErr_Occurred()) {
        PySys_WriteStderr(
            "Exception was thrown from destructor of %.200s\n",
            boost::typeindex::type_id<T>().pretty_name().c_str());
        // This also clears the error indicator.
        PyErr_Print();
      }

      PyErr_SetExcInfo(type, value, traceback);
    }
    PyErr_Restore(type, value, traceback);
  }

  // Give user the ability to call destructor explicitly and handle any
  // exception it may throw.
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
  // disposer is declared as noexcept, exception should not leave the
  // deleter; otherwise the Python process will be terminated
  // immediately.
  static void deleter(T* resource) noexcept {
    try {
      delete resource;
    } catch (const std::exception& exc) {
      PyErr_SetString(PyExc_RuntimeError, exc.what());
    }
  }
};

// It seems that Boost.Python does a lot of copying on (result) objects,
// which is not friendly to member functions that returns resources.
// This generates wrapper functions that move result resource into a
// ResourceSharedPtr.
template <typename T, typename R, typename... Args>
struct MemberFuncReturningResource {

  typedef R (T::*ConstMemberFuncType)(Args...) const;
  typedef R (T::*NonCostMemberFuncType)(Args...);
  typedef std::conditional_t<
      std::is_const<T>::value,  // is_const_v is added in C++17.
      ConstMemberFuncType,
      NonCostMemberFuncType>
      MemberFuncType;

  template <MemberFuncType mfptr>
  static ResourceSharedPtr<R> memberFunc(T& obj, Args&&... args) {
    return ResourceSharedPtr<R>(new R((obj.*mfptr)(std::forward<Args>(args)...)));
  }
};

}  // namespace capnp_python

namespace boost {
namespace python {

// Tag capnp_python::ResourceSharedPtr type as a smart pointer.
template <typename T>
struct pointee<capnp_python::ResourceSharedPtr<T>> {
  typedef T type;
};

}  // namespace python
}  // namespace boost

#endif  // CAPNP_PYTHON_RESOURCE_TYPES_H_
