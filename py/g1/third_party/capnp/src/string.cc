#include <Python.h>

#include <boost/python/errors.hpp>
#include <boost/python/to_python_converter.hpp>

#include <kj/common.h>
#include <kj/string.h>

#include <capnp/common.h>

namespace capnp_python {

namespace {

//
// Converter of kj::ArrayPtr<kj::byte>>, etc.
//
// NOTE: kj::ArrayPtr is not owning.
//

template <typename T, typename E>
struct ArrayLikeFromPython {

  ArrayLikeFromPython() {

    boost::python::converter::registry::push_back(
        &convertibleBytes,
        &constructBytes,
        boost::python::type_id<T>()  //
    );

    boost::python::converter::registry::push_back(
        &convertibleMemoryView,
        &constructMemoryView,
        boost::python::type_id<T>()  //
    );
  }

  static void* convertibleBytes(PyObject* object) {
    return PyBytes_Check(object) ? object : nullptr;
  }

  static void constructBytes(
      PyObject* object,
      boost::python::converter::rvalue_from_python_stage1_data* data  //
  ) {
    void* buffer = PyBytes_AsString(object);
    if (!buffer) {
      boost::python::throw_error_already_set();
    }

    Py_ssize_t size = PyBytes_Size(object);

    void* storage = ((boost::python::converter::rvalue_from_python_storage<T>*)data)->storage.bytes;
    new (storage) T(static_cast<E*>(buffer), static_cast<size_t>(size));

    data->convertible = storage;
  }

  static void* convertibleMemoryView(PyObject* object) {
    return PyMemoryView_Check(object) ? object : nullptr;
  }

  static void constructMemoryView(
      PyObject* object,
      boost::python::converter::rvalue_from_python_stage1_data* data  //
  ) {
    Py_buffer* buffer = PyMemoryView_GET_BUFFER(object);

    void* storage = ((boost::python::converter::rvalue_from_python_storage<T>*)data)->storage.bytes;
    new (storage) T(static_cast<E*>(buffer->buf), static_cast<size_t>(buffer->len));

    data->convertible = storage;
  }
};

template <typename T>
struct ArrayLikeToPython {
  static PyObject* convert(const T& array) {
    // To convert const unsigned char* and const char*, you need
    // reinterpret_cast.
    PyObject* mview = PyMemoryView_FromMemory(
        const_cast<char*>(reinterpret_cast<const char*>(array.begin())),
        static_cast<Py_ssize_t>(array.size()),
        PyBUF_READ  //
    );
    if (!mview) {
      boost::python::throw_error_already_set();
    }
    return mview;
  }
};

template <typename T>
using ArrayLikeToPythonConverter = boost::python::to_python_converter<T, ArrayLikeToPython<T>>;

//
// Converter of kj::StringPtr, etc.
//
// NOTE: kj::StringPtr is not owning.
//
template <typename T>
struct StringPtrFromPython {

  StringPtrFromPython() {

    boost::python::converter::registry::push_back(
        &convertibleStr,
        &constructStr,
        boost::python::type_id<T>()  //
    );

    boost::python::converter::registry::push_back(
        &convertibleMemoryView,
        &constructMemoryView,
        boost::python::type_id<T>()  //
    );
  }

  static void* convertibleStr(PyObject* object) {
    return PyUnicode_Check(object) ? object : nullptr;
  }

  static void constructStr(
      PyObject* object,
      boost::python::converter::rvalue_from_python_stage1_data* data  //
  ) {
    Py_ssize_t size;
    const char* buffer = PyUnicode_AsUTF8AndSize(object, &size);
    if (!buffer) {
      boost::python::throw_error_already_set();
    }

    void* storage = ((boost::python::converter::rvalue_from_python_storage<T>*)data)->storage.bytes;
    new (storage) T(buffer, static_cast<size_t>(size));

    data->convertible = storage;
  }

  static void* convertibleMemoryView(PyObject* object) {
    return PyMemoryView_Check(object) ? object : nullptr;
  }

  static void constructMemoryView(
      PyObject* object,
      boost::python::converter::rvalue_from_python_stage1_data* data  //
  ) {
    Py_buffer* buffer = PyMemoryView_GET_BUFFER(object);

    void* storage = ((boost::python::converter::rvalue_from_python_storage<T>*)data)->storage.bytes;
    new (storage) T(static_cast<const char*>(buffer->buf), static_cast<size_t>(buffer->len));

    data->convertible = storage;
  }
};

//
// Converter of kj and capnp string-like object to Python memory view.
//
template <typename T>
struct StringLikeToPython {
  static PyObject* convert(const T& strLike) {
    PyObject* mview = PyMemoryView_FromMemory(
        const_cast<char*>(strLike.cStr()),
        static_cast<Py_ssize_t>(strLike.size()),
        PyBUF_READ  //
    );
    if (!mview) {
      boost::python::throw_error_already_set();
    }
    return mview;
  }
};

template <typename T>
using StringLikeToPythonConverter = boost::python::to_python_converter<T, StringLikeToPython<T>>;

}  // namespace

//
// Export string types.
//
void defineStringTypes(void) {

  ArrayLikeFromPython<kj::ArrayPtr<const kj::byte>, const kj::byte>();
  ArrayLikeToPythonConverter<kj::ArrayPtr<kj::byte>>();
  ArrayLikeToPythonConverter<kj::ArrayPtr<const kj::byte>>();

  ArrayLikeFromPython<kj::ArrayPtr<const capnp::word>, const capnp::word>();
  ArrayLikeToPythonConverter<kj::ArrayPtr<capnp::word>>();
  ArrayLikeToPythonConverter<kj::ArrayPtr<const capnp::word>>();

  StringPtrFromPython<kj::StringPtr>();
  StringLikeToPythonConverter<kj::StringPtr>();
}

}  // namespace capnp_python
