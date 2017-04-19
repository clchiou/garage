// Definition of the extension module

#include "hack.h"

#include <boost/python/module.hpp>

#include "common.h"

BOOST_PYTHON_MODULE(_capnp) {
  capnp_python::defineSchemaCapnp();
  capnp_python::defineResourceTypes();
  capnp_python::defineValueTypes();
}
