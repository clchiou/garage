#include <boost/python/def.hpp>

#include <capnp/schema.h>

namespace capnp_python {
namespace test {

namespace {

template <typename T>
static T make(void) {
  return T();
}

}  // namespace

void defineSchemaTypesForTesting(void) {
#define DEF(STR, NAME) boost::python::def("makeSchema" STR, make<capnp::schema::NAME::Reader>)
  DEF("Node", Node);
  DEF("NodeParameter", Node::Parameter);
  DEF("NodeNestedNode", Node::NestedNode);
  DEF("NodeStruct", Node::Struct);
  DEF("NodeEnum", Node::Enum);
  DEF("NodeInterface", Node::Interface);
  DEF("NodeConst", Node::Const);
  DEF("NodeAnnotation", Node::Annotation);
  DEF("NodeSourceInfo", Node::SourceInfo);
  DEF("NodeSourceInfoMember", Node::SourceInfo::Member);
  DEF("Field", Field);
  DEF("FieldSlot", Field::Slot);
  DEF("FieldOrdinal", Field::Ordinal);
  DEF("Enumerant", Enumerant);
  DEF("Superclass", Superclass);
  DEF("Method", Method);
  DEF("Type", Type);
  DEF("TypeList", Type::List);
  DEF("TypeEnum", Type::Enum);
  DEF("TypeStruct", Type::Struct);
  DEF("TypeInterface", Type::Interface);
  DEF("TypeAnyPointer", Type::AnyPointer);
  DEF("TypeAnyPointerUnconstrained", Type::AnyPointer::Unconstrained);
  DEF("TypeAnyPointerParameter", Type::AnyPointer::Parameter);
  DEF("TypeAnyPointerImplicitMethodParameter", Type::AnyPointer::ImplicitMethodParameter);
  DEF("Brand", Brand);
  DEF("BrandScope", Brand::Scope);
  DEF("BrandBinding", Brand::Binding);
  DEF("Value", Value);
  DEF("Annotation", Annotation);
  DEF("CapnpVersion", CapnpVersion);
  DEF("CodeGeneratorRequest", CodeGeneratorRequest);
  DEF("CodeGeneratorRequestRequestedFile", CodeGeneratorRequest::RequestedFile);
  DEF("CodeGeneratorRequestRequestedFileImport", CodeGeneratorRequest::RequestedFile::Import);
#undef DEF

#define DEF(STR, NAME) boost::python::def("make" STR, make<capnp::NAME>)
  DEF("Schema", Schema);
  DEF("SchemaBrandArgumentList", Schema::BrandArgumentList);
  DEF("StructSchema", StructSchema);
  DEF("StructSchemaField", StructSchema::Field);
  DEF("StructSchemaFieldList", StructSchema::FieldList);
  DEF("StructSchemaFieldSubset", StructSchema::FieldSubset);
  DEF("EnumSchema", EnumSchema);
  DEF("EnumSchemaEnumerant", EnumSchema::Enumerant);
  DEF("EnumSchemaEnumerantList", EnumSchema::EnumerantList);
  DEF("InterfaceSchema", InterfaceSchema);
  DEF("InterfaceSchemaMethod", InterfaceSchema::Method);
  DEF("InterfaceSchemaMethodList", InterfaceSchema::MethodList);
  DEF("InterfaceSchemaSuperclassList", InterfaceSchema::SuperclassList);
  DEF("ConstSchema", ConstSchema);
  DEF("Type", Type);
  DEF("ListSchema", ListSchema);
#undef DEF
}

}  // namespace test
}  // namespace capnp_python
