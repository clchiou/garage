#include <exception>
#include <memory>
#include <string>

#include <boost/python.hpp>
#include <boost/type_index.hpp>

class Error : public std::exception {
 public:
  const char* what() const noexcept { return "An error message"; }
};

namespace boom {
namespace boom {
namespace boom {

class Boom {
 public:
  Boom() = default;
  ~Boom() noexcept(false) { throw Error(); }
};

}  // namespace boom
}  // namespace boom
}  // namespace boom

using boom::boom::boom::Boom;

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
      // We are called by boost::python::objects::instance_dealloc, and
      // it doesn't expect an exception to be thrown from here, i.e.,
      // this is not wrapped inside boost::python::handle_exception; so
      // if we let exception leave here, the whole Python process will
      // be aborted.  On the other hand, we can't set a Python exception
      // either (i.e., calling PyErr_SetString) because Python doesn't
      // expect nor check if an exception is raised by tp_dealloc (plus
      // if there is already an active exception, you will override it).
      // The result is that this exception will be checked and raised at
      // a later point, making it very confusing.  I guess the action we
      // may take here is to log it, just like __del__.
      PySys_WriteStderr(
          "Exception thrown from a C++ destructor is ignored: %.200s - %.200s\n",
          boost::typeindex::type_id<T>().pretty_name().c_str(), exc.what());
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
  boost::python::class_<Boom, ThrowingDtorHandler<Boom>>("Boom");
}
