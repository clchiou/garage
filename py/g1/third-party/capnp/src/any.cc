#include <string>

#include <boost/python/class.hpp>
#include <boost/python/enum.hpp>
#include <boost/python/operators.hpp>
#include <boost/python/scope.hpp>

#include <capnp/any.h>
#include <capnp/blob.h>
#include <capnp/common.h>
#include <capnp/dynamic.h>

#include "resource-types.h"
#include "special-methods.h"
#include "value-types.h"

//
// Notes to implementer:
//
// * The nullptr constructor of builder types is not really usable (the
//   objects constructed this way may result in SEGFAULT when used); so
//   do not expose it.
//
// * TODO: Expose Pipeline.
//
// * TODO: Expose adopt/disown (this requires more support on move
//   semantics).
//
// * TODO: Expose DynamicCapability (it is not exposed becasue we do not
//   intend to use Cap'n Proto's RPC system at the moment).
//

namespace capnp_python {

namespace {

#define SCOPE_CLASS_(NAME)     \
  using Scope = capnp::NAME;   \
  std::string qualname(#NAME); \
  boost::python::scope _ = boost::python::class_<Scope>(#NAME, boost::python::no_init)

// You need a tmp string to prevent std::bad_alloc error.
#define CLASS_(NAME, INIT)                \
  using Scope = Scope::NAME;              \
  std::string tmp = qualname + "." #NAME; \
  std::string qualname = tmp;             \
  boost::python::scope _ =                \
      boost::python::class_<Scope>(#NAME, INIT).setattr("__qualname__", qualname)

#define DEF(NAME) def(#NAME, &Scope::NAME)

#define DEF_TEMPLATED_GETTER(NAME, R, ...) \
  def(#NAME #R,                            \
      static_cast<RETURN_TYPE(capnp::R) (Scope::*)(__VA_ARGS__)CONST>(&Scope::NAME<capnp::R>))

#define DEF_TEMPLATED_SETTER(NAME, T) \
  def(#NAME #T, static_cast<void (Scope::*)(capnp::ReaderFor<capnp::T>)>(&Scope::NAME<capnp::T>))

void defineAnyList(void) {
  SCOPE_CLASS_(AnyList);

  {
    CLASS_(Reader, boost::python::init<>())
        .DEF(getElementSize)
        .DEF(size)
        .DEF(getRawBytes)
        .def(boost::python::self == boost::python::self)
        .def(boost::python::self != boost::python::self)
        .DEF(totalSize);
  }

  {
    CLASS_(Builder, boost::python::no_init)
        .DEF(getElementSize)
        .DEF(size)
        .def(boost::python::self == boost::python::other<capnp::AnyList::Reader>())
        .def(boost::python::self != boost::python::other<capnp::AnyList::Reader>())
        .DEF(asReader);
  }
}

void defineAnyStruct(void) {
  SCOPE_CLASS_(AnyStruct);

  {
#define CONST const
#define RETURN_TYPE(T) capnp::ReaderFor<T>

    CLASS_(Reader, boost::python::init<>())
        .DEF(totalSize)
        .DEF(getDataSection)
        // TODO: Expose capnp::List<capnp::AnyPointer>::Reader.
        // .DEF(getPointerSection)
        .def(
            "canonicalize",
            &MemberFuncReturningResource<capnp::AnyStruct::Reader, kj::Array<capnp::word>>::
                memberFunc<&capnp::AnyStruct::Reader::canonicalize>)
        .def(boost::python::self == boost::python::self)
        .def(boost::python::self != boost::python::self)
        .DEF_TEMPLATED_GETTER(as, DynamicStruct, capnp::StructSchema);

#undef CONST
#undef RETURN_TYPE
  }

  {
#define CONST
#define RETURN_TYPE(T) capnp::BuilderFor<T>

    CLASS_(Builder, boost::python::no_init)
        .DEF(getDataSection)
        // TODO: Expose capnp::List<capnp::AnyPointer>::Builder.
        // .DEF(getPointerSection)
        .def(boost::python::self == boost::python::other<capnp::AnyStruct::Reader>())
        .def(boost::python::self != boost::python::other<capnp::AnyStruct::Reader>())
        .DEF(asReader)
        .DEF_TEMPLATED_GETTER(as, DynamicStruct, capnp::StructSchema);

#undef CONST
#undef RETURN_TYPE
  }
}

void defineAnyPointer(void) {
  SCOPE_CLASS_(AnyPointer);

  {
#define CONST const
#define RETURN_TYPE(T) capnp::ReaderFor<T>

    CLASS_(Reader, boost::python::init<>())
        .DEF(targetSize)
        .DEF(getPointerType)
        .DEF(isNull)
        .DEF(isStruct)
        .DEF(isList)
        .DEF(isCapability)
        .def(boost::python::self == boost::python::self)
        .def(boost::python::self != boost::python::self)
        .DEF_TEMPLATED_GETTER(getAs, Data)
        .DEF_TEMPLATED_GETTER(getAs, Text)
        .DEF_TEMPLATED_GETTER(getAs, DynamicStruct, capnp::StructSchema)
        .DEF_TEMPLATED_GETTER(getAs, DynamicList, capnp::ListSchema);

#undef CONST
#undef RETURN_TYPE
  }

  {
#define CONST
#define RETURN_TYPE(T) capnp::BuilderFor<T>

    CLASS_(Builder, boost::python::no_init)
        .DEF(targetSize)
        .DEF(getPointerType)
        .DEF(isNull)
        .DEF(isStruct)
        .DEF(isList)
        .DEF(isCapability)
        .def(boost::python::self == boost::python::other<capnp::AnyPointer::Reader>())
        .def(boost::python::self != boost::python::other<capnp::AnyPointer::Reader>())
        .DEF(clear)
        .DEF_TEMPLATED_GETTER(getAs, Data)
        .DEF_TEMPLATED_GETTER(getAs, Text)
        .DEF_TEMPLATED_GETTER(getAs, DynamicStruct, capnp::StructSchema)
        .DEF_TEMPLATED_GETTER(getAs, DynamicList, capnp::ListSchema)
        .DEF_TEMPLATED_GETTER(initAs, Data, uint)
        .DEF_TEMPLATED_GETTER(initAs, Text, uint)
        .DEF_TEMPLATED_GETTER(initAs, DynamicStruct, capnp::StructSchema)
        .DEF_TEMPLATED_GETTER(initAs, DynamicList, capnp::ListSchema, uint)
        .DEF(initAsAnyList)
        .DEF(initAsListOfAnyStruct)
        .DEF(initAsAnyStruct)
        .DEF_TEMPLATED_SETTER(setAs, Data)
        .DEF_TEMPLATED_SETTER(setAs, Text)
        .DEF_TEMPLATED_SETTER(setAs, DynamicStruct)
        .DEF_TEMPLATED_SETTER(setAs, DynamicList)
        .DEF_TEMPLATED_SETTER(setCanonicalAs, Data)
        .DEF_TEMPLATED_SETTER(setCanonicalAs, Text)
        // TODO: Figure out why these two do not work.
        // .DEF_TEMPLATED_SETTER(setCanonicalAs, DynamicStruct)
        // .DEF_TEMPLATED_SETTER(setCanonicalAs, DynamicList)
        .DEF(set)
        .DEF(setCanonical)
        .DEF(asReader);

#undef CONST
#undef RETURN_TYPE
  }
}

#undef SCOPE_CLASS_
#undef CLASS_
#undef DEF
#undef DEF_TEMPLATED_GETTER
#undef DEF_TEMPLATED_SETTER

}  // namespace

void defineAnyTypes(void) {

#define ENUM_(NAME)          \
  using Scope = capnp::NAME; \
  boost::python::enum_<Scope>(#NAME)
#define VALUE(NAME) value(#NAME, Scope::NAME)

  // Define in common.h.
  {
    ENUM_(ElementSize)
        .VALUE(VOID)
        .VALUE(BIT)
        .VALUE(BYTE)
        .VALUE(TWO_BYTES)
        .VALUE(FOUR_BYTES)
        .VALUE(EIGHT_BYTES)
        .VALUE(POINTER)
        .VALUE(INLINE_COMPOSITE);
  }

  // Define in common.h.
  { ENUM_(PointerType).VALUE(NULL_).VALUE(STRUCT).VALUE(LIST).VALUE(CAPABILITY); }

  { ENUM_(Equality).VALUE(NOT_EQUAL).VALUE(EQUAL).VALUE(UNKNOWN_CONTAINS_CAPS); }

#undef ENUM_
#undef VALUE

  defineAnyList();
  defineAnyStruct();
  defineAnyPointer();
}

}  // namespace capnp_python
