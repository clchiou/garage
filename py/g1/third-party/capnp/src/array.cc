// You must include this before including boost headers.
#include "resource-types-fwd.h"

#include <boost/python/class.hpp>

#include <kj/array.h>
#include <kj/common.h>

#include <capnp/common.h>

#include "resource-types.h"

namespace capnp_python {

void defineArrayTypes(void) {
#include "resource-types-def-macros.h"

  {
    RESOURCE_CLASS_(kj::Array<kj::byte>, "_Array_byte", boost::python::no_init)
        .DEF_LEN()
        .def(
            "asBytes",
            static_cast<kj::ArrayPtr<const kj::byte> (Type::*)() const>(&Type::asBytes)  //
        );
  }

  {
    RESOURCE_CLASS_(kj::Array<capnp::word>, "_Array_word", boost::python::no_init)
        .DEF_LEN()
        .def(
            "asBytes",
            static_cast<kj::ArrayPtr<const kj::byte> (Type::*)() const>(&Type::asBytes)  //
        );
  }

#include "resource-types-undef-macros.h"
}

}  // namespace capnp_python
