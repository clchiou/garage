#include <exception>
#include <iostream>
#include <memory>
#include <string>

#include <boost/python.hpp>

class Error : public std::exception {
 public:
  const char* what() const noexcept { return "An error message"; }
};

class Boom {
 public:
  Boom() = default;
  ~Boom() noexcept(false) { throw Error(); }
};

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
      std::cerr << "Dtor throws: " << std::string(exc.what()) << std::endl;
      PyErr_SetString(PyExc_RuntimeError, exc.what());
      // Unfortunately you cannot call throw_error_already_set() here,
      // which throws an exception and triggers exception translation,
      // because you are in the destructor :(
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
