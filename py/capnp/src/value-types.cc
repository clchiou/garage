// Definition of value types

#include <boost/python/bases.hpp>
#include <boost/python/class.hpp>
#include <boost/python/enum.hpp>
#include <boost/python/scope.hpp>
#include <boost/python/to_python_converter.hpp>

#include <kj/common.h>

#include <capnp/common.h>
#include <capnp/blob.h>
#include <capnp/dynamic.h>
#include <capnp/list.h>
#include <capnp/message.h>
#include <capnp/schema.h>

#include "common.h"

namespace capnp_python {

// Convert Python bytes to kj::ArrayPtr<const capnp::word>>
// Be careful: kj::ArrayPtr doesn't own the data
struct ArrayPtrFromPythonBytes {
  ArrayPtrFromPythonBytes() {
    boost::python::converter::registry::push_back(
        &convertible, &construct,
        boost::python::type_id<kj::ArrayPtr<const capnp::word>>());
  }

  static void* convertible(PyObject* object) {
    if (!PyBytes_Check(object)) {
      return nullptr;
    }
    return object;
  }

  static void construct(
      PyObject* object,
      boost::python::converter::rvalue_from_python_stage1_data* data) {
    void* buffer = PyBytes_AsString(object);
    if (!buffer) {
      boost::python::throw_error_already_set();
    }
    Py_ssize_t size = PyBytes_Size(object);

    void* storage = ((boost::python::converter::rvalue_from_python_storage<
                         kj::ArrayPtr<const capnp::word>>*)data)
                        ->storage.bytes;
    new (storage) kj::ArrayPtr<const capnp::word>(
        static_cast<const capnp::word*>(buffer), static_cast<size_t>(size));

    data->convertible = storage;
  }
};

// Convert capnp::Void to Python None
struct VoidToPythonNone {
  static PyObject* convert(const capnp::Void& void_) { return Py_None; }
};

// Convert kj and capnp string-like object to Python str
template <typename T>
struct StringLikeToPythonStr {
  static PyObject* convert(const T& str) {
    return PyUnicode_FromString(str.cStr());
  }
};

template <typename T>
using StringLikeToPythonStrConverter =
    boost::python::to_python_converter<T, StringLikeToPythonStr<T>>;

// Convert kj::StringTree to Python str
struct StringTreeToPythonStr {
  static PyObject* convert(const kj::StringTree& stree) {
    return PyUnicode_FromString(stree.flatten().cStr());
  }
};

// Convert kj::Maybe<T> to Python None or T
template <typename T>
struct MaybeToPython {
  static PyObject* convert(kj::Maybe<T> maybe) {
    KJ_IF_MAYBE(ptr, maybe) {
      return boost::python::incref(boost::python::object(*ptr).ptr());
    }
    else {
      return Py_None;
    }
  }
};

template <typename T>
using MaybeToPythonConverter =
    boost::python::to_python_converter<kj::Maybe<T>, MaybeToPython<T>>;

// Convert std::vector<T>-like object to Python tuple
template <typename T>
struct VectorLikeToPythonTuple {
  static PyObject* convert(const T& vector) {
    uint size = vector.size();
    PyObject* tuple = PyTuple_New(size);
    if (!tuple) {
      boost::python::throw_error_already_set();
    }
    for (uint i = 0; i < size; i++) {
      PyObject* element =
          boost::python::incref(boost::python::object(vector[i]).ptr());
      if (PyTuple_SetItem(tuple, i, element) != 0) {
        boost::python::decref(tuple);
        boost::python::throw_error_already_set();
      }
    }
    return tuple;
  }
};

template <typename T>
using VectorLikeToPythonTupleConverter =
    boost::python::to_python_converter<T, VectorLikeToPythonTuple<T>>;

// Generate __getitem__
template <typename T, typename E>
struct Getitem {
  static E getitemConst(const T& self, uint index) { return self[index]; }
  static E getitem(T& self, uint index) { return self[index]; }
};

//
// Because some value types have universal copy constructor like this:
//
//   template <typename T, typename = kj::EnableIf<kind<FromBuilder<T>>() ==
//   Kind::STRUCT>>
//   inline Builder(T&& value): Builder(toDynamic(value)) {}
//
// They cannot be copy constructed from a const reference to another
// instance of the same type.  And to make things worse, Boost.Python's
// value_holder and pointer_holder insist on calling the value type's
// copy constructor with reference to const.  We work around this with
// the Boost.Python's value_holder_back_reference.  (As a consequence,
// we lose all other constructors, but since we don't expose most if not
// all constructors to Python, this trade-off seems to be acceptable.)
//
template <typename T>
class _MakeCopyable : public T {
 public:
  _MakeCopyable(PyObject* self) : self_(self) {}
  _MakeCopyable(PyObject* self, const T& obj)
      : T(const_cast<T&>(obj)),  // Cast away constness
        self_(self) {}

 private:
  PyObject* self_;
};

template <typename T, typename Bases = boost::python::bases<>>
using MakeCopyable = boost::python::class_<T, Bases, _MakeCopyable<T>>;

//
// defineValueTypes
//

void defineDynamicEnum(void);
void defineDynamicList(void);
void defineDynamicStruct(void);
void defineDynamicValue(void);

void defineSchema(void);
void defineType(void);
void defineListSchema(void);

void defineValueTypes(void) {
  // kj/common.h, kj/string.h, and kj/string-tree.h

  ArrayPtrFromPythonBytes();

  StringLikeToPythonStrConverter<kj::StringPtr>();

  boost::python::to_python_converter<kj::StringTree, StringTreeToPythonStr>();

  // capnp/common.h

  boost::python::to_python_converter<capnp::Void, VoidToPythonNone>();

  ValueType<capnp::MessageSize>("MessageSize", boost::python::no_init)
      .def_readonly("wordCount", &capnp::MessageSize::wordCount)
      .def_readonly("capCount", &capnp::MessageSize::capCount);

  // capnp/blob.h

  StringLikeToPythonStrConverter<capnp::Text::Reader>();

  // capnp/dynamic.h

  defineDynamicEnum();
  defineDynamicList();
  defineDynamicStruct();
  defineDynamicValue();

  // capnp/list.h

  VectorLikeToPythonTupleConverter<capnp::List<capnp::schema::Node>::Reader>();
  VectorLikeToPythonTupleConverter<
      capnp::List<capnp::schema::Node::NestedNode>::Reader>();
  VectorLikeToPythonTupleConverter<
      capnp::List<capnp::schema::Node::Annotation>::Reader>();
  VectorLikeToPythonTupleConverter<capnp::List<
      capnp::schema::CodeGeneratorRequest::RequestedFile>::Reader>();

  // capnp/schema.h

  defineSchema();
  defineType();
  defineListSchema();
}

//
// capnp::DynamicEnum
//

void defineDynamicEnum(void) {
  using capnp::DynamicEnum;
  ValueType<DynamicEnum>("DynamicEnum", boost::python::no_init)
      .def("getSchema", &DynamicEnum::getSchema)
      .def("getEnumerant", &DynamicEnum::getEnumerant)
      .def("getRaw", &DynamicEnum::getRaw);

  // This is defined in defineEnumSchema
  // MaybeToPythonConverter<EnumSchema::Enumerant>();
}

//
// capnp::DynamicList
//

void defineDynamicList(void) {
  using capnp::DynamicList;
  boost::python::scope _ =
      boost::python::class_<DynamicList>("DynamicList", boost::python::no_init);

  using Reader = DynamicList::Reader;
  ValueType<Reader>("Reader", boost::python::no_init)
      .def("getSchema", &Reader::getSchema)
      .def("__len__", &Reader::size)
      .def("__getitem__",
           Getitem<Reader, capnp::DynamicValue::Reader>::getitemConst);

  using Builder = DynamicList::Builder;
  MakeCopyable<Builder>("Builder", boost::python::no_init)
      .def("getSchema", &Builder::getSchema)
      .def("__len__", &Builder::size)
      .def("__getitem__",
           Getitem<Builder, capnp::DynamicValue::Builder>::getitem)
      .def("__setitem__", &Builder::set)
      .def("init", &Builder::init)
      // TODO: Test whether Boost.Python can handle std::initializer_list
      .def("copyFrom", &Builder::copyFrom)
      .def("asReader", &Builder::asReader);
}

//
// capnp::DynamicStruct
//

void defineDynamicStruct(void) {
  using capnp::DynamicStruct;
  boost::python::scope _ = boost::python::class_<DynamicStruct>(
      "DynamicStruct", boost::python::no_init);

  using Reader = DynamicStruct::Reader;
  ValueType<Reader>("Reader", boost::python::no_init)
      .def("totalSize", &Reader::totalSize)
      .def("getSchema", &Reader::getSchema)
      .DEF_MF_CONST(get, capnp::DynamicValue::Reader, Reader,
                    capnp::StructSchema::Field)
      .DEF_MF_CONST(has, bool, Reader, capnp::StructSchema::Field)
      .def("which", &Reader::which);

  // This is defined in defineStructSchema
  // MaybeToPythonConverter<StructSchema::Field>();

  using Builder = DynamicStruct::Builder;
  MakeCopyable<Builder>("Builder", boost::python::no_init)
      .def("totalSize", &Builder::totalSize)
      .def("getSchema", &Builder::getSchema)
      .DEF_MF(get, capnp::DynamicValue::Builder, Builder,
              capnp::StructSchema::Field)
      .DEF_MF(has, bool, Builder, capnp::StructSchema::Field)
      .def("which", &Builder::which)
      .DEF_MF(set, void, Builder, capnp::StructSchema::Field,
              const capnp::DynamicValue::Reader&)
      .DEF_MF(init, capnp::DynamicValue::Builder, Builder,
              capnp::StructSchema::Field)
      .DEF_MF(init, capnp::DynamicValue::Builder, Builder,
              capnp::StructSchema::Field, uint)
      .DEF_MF(clear, void, Builder, capnp::StructSchema::Field)
      .def("asReader", &Builder::asReader);
}

//
// capnp::DynamicValue
//

void defineDynamicValue(void) {
  using capnp::DynamicValue;
  boost::python::scope _ = boost::python::class_<DynamicValue>(
      "DynamicValue", boost::python::no_init);

#define EV(FIELD) value(#FIELD, DynamicValue::FIELD)
  boost::python::enum_<DynamicValue::Type>("Type")
      .EV(UNKNOWN)
      .EV(VOID)
      .EV(BOOL)
      .EV(INT)
      .EV(UINT)
      .EV(FLOAT)
      .EV(TEXT)
      .EV(DATA)
      .EV(LIST)
      .EV(ENUM)
      .EV(STRUCT)
      .EV(CAPABILITY)
      .EV(ANY_POINTER);
#undef EV

  using Reader = DynamicValue::Reader;
  boost::python::class_<Reader, ThrowingDtorHandler<Reader>>(
      "Reader", boost::python::no_init)
      .def("asVoid", &Reader::as<capnp::Void>)
      .def("asBool", &Reader::as<bool>)
      .def("asInt", &Reader::as<int64_t>)
      .def("asUInt", &Reader::as<uint64_t>)
      .def("asFloat", &Reader::as<double>)
      .def("asText", &Reader::as<capnp::Text>)
      .def("asList", &Reader::as<capnp::DynamicList>)
      .def("asEnum", &Reader::as<capnp::DynamicEnum>)
      .def("asStruct", &Reader::as<capnp::DynamicStruct>)
      .def("getType", &Reader::getType);

  using Builder = DynamicValue::Builder;
  boost::python::class_<MakeCopyable<Builder>,
                        ThrowingDtorHandler<MakeCopyable<Builder>>>(
      "Builder", boost::python::no_init)
      .def("asVoid", &Builder::as<capnp::Void>)
      .def("asBool", &Builder::as<bool>)
      .def("asInt", &Builder::as<int64_t>)
      .def("asUInt", &Builder::as<uint64_t>)
      .def("asFloat", &Builder::as<double>)
      .def("asText", &Builder::as<capnp::Text>)
      .def("asList", &Builder::as<capnp::DynamicList>)
      .def("asEnum", &Builder::as<capnp::DynamicEnum>)
      .def("asStruct", &Builder::as<capnp::DynamicStruct>)
      .def("getType", &Builder::getType)
      .def("asReader", &Builder::asReader);
}

//
// capnp::Schema
//

void defineStructSchema(void);
void defineEnumSchema(void);
void defineInterfaceSchema(void);
void defineConstSchema(void);

void defineSchema(void) {
  using capnp::Schema;
  ValueType<Schema>("Schema", boost::python::no_init)
      .def("getProto", &Schema::getProto)
      .def("isBranded", &Schema::isBranded)
      .def("getGeneric", &Schema::getGeneric)
      .def("asStruct", &Schema::asStruct)
      .def("asEnum", &Schema::asEnum)
      .def("asInterface", &Schema::asInterface)
      .def("asConst", &Schema::asConst)
      .def("getShortDisplayName", &Schema::getShortDisplayName);

  defineStructSchema();
  defineEnumSchema();
  defineInterfaceSchema();
  defineConstSchema();
}

//
// capnp::StructSchema
//

void defineStructSchemaField(void);

void defineStructSchema(void) {
  using capnp::Schema;
  using capnp::StructSchema;
  boost::python::scope _ =
      ValueType<StructSchema, boost::python::bases<Schema>>(
          "StructSchema", boost::python::no_init)
          .def("getFields", &StructSchema::getFields)
          .def("getUnionFields", &StructSchema::getUnionFields)
          .def("getNonUnionFields", &StructSchema::getNonUnionFields)
          .def("findFieldByName", &StructSchema::findFieldByName);

  MaybeToPythonConverter<StructSchema::Field>();

  defineStructSchemaField();
  VectorLikeToPythonTupleConverter<StructSchema::FieldList>();
  VectorLikeToPythonTupleConverter<StructSchema::FieldSubset>();
}

void defineStructSchemaField(void) {
  using Field = capnp::StructSchema::Field;
  ValueType<Field>("Field", boost::python::no_init)
      .def("getProto", &Field::getProto)
      .def("getContainingStruct", &Field::getContainingStruct)
      .def("getIndex", &Field::getIndex)
      .def("getType", &Field::getType)
      .def("getDefaultValueSchemaOffset", &Field::getDefaultValueSchemaOffset);
}

//
// capnp::EnumSchema
//

void defineEnumSchemaEnumerant(void);

void defineEnumSchema(void) {
  using capnp::Schema;
  using capnp::EnumSchema;
  boost::python::scope _ =
      ValueType<EnumSchema, boost::python::bases<Schema>>(
          "EnumSchema", boost::python::no_init)
          .def("getEnumerants", &EnumSchema::getEnumerants)
          .def("findEnumerantByName", &EnumSchema::findEnumerantByName);

  MaybeToPythonConverter<EnumSchema::Enumerant>();

  defineEnumSchemaEnumerant();
  VectorLikeToPythonTupleConverter<EnumSchema::EnumerantList>();
}

void defineEnumSchemaEnumerant(void) {
  using Enumerant = capnp::EnumSchema::Enumerant;
  ValueType<Enumerant>("Enumerant", boost::python::no_init)
      .def("getProto", &Enumerant::getProto)
      .def("getContainingEnum", &Enumerant::getContainingEnum)
      .def("getOrdinal", &Enumerant::getOrdinal)
      .def("getIndex", &Enumerant::getIndex);
}

//
// capnp::InterfaceSchema
//

void defineInterfaceSchemaMethod(void);

void defineInterfaceSchema(void) {
  using capnp::Schema;
  using capnp::InterfaceSchema;
  // TODO: Figure out why compiler cannot deduce these function
  // signatures (and thus I am forced to explicitly specify them with
  // DEF_MF_CONST)
  boost::python::scope _ =
      ValueType<InterfaceSchema, boost::python::bases<Schema>>(
          "InterfaceSchema", boost::python::no_init)
          .def("getMethods", &InterfaceSchema::getMethods)
          .DEF_MF_CONST(findMethodByName, kj::Maybe<InterfaceSchema::Method>,
                        InterfaceSchema, kj::StringPtr)
          .def("getSuperclasses", &InterfaceSchema::getSuperclasses)
          .DEF_MF_CONST(extends, bool, InterfaceSchema, InterfaceSchema)
          .DEF_MF_CONST(findSuperclass, kj::Maybe<InterfaceSchema>,
                        InterfaceSchema, uint64_t);

  MaybeToPythonConverter<InterfaceSchema>();
  MaybeToPythonConverter<InterfaceSchema::Method>();

  defineInterfaceSchemaMethod();
  VectorLikeToPythonTupleConverter<InterfaceSchema::MethodList>();
  VectorLikeToPythonTupleConverter<InterfaceSchema::SuperclassList>();
}

void defineInterfaceSchemaMethod(void) {
  using Method = capnp::InterfaceSchema::Method;
  ValueType<Method>("Method", boost::python::no_init)
      .def("getProto", &Method::getProto)
      .def("getContainingInterface", &Method::getContainingInterface)
      .def("getOrdinal", &Method::getOrdinal)
      .def("getIndex", &Method::getIndex)
      .def("getParamType", &Method::getParamType)
      .def("getResultType", &Method::getResultType);
}

//
// capnp::ConstSchema
//

void defineConstSchema(void) {
  using capnp::Schema;
  using capnp::ConstSchema;
  ValueType<ConstSchema, boost::python::bases<Schema>>("ConstSchema",
                                                       boost::python::no_init)
      .def("asDynamicValue", &ConstSchema::as<capnp::DynamicValue>)
      .def("getValueSchemaOffset", &ConstSchema::getValueSchemaOffset)
      .def("getType", &ConstSchema::getType);
}

//
// capnp::Type
//

void defineType(void) {
#define DEF(mf) def(#mf, &Type::mf)
  using capnp::Type;
  ValueType<Type>("Type", boost::python::no_init)
      .DEF(which)
      .DEF(asStruct)
      .DEF(asEnum)
      .DEF(asInterface)
      .DEF(asList)
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
      .DEF(hashCode)
      .DEF(wrapInList);
#undef DEF
}

//
// capnp::ListSchema
//

void defineListSchema(void) {
  // NOTE: capnp::ListSchema is **not** a sub-class of capnp::Schema
  using capnp::ListSchema;
  ValueType<ListSchema>("ListSchema", boost::python::no_init)
      .def("getElementType", &ListSchema::getElementType)
      .def("whichElementType", &ListSchema::whichElementType)
      .def("getStructElementType", &ListSchema::getStructElementType)
      .def("getEnumElementType", &ListSchema::getEnumElementType)
      .def("getInterfaceElementType", &ListSchema::getInterfaceElementType)
      .def("getListElementType", &ListSchema::getListElementType);
}

}  // namespace capnp_python
