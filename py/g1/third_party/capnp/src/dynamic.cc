#include <string>

#include <boost/python/class.hpp>
#include <boost/python/enum.hpp>
#include <boost/python/scope.hpp>

#include <capnp/dynamic.h>

#include "special-methods.h"
#include "value-types.h"

//
// Notes to implementer:
//
// * Boost.Python does not set __qualname__ properly, and we have to
//   provide __qualname__ for it; this helps debug output.
//
// * For now, for each type X, we expose X::Reader and X::Builder, and
//   omit X::Pipeline.
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
#define CLASS_(NAME, INIT, ...)           \
  using Scope = Scope::NAME;              \
  std::string tmp = qualname + "." #NAME; \
  std::string qualname = tmp;             \
  boost::python::scope _ =                \
      boost::python::class_<Scope, ##__VA_ARGS__>(#NAME, INIT).setattr("__qualname__", qualname)

#define DEF(NAME) def(#NAME, &Scope::NAME)

#define DEF_CAST(NAME, E) def(#NAME, &Scope::operator E)

#define DEF_LEN() def("__len__", &Scope::size)
#define DEF_GETITEM(E) def("__getitem__", SpecialMethods<Scope, E>::getitem)

#define DEF_OVERLOAD(NAME, R, ...) def(#NAME, static_cast<R (Scope::*)(__VA_ARGS__)>(&Scope::NAME))
#define DEF_OVERLOAD_CONST(NAME, R, ...) \
  def(#NAME, static_cast<R (Scope::*)(__VA_ARGS__) const>(&Scope::NAME))

#define ENUM_(NAME)          \
  using Scope = Scope::NAME; \
  boost::python::enum_<Scope>(#NAME)
#define VALUE(NAME) value(#NAME, Scope::NAME)

void defineDynamicValue(void) {
  SCOPE_CLASS_(DynamicValue);

  {
    ENUM_(Type)
        .VALUE(UNKNOWN)
        .VALUE(VOID)
        .VALUE(BOOL)
        .VALUE(INT)
        .VALUE(UINT)
        .VALUE(FLOAT)
        .VALUE(TEXT)
        .VALUE(DATA)
        .VALUE(LIST)
        .VALUE(ENUM)
        .VALUE(STRUCT)
        .VALUE(CAPABILITY)
        .VALUE(ANY_POINTER);
  }

  // Internally, DynamicValue stores the largest numerical type
  // (int64_t, double, etc.).  So it probably make sense to expose one
  // constructor for each Type enum member, not all constructors.
#define DEF_CTOR(NAME, E) \
  def("from" #NAME, SpecialMethods<Scope, E>::constructor).staticmethod("from" #NAME)

#define DEF_AS(NAME, E) def("as" #NAME, &Scope::as<E>)

  {
    CLASS_(Reader, boost::python::init<>(), ValueHolder<capnp::DynamicValue::Reader>)
        .DEF_CTOR(Void, capnp::Void)
        .DEF_CTOR(Bool, bool)
        .DEF_CTOR(Int, long long)
        .DEF_CTOR(Uint, unsigned long long)
        .DEF_CTOR(Float, double)
        .DEF_CTOR(Text, const capnp::Text::Reader&)
        .DEF_CTOR(Data, const capnp::Data::Reader&)
        .DEF_CTOR(DynamicList, const capnp::DynamicList::Reader&)
        .DEF_CTOR(DynamicEnum, capnp::DynamicEnum)
        .DEF_CTOR(DynamicStruct, capnp::DynamicStruct::Reader&)
        .DEF_CTOR(AnyPointer, capnp::AnyPointer::Reader&)
        .DEF_CTOR(ConstSchema, capnp::ConstSchema)
        .DEF_CTOR(DynamicValue, const capnp::DynamicValue::Reader&)
        .DEF_AS(Void, capnp::Void)
        .DEF_AS(Bool, bool)
        .DEF_AS(Int, int64_t)
        .DEF_AS(Uint, uint64_t)
        .DEF_AS(Float, double)
        .DEF_AS(Text, capnp::Text)
        .DEF_AS(Data, capnp::Data)
        .DEF_AS(DynamicList, capnp::DynamicList)
        .DEF_AS(DynamicEnum, capnp::DynamicEnum)
        .DEF_AS(DynamicStruct, capnp::DynamicStruct)
        .DEF_AS(AynPointer, capnp::AnyPointer)
        .DEF_AS(DynamicValue, capnp::DynamicValue)
        .DEF(getType);
  }

  {
    CLASS_(Builder, boost::python::init<>(), ValueHolder<capnp::DynamicValue::Builder>)
        .DEF_CTOR(Void, capnp::Void)
        .DEF_CTOR(Bool, bool)
        .DEF_CTOR(Int, long long)
        .DEF_CTOR(Uint, unsigned long long)
        .DEF_CTOR(Float, double)
        .DEF_CTOR(Text, capnp::Text::Builder)
        .DEF_CTOR(Data, capnp::Data::Builder)
        .DEF_CTOR(DynamicList, capnp::DynamicList::Builder)
        .DEF_CTOR(DynamicEnum, capnp::DynamicEnum)
        .DEF_CTOR(DynamicStruct, capnp::DynamicStruct::Builder)
        .DEF_CTOR(AnyPointer, capnp::AnyPointer::Builder)
        .DEF_CTOR(DynamicValue, capnp::DynamicValue::Builder&)
        .DEF_AS(Void, capnp::Void)
        .DEF_AS(Bool, bool)
        .DEF_AS(Int, int64_t)
        .DEF_AS(Uint, uint64_t)
        .DEF_AS(Float, double)
        .DEF_AS(Text, capnp::Text)
        .DEF_AS(Data, capnp::Data)
        .DEF_AS(DynamicList, capnp::DynamicList)
        .DEF_AS(DynamicEnum, capnp::DynamicEnum)
        .DEF_AS(DynamicStruct, capnp::DynamicStruct)
        .DEF_AS(AynPointer, capnp::AnyPointer)
        .DEF_AS(DynamicValue, capnp::DynamicValue)
        .DEF(getType)
        .DEF(asReader);
  }

#undef DEF_CTOR
#undef DEF_AS
}

void defineDynamicStruct(void) {
  SCOPE_CLASS_(DynamicStruct);

  {
    CLASS_(Reader, boost::python::init<>())
        .DEF_CAST(asAnyStruct, capnp::AnyStruct::Reader)
        .DEF(totalSize)
        .DEF(getSchema)
        .DEF_OVERLOAD_CONST(get, capnp::DynamicValue::Reader, capnp::StructSchema::Field)
        .DEF_OVERLOAD_CONST(has, bool, capnp::StructSchema::Field, capnp::HasMode)
        .DEF(which)
        .DEF_OVERLOAD_CONST(get, capnp::DynamicValue::Reader, kj::StringPtr)
        .DEF_OVERLOAD_CONST(has, bool, kj::StringPtr, capnp::HasMode);
  }

  {
    CLASS_(Builder, boost::python::init<>())
        .DEF_CAST(asAnyStruct, capnp::AnyStruct::Builder)
        .DEF(totalSize)
        .DEF(getSchema)
        .DEF_OVERLOAD(get, capnp::DynamicValue::Builder, capnp::StructSchema::Field)
        .DEF_OVERLOAD(has, bool, capnp::StructSchema::Field, capnp::HasMode)
        .DEF(which)
        .DEF_OVERLOAD(set, void, capnp::StructSchema::Field, const capnp::DynamicValue::Reader&)
        .DEF_OVERLOAD(init, capnp::DynamicValue::Builder, capnp::StructSchema::Field)
        .DEF_OVERLOAD(init, capnp::DynamicValue::Builder, capnp::StructSchema::Field, uint)
        .DEF_OVERLOAD(clear, void, capnp::StructSchema::Field)
        .DEF_OVERLOAD(get, capnp::DynamicValue::Builder, kj::StringPtr)
        .DEF_OVERLOAD(has, bool, kj::StringPtr, capnp::HasMode)
        .DEF_OVERLOAD(set, void, kj::StringPtr, const capnp::DynamicValue::Reader&)
        .DEF_OVERLOAD(init, capnp::DynamicValue::Builder, kj::StringPtr)
        .DEF_OVERLOAD(init, capnp::DynamicValue::Builder, kj::StringPtr, uint)
        .DEF_OVERLOAD(clear, void, kj::StringPtr)
        .DEF(asReader);
  }

  // which returns kj::Maybe<capnp::StructSchema::Field>.  Its converter
  // is defined in schema.cc.
}

void defineDynamicEnum(void) {
  using boost::python::args;
  using boost::python::init;
  using Scope = capnp::DynamicEnum;
  boost::python::class_<Scope>("DynamicEnum", init<>())
      .def(init<capnp::EnumSchema::Enumerant>(args("enumerant")))
      .def(init<capnp::EnumSchema, uint16_t>(args("schema", "value")))
      .DEF(getSchema)
      .DEF(getEnumerant)
      .DEF(getRaw);

  // getEnumerant returns kj::Maybe<capnp::EnumSchema::Enumerant>.  Its
  // converter is defined in schema.cc.
}

void defineDynamicList(void) {
  SCOPE_CLASS_(DynamicList);

  {
    CLASS_(Reader, boost::python::init<>())
        .DEF_CAST(asAnyList, capnp::AnyList::Reader)
        .DEF(getSchema)
        .DEF_LEN()
        .DEF_GETITEM(capnp::DynamicValue::Reader);
  }

  {
    CLASS_(Builder, boost::python::init<>())
        .DEF_CAST(asAnyList, capnp::AnyList::Builder)
        .DEF(getSchema)
        .DEF_LEN()
        .DEF_GETITEM(capnp::DynamicValue::Builder)
        .DEF(set)
        .DEF(init)
        .DEF(copyFrom)
        .DEF(asReader);
  }
}

#undef SCOPE_CLASS_
#undef CLASS_
#undef DEF
#undef DEF_CAST
#undef DEF_LEN
#undef DEF_GETITEM
#undef DEF_OVERLOAD
#undef DEF_OVERLOAD_CONST

}  // namespace

void defineDynamicValueTypes(void) {

  {
    using Scope = capnp::HasMode;
    boost::python::enum_<capnp::HasMode>("HasMode").VALUE(NON_NULL).VALUE(NON_DEFAULT);
  }

  defineDynamicValue();
  defineDynamicStruct();
  defineDynamicEnum();
  defineDynamicList();
}

}  // namespace capnp_python
