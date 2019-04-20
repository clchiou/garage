// You must include this before including boost headers.
#include "resource-types-fwd.h"

#include <boost/python/class.hpp>

#include <capnp/schema-loader.h>

#include "maybe.h"
#include "resource-types.h"
#include "special-methods.h"

namespace capnp_python {

void defineSchemaLoaderType(void) {
#include "resource-types-def-macros.h"

  {
    // For now, do not handle argument defaults for get, getType, etc.
    RESOURCE_CLASS_(capnp::SchemaLoader, "SchemaLoader", boost::python::init<>())
        .DEF(get)
        .DEF(tryGet)
        .DEF(getUnbound)
        .DEF(getType)
        .DEF(load)
        .DEF(loadOnce)
        .DEF_R_CONST(getAllLoaded, kj::Array<capnp::Schema>);
  }

  // tryGet returns kj::Maybe<capnp::Schema>.
  MaybeToPythonConverter<capnp::Schema>();

  // getAllLoaded returns kj::Array<capnp::Schema>.
  {
    // Add leading underscore to the exported name as we do not want
    // this class to be created or explicitly referenced by user.
    RESOURCE_CLASS_(kj::Array<capnp::Schema>, "_Array_Schema", boost::python::no_init)
        .DEF_LEN()
        .DEF_GETITEM(capnp::Schema);
  }

#include "resource-types-undef-macros.h"
}

}  // namespace capnp_python
