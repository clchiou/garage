#include <string>

#include <Python.h>

#include <boost/python/class.hpp>
#include <boost/python/enum.hpp>
#include <boost/python/errors.hpp>
#include <boost/python/operators.hpp>
#include <boost/python/scope.hpp>

#include <capnp/common.h>
#include <capnp/dynamic.h>
#include <capnp/schema.h>

#include "list.h"
#include "maybe.h"
#include "special-methods.h"

//
// Notes to implementer:
//
// * capnp defines schema objects in capnp itself, and then wraps the
//   generated "raw" schema objects to provide higher level interface.
//
// * The raw schema objects are defined in capnp::schema namespace, and
//   the high-level interface is defined in top-level capnp namespace.
//
// * Boost.Python does not set __qualname__ properly, and we have to
//   provide __qualname__ for it; this helps debug output.
//

namespace capnp_python {

namespace schema {
namespace {

//
// Exposing capnp::schema "raw" objects to Python.
//
// For now, for each type X, we only expose X::Reader, and omit
// X::Builder and X::Pipeline; for convenience, we just name the the
// reader type X, not X.Reader.
//

#define CLASS_(...) _GET_3RD_ARG(__VA_ARGS__, _CLASS_2_ARGS_, _CLASS_1_ARGS_)(__VA_ARGS__)
#define _GET_3RD_ARG(arg1, arg2, arg3, ...) arg3
// You need a tmp string to prevent std::bad_alloc error.
#define _CLASS_1_ARGS_(NAME) \
  std::string tmp(qualname); \
  std::string qualname(tmp); \
  _CLASS_2_ARGS_(Scope, NAME)
#define _CLASS_2_ARGS_(SCOPE, NAME)                                                     \
  using Scope = SCOPE::NAME;                                                            \
  using Reader = Scope::Reader;                                                         \
  qualname += "." #NAME;                                                                \
  boost::python::scope _ = boost::python::class_<Reader>(#NAME, boost::python::no_init) \
                               .setattr("__qualname__", qualname)                       \
                               .def("totalSize", &Reader::totalSize)                    \
                               .def("toString", &Reader::toString)

#define DEF(FIELD) def(#FIELD, &Reader::FIELD)
#define DEF_GETTER(FIELD) def("get" #FIELD, &Reader::get##FIELD)
#define DEF_HAZZER(FIELD) def("has" #FIELD, &Reader::has##FIELD)
#define DEF_IZZER(FIELD) def("is" #FIELD, &Reader::is##FIELD)
#define DEF_POINTER(FIELD) DEF_HAZZER(FIELD).DEF_GETTER(FIELD)
#define DEF_UNION(FIELD) DEF_IZZER(FIELD).DEF_GETTER(FIELD)
#define DEF_POINTER_UNION(FIELD) DEF_IZZER(FIELD).DEF_HAZZER(FIELD).DEF_GETTER(FIELD)

#define ENUM_(NAME) boost::python::enum_<Scope::NAME>(#NAME)
#define VALUE(FIELD) value(#FIELD, Scope::FIELD)

void defineNode(void) {
  std::string qualname("schema");

  CLASS_(capnp::schema, Node)
      .DEF_GETTER(Id)
      .DEF_POINTER(DisplayName)
      .DEF_GETTER(DisplayNamePrefixLength)
      .DEF_GETTER(ScopeId)
      .DEF_POINTER(Parameters)
      .DEF_GETTER(IsGeneric)
      .DEF_POINTER(NestedNodes)
      .DEF_POINTER(Annotations)
      .DEF(which)
      .DEF_UNION(File)
      .DEF_UNION(Struct)
      .DEF_UNION(Enum)
      .DEF_UNION(Interface)
      .DEF_UNION(Const)
      .DEF_UNION(Annotation);
  ENUM_(Which)  //
      .VALUE(FILE)
      .VALUE(STRUCT)
      .VALUE(ENUM)
      .VALUE(INTERFACE)
      .VALUE(CONST)
      .VALUE(ANNOTATION);

  { CLASS_(Parameter).DEF_POINTER(Name); }

  { CLASS_(NestedNode).DEF_POINTER(Name).DEF_GETTER(Id); }

  {
    CLASS_(SourceInfo).DEF_GETTER(Id).DEF_POINTER(DocComment).DEF_POINTER(Members);
    { CLASS_(Member).DEF_POINTER(DocComment); }
  }

  {
    CLASS_(Struct)
        .DEF_GETTER(DataWordCount)
        .DEF_GETTER(PointerCount)
        .DEF_GETTER(PreferredListEncoding)
        .DEF_GETTER(IsGroup)
        .DEF_GETTER(DiscriminantCount)
        .DEF_GETTER(DiscriminantOffset)
        .DEF_POINTER(Fields);
  }

  { CLASS_(Enum).DEF_POINTER(Enumerants); }

  { CLASS_(Interface).DEF_POINTER(Methods).DEF_POINTER(Superclasses); }

  { CLASS_(Const).DEF_POINTER(Type).DEF_POINTER(Value); }

  {
    // This is the annotation group defined in the Node struct, not the
    // top-level Annotation struct; don't get confused.
    CLASS_(Annotation)
        .DEF_POINTER(Type)
        .DEF_GETTER(TargetsFile)
        .DEF_GETTER(TargetsConst)
        .DEF_GETTER(TargetsEnum)
        .DEF_GETTER(TargetsEnumerant)
        .DEF_GETTER(TargetsStruct)
        .DEF_GETTER(TargetsField)
        .DEF_GETTER(TargetsUnion)
        .DEF_GETTER(TargetsGroup)
        .DEF_GETTER(TargetsInterface)
        .DEF_GETTER(TargetsMethod)
        .DEF_GETTER(TargetsParam)
        .DEF_GETTER(TargetsAnnotation);
  }

  defineListType<capnp::schema::Node>("_List_Node");
  defineListType<capnp::schema::Node::Annotation>("_List_Node_Annotation");
  defineListType<capnp::schema::Node::NestedNode>("_List_Node_NestedNode");
  defineListType<capnp::schema::Node::Parameter>("_List_Node_Parameter");
  defineListType<capnp::schema::Node::SourceInfo>("_List_Node_SourceInfo");
  defineListType<capnp::schema::Node::SourceInfo::Member>("_List_Node_SourceInfo_Member");
}

void defineField(void) {
  std::string qualname("schema");

  CLASS_(capnp::schema, Field)
      .DEF_POINTER(Name)
      .DEF_GETTER(CodeOrder)
      .DEF_POINTER(Annotations)
      .def_readonly("NO_DISCRIMINANT", &capnp::schema::Field::NO_DISCRIMINANT)
      .DEF_GETTER(DiscriminantValue)
      .DEF(which)
      .DEF_UNION(Slot)
      .DEF_UNION(Group)
      .DEF_GETTER(Ordinal);
  ENUM_(Which).VALUE(SLOT).VALUE(GROUP);

  {
    CLASS_(Slot)
        .DEF_GETTER(Offset)
        .DEF_POINTER(Type)
        .DEF_POINTER(DefaultValue)
        .DEF_GETTER(HadExplicitDefault);
  }

  { CLASS_(Group).DEF_GETTER(TypeId); }

  {
    CLASS_(Ordinal).DEF(which).DEF_UNION(Implicit).DEF_UNION(Explicit);
    ENUM_(Which).VALUE(IMPLICIT).VALUE(EXPLICIT);
  }

  defineListType<capnp::schema::Field>("_List_Field");
}

void defineEnumerant(void) {
  std::string qualname("schema");
  CLASS_(capnp::schema, Enumerant).DEF_POINTER(Name).DEF_GETTER(CodeOrder).DEF_POINTER(Annotations);
  defineListType<capnp::schema::Enumerant>("_List_Enumerant");
}

void defineSuperclass(void) {
  std::string qualname("schema");
  CLASS_(capnp::schema, Superclass).DEF_GETTER(Id).DEF_POINTER(Brand);
  defineListType<capnp::schema::Superclass>("_List_Superclass");
}

void defineMethod(void) {
  std::string qualname("schema");

  CLASS_(capnp::schema, Method)
      .DEF_POINTER(Name)
      .DEF_GETTER(CodeOrder)
      .DEF_POINTER(ImplicitParameters)
      .DEF_GETTER(ParamStructType)
      .DEF_POINTER(ParamBrand)
      .DEF_GETTER(ResultStructType)
      .DEF_POINTER(ResultBrand)
      .DEF_POINTER(Annotations);

  defineListType<capnp::schema::Method>("_List_Method");
}

void defineType(void) {
  std::string qualname("schema");

  CLASS_(capnp::schema, Type)
      .DEF(which)
      .DEF_UNION(Void)
      .DEF_UNION(Bool)
      .DEF_UNION(Int8)
      .DEF_UNION(Int16)
      .DEF_UNION(Int32)
      .DEF_UNION(Int64)
      .DEF_UNION(Uint8)
      .DEF_UNION(Uint16)
      .DEF_UNION(Uint32)
      .DEF_UNION(Uint64)
      .DEF_UNION(Float32)
      .DEF_UNION(Float64)
      .DEF_UNION(Text)
      .DEF_UNION(Data)
      .DEF_UNION(List)
      .DEF_UNION(Enum)
      .DEF_UNION(Struct)
      .DEF_UNION(Interface)
      .DEF_UNION(AnyPointer);
  ENUM_(Which)
      .VALUE(VOID)
      .VALUE(BOOL)
      .VALUE(INT8)
      .VALUE(INT16)
      .VALUE(INT32)
      .VALUE(INT64)
      .VALUE(UINT8)
      .VALUE(UINT16)
      .VALUE(UINT32)
      .VALUE(UINT64)
      .VALUE(FLOAT32)
      .VALUE(FLOAT64)
      .VALUE(TEXT)
      .VALUE(DATA)
      .VALUE(LIST)
      .VALUE(ENUM)
      .VALUE(STRUCT)
      .VALUE(INTERFACE)
      .VALUE(ANY_POINTER);

  { CLASS_(List).DEF_POINTER(ElementType); }

  { CLASS_(Enum).DEF_GETTER(TypeId).DEF_POINTER(Brand); }

  { CLASS_(Struct).DEF_GETTER(TypeId).DEF_POINTER(Brand); }

  { CLASS_(Interface).DEF_GETTER(TypeId).DEF_POINTER(Brand); }

  {
    CLASS_(AnyPointer)
        .DEF(which)
        .DEF_UNION(Unconstrained)
        .DEF_UNION(Parameter)
        .DEF_UNION(ImplicitMethodParameter);
    ENUM_(Which).VALUE(UNCONSTRAINED).VALUE(PARAMETER).VALUE(IMPLICIT_METHOD_PARAMETER);

    {
      CLASS_(Unconstrained)
          .DEF(which)
          .DEF_UNION(AnyKind)
          .DEF_UNION(Struct)
          .DEF_UNION(List)
          .DEF_UNION(Capability);
      ENUM_(Which).VALUE(ANY_KIND).VALUE(STRUCT).VALUE(LIST).VALUE(CAPABILITY);
    }

    { CLASS_(Parameter).DEF_GETTER(ScopeId).DEF_GETTER(ParameterIndex); }

    { CLASS_(ImplicitMethodParameter).DEF_GETTER(ParameterIndex); }
  }
}

void defineBrand(void) {
  std::string qualname("schema");

  CLASS_(capnp::schema, Brand).DEF_POINTER(Scopes);

  {
    CLASS_(Scope).DEF_GETTER(ScopeId).DEF(which).DEF_POINTER_UNION(Bind).DEF_UNION(Inherit);
    ENUM_(Which).VALUE(BIND).VALUE(INHERIT);
  }

  {
    CLASS_(Binding).DEF(which).DEF_UNION(Unbound).DEF_POINTER_UNION(Type);
    ENUM_(Which).VALUE(UNBOUND).VALUE(TYPE);
  }

  defineListType<capnp::schema::Brand::Scope>("_List_Brand_Scope");
  defineListType<capnp::schema::Brand::Binding>("_List_Brand_Binding");
}

void defineValue(void) {
  std::string qualname("schema");

  CLASS_(capnp::schema, Value)
      .DEF(which)
      .DEF_UNION(Void)
      .DEF_UNION(Bool)
      .DEF_UNION(Int8)
      .DEF_UNION(Int16)
      .DEF_UNION(Int32)
      .DEF_UNION(Int64)
      .DEF_UNION(Uint8)
      .DEF_UNION(Uint16)
      .DEF_UNION(Uint32)
      .DEF_UNION(Uint64)
      .DEF_UNION(Float32)
      .DEF_UNION(Float64)
      .DEF_POINTER_UNION(Text)
      .DEF_POINTER_UNION(Data)
      .DEF_POINTER_UNION(List)
      .DEF_UNION(Enum)
      .DEF_POINTER_UNION(Struct)
      .DEF_UNION(Interface)
      .DEF_POINTER_UNION(AnyPointer);
  ENUM_(Which)
      .VALUE(VOID)
      .VALUE(BOOL)
      .VALUE(INT8)
      .VALUE(INT16)
      .VALUE(INT32)
      .VALUE(INT64)
      .VALUE(UINT8)
      .VALUE(UINT16)
      .VALUE(UINT32)
      .VALUE(UINT64)
      .VALUE(FLOAT32)
      .VALUE(FLOAT64)
      .VALUE(TEXT)
      .VALUE(DATA)
      .VALUE(LIST)
      .VALUE(ENUM)
      .VALUE(STRUCT)
      .VALUE(INTERFACE)
      .VALUE(ANY_POINTER);
}

void defineAnnotation(void) {
  std::string qualname("schema");
  CLASS_(capnp::schema, Annotation).DEF_GETTER(Id).DEF_POINTER(Brand).DEF_POINTER(Value);
  defineListType<capnp::schema::Annotation>("_List_Annotation");
}

void defineElementSize(void) {
  // enum_ does not support setattr; so no setting __qualname__ for it.
  using Scope = capnp::schema::ElementSize;
  boost::python::enum_<Scope>("ElementSize")
      .VALUE(EMPTY)
      .VALUE(BIT)
      .VALUE(BYTE)
      .VALUE(TWO_BYTES)
      .VALUE(FOUR_BYTES)
      .VALUE(EIGHT_BYTES)
      .VALUE(POINTER)
      .VALUE(INLINE_COMPOSITE);
}

void defineCapnpVersion(void) {
  std::string qualname("schema");
  CLASS_(capnp::schema, CapnpVersion).DEF_GETTER(Major).DEF_GETTER(Minor).DEF_GETTER(Micro);
}

void defineCodeGeneratorRequest() {
  std::string qualname("schema");
  CLASS_(capnp::schema, CodeGeneratorRequest)
      .DEF_POINTER(CapnpVersion)
      .DEF_POINTER(Nodes)
      .DEF_POINTER(SourceInfo)
      .DEF_POINTER(RequestedFiles);
  {
    CLASS_(RequestedFile).DEF_GETTER(Id).DEF_POINTER(Filename).DEF_POINTER(Imports);
    { CLASS_(Import).DEF_GETTER(Id).DEF_POINTER(Name); }
  }

  defineListType<capnp::schema::CodeGeneratorRequest::RequestedFile>(
      "_List_CodeGeneratorRequest_RequestedFile");
  defineListType<capnp::schema::CodeGeneratorRequest::RequestedFile::Import>(
      "_List_CodeGeneratorRequest_RequestedFile_Import");
}

#undef CLASS_
#undef _GET_3RD_ARG
#undef _CLASS_1_ARGS_
#undef _CLASS_2_ARGS_

#undef DEF
#undef DEF_GETTER
#undef DEF_HAZZER
#undef DEF_IZZER
#undef DEF_POINTER
#undef DEF_UNION
#undef DEF_POINTER_UNION

#undef ENUM_
#undef VALUE

void defineSchemaTypes(void) {
  struct schema {};
  boost::python::scope _ = boost::python::class_<schema>("schema", boost::python::no_init);
  defineNode();
  defineField();
  defineEnumerant();
  defineSuperclass();
  defineMethod();
  defineType();
  defineBrand();
  defineValue();
  defineAnnotation();
  defineElementSize();
  defineCapnpVersion();
  defineCodeGeneratorRequest();
}

}  // namespace
}  // namespace schema

namespace {

//
// Exposing (high-level) capnp objects to Python.
//

#define CLASS_(...) _GET_3RD_ARG(__VA_ARGS__, _CLASS_2_ARGS_, _CLASS_1_ARGS_)(__VA_ARGS__)
#define _GET_3RD_ARG(arg1, arg2, arg3, ...) arg3
// You need a tmp string to prevent std::bad_alloc error.
#define _CLASS_1_ARGS_(NAME)        \
  std::string tmp = qualname + "."; \
  std::string qualname = tmp;       \
  _CLASS_2_ARGS_(Scope, NAME)
#define _CLASS_2_ARGS_(SCOPE, NAME)                                                    \
  using Scope = SCOPE::NAME;                                                           \
  qualname += #NAME;                                                                   \
  boost::python::scope _ = boost::python::class_<Scope>(#NAME, boost::python::no_init) \
                               .setattr("__qualname__", qualname)

#define DERIVED_CLASS_(SCOPE, NAME, ...)                                                    \
  using Scope = SCOPE::NAME;                                                                \
  qualname += #NAME;                                                                        \
  boost::python::scope _ = boost::python::class_<Scope, boost::python::bases<__VA_ARGS__>>( \
      #NAME, boost::python::no_init)

#define DEF(NAME) def(#NAME, &Scope::NAME)
#define DEF_LEN() def("__len__", &Scope::size)
#define DEF_GETITEM(E) def("__getitem__", SpecialMethods<Scope, E>::getitem)

void defineSchema(void) {
  std::string qualname;
  CLASS_(capnp, Schema)
      .DEF(getProto)
      .DEF(asUncheckedMessage)
      .DEF(isBranded)
      .DEF(getGeneric)
      .DEF(getBrandArgumentsAtScope)
      .DEF(asStruct)
      .DEF(asEnum)
      .DEF(asInterface)
      .DEF(asConst)
      .def(boost::python::self == boost::python::self)
      .def(boost::python::self != boost::python::self)
      .DEF(hashCode)
      .DEF(getShortDisplayName);

  {
    CLASS_(BrandArgumentList)
        .DEF_LEN()
        .DEF_GETITEM(capnp::Type)
        .def("_get", &capnp::Schema::BrandArgumentList::operator[]);
  }
}

void defineStructSchema(void) {
  std::string qualname;
  DERIVED_CLASS_(capnp, StructSchema, capnp::Schema)
      .DEF(getFields)
      .DEF(getUnionFields)
      .DEF(getNonUnionFields)
      .DEF(findFieldByName)
      .DEF(getFieldByName)
      .DEF(getFieldByDiscriminant);

  {
    CLASS_(Field)
        .DEF(getProto)
        .DEF(getContainingStruct)
        .DEF(getIndex)
        .DEF(getType)
        .DEF(getDefaultValueSchemaOffset)
        .def(boost::python::self == boost::python::self)
        .def(boost::python::self != boost::python::self)
        .DEF(hashCode);
  }

  { CLASS_(FieldList).DEF_LEN().DEF_GETITEM(capnp::StructSchema::Field); }

  { CLASS_(FieldSubset).DEF_LEN().DEF_GETITEM(capnp::StructSchema::Field); }
}

void defineEnumSchema(void) {
  std::string qualname;
  DERIVED_CLASS_(capnp, EnumSchema, capnp::Schema)
      .DEF(getEnumerants)
      .DEF(findEnumerantByName)
      .DEF(getEnumerantByName);

  {
    CLASS_(Enumerant)
        .DEF(getProto)
        .DEF(getContainingEnum)
        .DEF(getOrdinal)
        .DEF(getIndex)
        .def(boost::python::self == boost::python::self)
        .def(boost::python::self != boost::python::self)
        .DEF(hashCode);
  }

  { CLASS_(EnumerantList).DEF_LEN().DEF_GETITEM(capnp::EnumSchema::Enumerant); }
}

void defineInterfaceSchema(void) {
  std::string qualname;
  // TODO: I do not know why, but when there are private overloaded
  // member functions (findMethodByName, extends, and findSuperclass),
  // compiler will not be able to find the correct one (public one).
  using InterfaceSchema = capnp::InterfaceSchema;
  using Method = capnp::InterfaceSchema::Method;
  typedef kj::Maybe<Method> (InterfaceSchema::*findMethodByName)(kj::StringPtr) const;
  typedef bool (InterfaceSchema::*extends)(InterfaceSchema) const;
  typedef kj::Maybe<InterfaceSchema> (InterfaceSchema::*findSuperclass)(uint64_t typeId) const;
  DERIVED_CLASS_(capnp, InterfaceSchema, capnp::Schema)
      .DEF(getMethods)
      .def("findMethodByName", static_cast<findMethodByName>(&InterfaceSchema::findMethodByName))
      .DEF(getMethodByName)
      .DEF(getSuperclasses)
      .def("extends", static_cast<extends>(&InterfaceSchema::extends))
      .def("findSuperclass", static_cast<findSuperclass>(&InterfaceSchema::findSuperclass));

  {
    CLASS_(Method)
        .DEF(getProto)
        .DEF(getContainingInterface)
        .DEF(getOrdinal)
        .DEF(getIndex)
        .DEF(getParamType)
        .DEF(getResultType)
        .def(boost::python::self == boost::python::self)
        .def(boost::python::self != boost::python::self)
        .DEF(hashCode);
  }

  { CLASS_(MethodList).DEF_LEN().DEF_GETITEM(capnp::InterfaceSchema::Method); }

  { CLASS_(SuperclassList).DEF_LEN().DEF_GETITEM(capnp::InterfaceSchema); }
}

void defineConstSchema(void) {
  std::string qualname;
  DERIVED_CLASS_(capnp, ConstSchema, capnp::Schema)
      .def("asDynamicValue", &capnp::ConstSchema::as<capnp::DynamicValue>)
      .DEF(getValueSchemaOffset)
      .DEF(getType);
}

void defineType(void) {
  std::string qualname;
  CLASS_(capnp, Type)
      .DEF(which)
      .DEF(asStruct)
      .DEF(asEnum)
      .DEF(asInterface)
      .DEF(asList)
      .DEF(getBrandParameter)
      .DEF(getImplicitParameter)
      .DEF(whichAnyPointerKind)
      .DEF(isVoid)
      .DEF(isBool)
      .DEF(isInt8)
      .DEF(isInt16)
      .DEF(isInt32)
      .DEF(isInt64)
      .DEF(isUInt8)
      .DEF(isUInt16)
      .DEF(isUInt32)
      .DEF(isUInt64)
      .DEF(isFloat32)
      .DEF(isFloat64)
      .DEF(isText)
      .DEF(isData)
      .DEF(isList)
      .DEF(isEnum)
      .DEF(isStruct)
      .DEF(isInterface)
      .DEF(isAnyPointer)
      .def(boost::python::self == boost::python::self)
      .def(boost::python::self != boost::python::self)
      .DEF(hashCode)
      .DEF(wrapInList);
}

void defineListSchema(void) {
  std::string qualname;
  // NOTE: Unlike other, ListSchema does not inherit from Schema.
  CLASS_(capnp, ListSchema)
      .DEF(getElementType)
      .DEF(whichElementType)
      .DEF(getStructElementType)
      .DEF(getEnumElementType)
      .DEF(getInterfaceElementType)
      .DEF(getListElementType)
      .def(boost::python::self == boost::python::self)
      .def(boost::python::self != boost::python::self);
}

#undef CLASS_
#undef _GET_3RD_ARG
#undef _CLASS_1_ARGS_
#undef _CLASS_2_ARGS_

#undef DERIVED_CLASS_

#undef DEF
#undef DEF_LEN
#undef DEF_GETITEM

}  // namespace

void defineSchemaTypes(void) {

  MaybeToPythonConverter<capnp::EnumSchema::Enumerant>();
  MaybeToPythonConverter<capnp::InterfaceSchema>();
  MaybeToPythonConverter<capnp::InterfaceSchema::Method>();
  MaybeToPythonConverter<capnp::StructSchema::Field>();

  boost::python::class_<capnp::MessageSize>("MessageSize", boost::python::no_init)
      .def_readonly("wordCount", &capnp::MessageSize::wordCount)
      .def_readonly("capCount", &capnp::MessageSize::capCount);

  schema::defineSchemaTypes();

  defineSchema();
  defineStructSchema();
  defineEnumSchema();
  defineInterfaceSchema();
  defineConstSchema();
  defineType();
  defineListSchema();
}

}  // namespace capnp_python
