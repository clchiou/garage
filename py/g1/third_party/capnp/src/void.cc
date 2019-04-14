#include <Python.h>

#include <boost/python/handle.hpp>
#include <boost/python/scope.hpp>
#include <boost/python/to_python_converter.hpp>

#include <capnp/common.h>

namespace capnp_python {

namespace {

//
// Define void type similar to how NoneType is defined.
//
// NOTE: Since C++ does not not fully support C designated initializers,
// we cannot define VOID_TYPE and VOID_AS_NUMBER in the idiomatic way.
//

PyTypeObject VOID_TYPE;

PyNumberMethods VOID_AS_NUMBER;

PyObject VOID_OBJECT = {_PyObject_EXTRA_INIT 1, &VOID_TYPE};

PyObject* voidNew(PyTypeObject*, PyObject* args, PyObject* kwargs) {
  if (PyTuple_GET_SIZE(args) || (kwargs && PyDict_GET_SIZE(kwargs))) {
    PyErr_SetString(PyExc_TypeError, "VoidType takes no arguments");
    return NULL;
  }
  Py_INCREF(&VOID_OBJECT);
  return &VOID_OBJECT;
}

PyObject* voidRepr(PyObject*) {
  return PyUnicode_FromString("Void");
}

int voidBool(PyObject*) {
  return 0;
}

void voidDealloc(PyObject*) {
  Py_FatalError("deallocating Void");
}

//
// Converter of capnp::Void.
//

struct VoidFromPython {

  VoidFromPython() {
    boost::python::converter::registry::push_back(
        &convertible,
        &construct,
        boost::python::type_id<capnp::Void>()  //
    );
  }

  static void* convertible(PyObject* object) { return object == &VOID_OBJECT ? object : nullptr; }

  static void construct(
      PyObject* object,
      boost::python::converter::rvalue_from_python_stage1_data* data  //
  ) {
    void* storage =
        ((boost::python::converter::rvalue_from_python_storage<capnp::Void>*)data)->storage.bytes;
    new (storage) capnp::Void();

    data->convertible = storage;
  }
};

struct VoidToPython {
  static PyObject* convert(const capnp::Void& void_) {
    Py_INCREF(&VOID_OBJECT);
    return &VOID_OBJECT;
  }
};

}  // namespace

void defineVoidType(void) {

  VOID_TYPE = {PyVarObject_HEAD_INIT(&PyType_Type, 0)};
  VOID_TYPE.tp_name = "capnp.VoidType";
  VOID_TYPE.tp_new = voidNew;
  VOID_TYPE.tp_flags = Py_TPFLAGS_DEFAULT;
  VOID_TYPE.tp_repr = voidRepr;
  VOID_TYPE.tp_as_number = &VOID_AS_NUMBER;
  VOID_TYPE.tp_dealloc = voidDealloc;

  VOID_AS_NUMBER.nb_bool = voidBool;

  boost::python::scope().attr("VoidType") =
      boost::python::handle<>(boost::python::borrowed(&VOID_TYPE));
  boost::python::scope().attr("VOID") =
      boost::python::handle<>(boost::python::borrowed(&VOID_OBJECT));

  VoidFromPython();
  boost::python::to_python_converter<capnp::Void, VoidToPython>();
}

}  // namespace capnp_python
