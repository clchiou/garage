#include <Python.h>

// You must include this before including boost headers.
#include "resource-types-fwd.h"

#include <boost/python/class.hpp>
#include <boost/python/def.hpp>
#include <boost/python/errors.hpp>

#include <kj/common.h>
#include <kj/debug.h>

#include "resource-types.h"

namespace capnp_python {
namespace test {

namespace {

class DummyResource {
 public:
  static int numCtor;
  static int numMove;
  static int numDtor;
  DummyResource() { numCtor++; }
  DummyResource(DummyResource&&) { numMove++; }
  KJ_DISALLOW_COPY(DummyResource);
  ~DummyResource() { numDtor++; }
};

int DummyResource::numCtor = 0;
int DummyResource::numMove = 0;
int DummyResource::numDtor = 0;

class DummyResourceFactory {
 public:
  DummyResource make() { return DummyResource(); }
};

class ThrowingDtorResource {
 public:
  ThrowingDtorResource() {}
  KJ_DISALLOW_COPY(ThrowingDtorResource);
  ~ThrowingDtorResource() noexcept(false) { KJ_FAIL_REQUIRE("Test ThrowingDtorResource"); }
};

void testErrorIndicator(void) {
  PyErr_SetString(PyExc_RuntimeError, "Test error indicator");
  {
    // Its destructor should not overwrite the above error indicator.
    capnp_python::ResourceSharedPtr<ThrowingDtorResource>(new ThrowingDtorResource());
  }
  if (PyErr_Occurred()) {
    boost::python::throw_error_already_set();
  }
}

}  // namespace

void defineResourceTypesForTesting(void) {
#include "resource-types-def-macros.h"
  {
    RESOURCE_CLASS_(DummyResource, "DummyResource")
        .def_readonly("numCtor", &DummyResource::numCtor)
        .def_readonly("numMove", &DummyResource::numMove)
        .def_readonly("numDtor", &DummyResource::numDtor);
  }
  { RESOURCE_CLASS_(DummyResourceFactory, "DummyResourceFactory").DEF_R(make, DummyResource); }
  { RESOURCE_CLASS_(ThrowingDtorResource, "ThrowingDtorResource"); }
#include "resource-types-undef-macros.h"
  boost::python::def("testErrorIndicator", testErrorIndicator);
}

}  // namespace test
}  // namespace capnp_python
