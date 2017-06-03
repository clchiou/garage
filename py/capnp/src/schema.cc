// Definition for schema.capnp objects

#include "hack.h"

#include <boost/python/class.hpp>
#include <boost/python/enum.hpp>
#include <boost/python/scope.hpp>

#include <capnp/schema.h>

#include "common.h"

// We do not expose Builder and Pipeline classes for schema.capnp (and
// so we do not create namespace class)

#define STRUCT(SCOPE, NAME)                                                 \
  using StructType = SCOPE::NAME;                                           \
  using Reader = StructType::Reader;                                        \
  boost::python::scope _ = ValueType<Reader>(#NAME, boost::python::no_init) \
                               .def("totalSize", &Reader::totalSize)        \
                               .def("toString", &Reader::toString)

#define DEF_PRIMITIVE(FIELD) def("get" #FIELD, &Reader::get##FIELD)

#define DEF_HAZZER(FIELD) def("has" #FIELD, &Reader::has##FIELD)

#define DEF_POINTER(FIELD) DEF_HAZZER(FIELD).def("get" #FIELD, &Reader::get##FIELD)

#define DEF_UNION(FIELD) def("is" #FIELD, &Reader::is##FIELD).def("get" #FIELD, &Reader::get##FIELD)

#define ENUM_VALUE(FIELD) value(#FIELD, StructType::FIELD)

namespace capnp_python {
namespace {

//
// Node
//

void defineNodeParameter(void);
void defineNodeNestedNode(void);
void defineNodeStruct(void);
void defineNodeEnum(void);
void defineNodeInterface(void);
void defineNodeConst(void);
void defineNodeAnnotation(void);

void defineNode(void) {
  STRUCT(capnp::schema, Node)
      .DEF_PRIMITIVE(Id)
      .DEF_POINTER(DisplayName)
      .DEF_PRIMITIVE(DisplayNamePrefixLength)
      .DEF_PRIMITIVE(ScopeId)
      .DEF_POINTER(Parameters)
      .DEF_PRIMITIVE(IsGeneric)
      .DEF_POINTER(NestedNodes)
      .DEF_POINTER(Annotations)
      .def("which", &Reader::which)
      .DEF_UNION(File)
      .DEF_UNION(Struct)
      .DEF_UNION(Enum)
      .DEF_UNION(Interface)
      .DEF_UNION(Const)
      .DEF_UNION(Annotation);

  boost::python::enum_<StructType::Which>("Which")
      .ENUM_VALUE(FILE)
      .ENUM_VALUE(STRUCT)
      .ENUM_VALUE(ENUM)
      .ENUM_VALUE(INTERFACE)
      .ENUM_VALUE(CONST)
      .ENUM_VALUE(ANNOTATION);

  defineNodeParameter();
  defineNodeNestedNode();
  defineNodeStruct();
  defineNodeEnum();
  defineNodeInterface();
  defineNodeConst();
  defineNodeAnnotation();
}

void defineNodeParameter(void) {
  STRUCT(capnp::schema::Node, Parameter).DEF_POINTER(Name);
}

void defineNodeNestedNode(void) {
  STRUCT(capnp::schema::Node, NestedNode).DEF_POINTER(Name).DEF_PRIMITIVE(Id);
}

void defineNodeStruct(void) {
  STRUCT(capnp::schema::Node, Struct)
      .DEF_PRIMITIVE(DataWordCount)
      .DEF_PRIMITIVE(PointerCount)
      .DEF_PRIMITIVE(PreferredListEncoding)
      .DEF_PRIMITIVE(IsGroup)
      .DEF_PRIMITIVE(DiscriminantCount)
      .DEF_PRIMITIVE(DiscriminantOffset)
      .DEF_POINTER(Fields);
}

void defineNodeEnum(void) {
  STRUCT(capnp::schema::Node, Enum).DEF_POINTER(Enumerants);
}

void defineNodeInterface(void) {
  STRUCT(capnp::schema::Node, Interface).DEF_POINTER(Methods).DEF_POINTER(Superclasses);
}

void defineNodeConst(void) {
  STRUCT(capnp::schema::Node, Const).DEF_POINTER(Type).DEF_POINTER(Value);
}

void defineNodeAnnotation(void) {
  STRUCT(capnp::schema::Node, Annotation)
      .DEF_POINTER(Type)
      .DEF_PRIMITIVE(TargetsFile)
      .DEF_PRIMITIVE(TargetsConst)
      .DEF_PRIMITIVE(TargetsEnum)
      .DEF_PRIMITIVE(TargetsEnumerant)
      .DEF_PRIMITIVE(TargetsStruct)
      .DEF_PRIMITIVE(TargetsField)
      .DEF_PRIMITIVE(TargetsUnion)
      .DEF_PRIMITIVE(TargetsGroup)
      .DEF_PRIMITIVE(TargetsInterface)
      .DEF_PRIMITIVE(TargetsMethod)
      .DEF_PRIMITIVE(TargetsParam)
      .DEF_PRIMITIVE(TargetsAnnotation);
}

//
// Field
//

void defineFieldSlot(void);
void defineFieldGroup(void);
void defineFieldOrdinal(void);

void defineField(void) {
  STRUCT(capnp::schema, Field)
      .DEF_POINTER(Name)
      .DEF_PRIMITIVE(CodeOrder)
      .DEF_POINTER(Annotations)
      .DEF_PRIMITIVE(DiscriminantValue)
      .def("which", &Reader::which)
      .DEF_UNION(Slot)
      .DEF_UNION(Group)
      .DEF_PRIMITIVE(Ordinal);

  boost::python::enum_<StructType::Which>("Which").ENUM_VALUE(SLOT).ENUM_VALUE(GROUP);

  defineFieldSlot();
  defineFieldGroup();
  defineFieldOrdinal();
}

void defineFieldSlot(void) {
  STRUCT(capnp::schema::Field, Slot)
      .DEF_PRIMITIVE(Offset)
      .DEF_POINTER(Type)
      .DEF_POINTER(DefaultValue)
      .DEF_PRIMITIVE(HadExplicitDefault);
}

void defineFieldGroup(void) {
  STRUCT(capnp::schema::Field, Group).DEF_PRIMITIVE(TypeId);
}

void defineFieldOrdinal(void) {
  STRUCT(capnp::schema::Field, Ordinal)
      .def("which", &Reader::which)
      .DEF_UNION(Implicit)
      .DEF_UNION(Explicit);

  boost::python::enum_<StructType::Which>("Which").ENUM_VALUE(IMPLICIT).ENUM_VALUE(EXPLICIT);
}

//
// Enumerant
//

void defineEnumerant(void) {
  STRUCT(capnp::schema, Enumerant)
      .DEF_POINTER(Name)
      .DEF_PRIMITIVE(CodeOrder)
      .DEF_POINTER(Annotations);
}

//
// Superclass
//

void defineSuperclass(void) {
  STRUCT(capnp::schema, Superclass).DEF_PRIMITIVE(Id).DEF_POINTER(Brand);
}

//
// Method
//

void defineMethod(void) {
  STRUCT(capnp::schema, Method)
      .DEF_POINTER(Name)
      .DEF_PRIMITIVE(CodeOrder)
      .DEF_POINTER(ImplicitParameters)
      .DEF_PRIMITIVE(ParamStructType)
      .DEF_POINTER(ParamBrand)
      .DEF_PRIMITIVE(ResultStructType)
      .DEF_POINTER(ResultBrand)
      .DEF_POINTER(Annotations);
}

//
// Type
//

void defineTypeList(void);
void defineTypeEnum(void);
void defineTypeStruct(void);
void defineTypeInterface(void);
void defineTypeAnyPointer(void);

void defineType(void) {
  STRUCT(capnp::schema, Type)
      .def("which", &Reader::which)
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

  boost::python::enum_<StructType::Which>("Which")
      .ENUM_VALUE(VOID)
      .ENUM_VALUE(BOOL)
      .ENUM_VALUE(INT8)
      .ENUM_VALUE(INT16)
      .ENUM_VALUE(INT32)
      .ENUM_VALUE(INT64)
      .ENUM_VALUE(UINT8)
      .ENUM_VALUE(UINT16)
      .ENUM_VALUE(UINT32)
      .ENUM_VALUE(UINT64)
      .ENUM_VALUE(FLOAT32)
      .ENUM_VALUE(FLOAT64)
      .ENUM_VALUE(TEXT)
      .ENUM_VALUE(DATA)
      .ENUM_VALUE(LIST)
      .ENUM_VALUE(ENUM)
      .ENUM_VALUE(STRUCT)
      .ENUM_VALUE(INTERFACE)
      .ENUM_VALUE(ANY_POINTER);

  defineTypeList();
  defineTypeEnum();
  defineTypeStruct();
  defineTypeInterface();
  defineTypeAnyPointer();
}

void defineTypeList(void) {
  STRUCT(capnp::schema::Type, List).DEF_POINTER(ElementType);
}

void defineTypeEnum(void) {
  STRUCT(capnp::schema::Type, Enum).DEF_PRIMITIVE(TypeId).DEF_POINTER(Brand);
}

void defineTypeStruct(void) {
  STRUCT(capnp::schema::Type, Struct).DEF_PRIMITIVE(TypeId).DEF_POINTER(Brand);
}

void defineTypeInterface(void) {
  STRUCT(capnp::schema::Type, Interface).DEF_PRIMITIVE(TypeId).DEF_POINTER(Brand);
}

void defineTypeAnyPointer(void) {
  STRUCT(capnp::schema::Type, AnyPointer)
  // TODO: Expose capnp::schema::Type::AnyPointer
  ;
}

//
// Brand
//

void defineBrand(void) {
  STRUCT(capnp::schema, Brand)
  // TODO: Expose capnp::schema::Brand
  ;
}

//
// Value
//

void defineValue(void) {
  STRUCT(capnp::schema, Value)
      .def("which", &Reader::which)
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
      .DEF_HAZZER(Text)
      .DEF_UNION(Data)
      .DEF_HAZZER(Data)
      .DEF_UNION(List)
      .DEF_HAZZER(List)
      .DEF_UNION(Enum)
      .DEF_UNION(Struct)
      .DEF_HAZZER(Struct)
      .DEF_UNION(Interface)
      .DEF_UNION(AnyPointer)
      .DEF_HAZZER(AnyPointer);

  boost::python::enum_<StructType::Which>("Which")
      .ENUM_VALUE(VOID)
      .ENUM_VALUE(BOOL)
      .ENUM_VALUE(INT8)
      .ENUM_VALUE(INT16)
      .ENUM_VALUE(INT32)
      .ENUM_VALUE(INT64)
      .ENUM_VALUE(UINT8)
      .ENUM_VALUE(UINT16)
      .ENUM_VALUE(UINT32)
      .ENUM_VALUE(UINT64)
      .ENUM_VALUE(FLOAT32)
      .ENUM_VALUE(FLOAT64)
      .ENUM_VALUE(TEXT)
      .ENUM_VALUE(DATA)
      .ENUM_VALUE(LIST)
      .ENUM_VALUE(ENUM)
      .ENUM_VALUE(STRUCT)
      .ENUM_VALUE(INTERFACE)
      .ENUM_VALUE(ANY_POINTER);
}

//
// Annotation
//

void defineAnnotation(void) {
  STRUCT(capnp::schema, Annotation).DEF_PRIMITIVE(Id).DEF_POINTER(Brand).DEF_POINTER(Value);
}

//
// CodeGeneratorRequest
//

void defineCodeGeneratorRequestRequestedFile(void);
void defineCodeGeneratorRequestRequestedFileImport(void);

void defineCodeGeneratorRequest(void) {
  STRUCT(capnp::schema, CodeGeneratorRequest).DEF_POINTER(Nodes).DEF_POINTER(RequestedFiles);

  defineCodeGeneratorRequestRequestedFile();
}

void defineCodeGeneratorRequestRequestedFile(void) {
  STRUCT(capnp::schema::CodeGeneratorRequest, RequestedFile)
      .DEF_PRIMITIVE(Id)
      .DEF_POINTER(Filename)
      .DEF_POINTER(Imports);

  defineCodeGeneratorRequestRequestedFileImport();
}

void defineCodeGeneratorRequestRequestedFileImport(void) {
  STRUCT(capnp::schema::CodeGeneratorRequest::RequestedFile, Import)
      .DEF_PRIMITIVE(Id)
      .DEF_POINTER(Name);
}

}  // namespace

void defineSchemaCapnp(void) {
  struct schema {};  // Dummy struct for namespace
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
  defineCodeGeneratorRequest();
}

}  // namespace capnp_python
