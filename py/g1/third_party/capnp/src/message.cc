#include <utility>

// You must include this before including boost headers.
#include "resource-types-fwd.h"

#include <boost/python/class.hpp>
#include <boost/python/def.hpp>

#include <kj/io.h>

#include <capnp/any.h>
#include <capnp/dynamic.h>
#include <capnp/message.h>
#include <capnp/schema.h>
#include <capnp/serialize-packed.h>
#include <capnp/serialize.h>

#include "resource-types.h"

//
// Notes to implementer:
//
// * For now, we focus on exposing memory-backed message reader/builder,
//   and do not expose I/O stream backed ones.
//
// * I feel that capnp's packed interface is somehow inconsistent with
//   non-packed's; so I define my own interface.
//
// * Do not expose segment-based interface, which requires exposing
//   kj::ArrayPtr<const kj::ArrayPtr<const word>> first.
//
// * Do not expose virtual member function for now (because Boost.Python
//   requires a wrapper class when exposing virtual member function).
//
// * Do not expose adopt/orphan interface for now.
//

namespace capnp_python {

namespace {

// Return a copy rather than a const reference to reader's state.
capnp::ReaderOptions messageReaderGetOptions(capnp::MessageReader& reader) {
  return reader.getOptions();
}

ResourceSharedPtr<capnp::PackedMessageReader> makePackedMessageReader(
    kj::ArrayPtr<const kj::byte> array  //
) {
  kj::ArrayInputStream inputStream(array);
  return ResourceSharedPtr<capnp::PackedMessageReader>(new capnp::PackedMessageReader(inputStream));
}

// We need this wrapper because Boost doesn't seem to support rvalue
// reference.
void messageBuilderSetRoot(capnp::MessageBuilder& builder, capnp::DynamicStruct::Reader& value) {
  builder.setRoot(value);
}

kj::ArrayPtr<const capnp::word> initMessageBuilderFromFlatArrayCopy_2(
    kj::ArrayPtr<const capnp::word> array,
    capnp::MessageBuilder& target  //
) {
  return capnp::initMessageBuilderFromFlatArrayCopy(array, target);
}

void initMessageBuilderFromPackedArrayCopy(
    kj::ArrayPtr<const capnp::word> array,
    capnp::MessageBuilder& target,
    capnp::ReaderOptions options  //
) {
  kj::ArrayInputStream inputStream(array.asBytes());
  capnp::PackedMessageReader reader(inputStream, options);
  target.setRoot(reader.getRoot<capnp::AnyPointer>());
}

void initMessageBuilderFromPackedArrayCopy_2(
    kj::ArrayPtr<const capnp::word> array,
    capnp::MessageBuilder& target  //
) {
  return initMessageBuilderFromPackedArrayCopy(array, target, capnp::ReaderOptions());
}

ResourceSharedPtr<kj::Array<capnp::word>> messageToFlatArray(capnp::MessageBuilder& builder) {
  kj::Array<capnp::word> array = capnp::messageToFlatArray(builder);
  return ResourceSharedPtr<kj::Array<capnp::word>>(new kj::Array<capnp::word>(std::move(array)));
}

ResourceSharedPtr<kj::Array<kj::byte>> messageToPackedArray(capnp::MessageBuilder& builder) {
  kj::VectorOutputStream outputStream;
  capnp::writePackedMessage(outputStream, builder);
  kj::Array<kj::byte> array = kj::heapArray(outputStream.getArray());
  return ResourceSharedPtr<kj::Array<kj::byte>>(new kj::Array<kj::byte>(std::move(array)));
}

}  // namespace

void defineMessageTypes(void) {

  boost::python::class_<capnp::ReaderOptions>("ReaderOptions", boost::python::init<>())
      .def_readwrite("traversalLimitInWords", &capnp::ReaderOptions::traversalLimitInWords)
      .def_readwrite("nestingLimit", &capnp::ReaderOptions::nestingLimit);

#include "resource-types-def-macros.h"

  // Virtual base classes.

  {
    using Type = capnp::MessageReader;
    boost::python::class_<Type, boost::noncopyable>("MessageReader", boost::python::no_init)
        // TODO: Do not expose virtual member function for now.
        // .DEF(getSegment)
        .def("getOptions", &messageReaderGetOptions)
        .def("getRoot", &Type::getRoot<capnp::schema::CodeGeneratorRequest>)
        .def("getRoot", &Type::getRoot<capnp::DynamicStruct, capnp::StructSchema>)
        .DEF(isCanonical);
  }

  {
    using Type = capnp::MessageBuilder;
    boost::python::class_<Type, boost::noncopyable>("MessageBuilder", boost::python::no_init)
        // TODO: Do not expose virtual member function for now.
        // .DEF(allocateSegment)
        .def("setRoot", &messageBuilderSetRoot)
        .def("getRoot", &Type::getRoot<capnp::DynamicStruct, capnp::StructSchema>)
        .def("initRoot", &Type::initRoot<capnp::DynamicStruct, capnp::StructSchema>)
        // TODO: Expose kj::ArrayPtr<const kj::ArrayPtr<const word>>.
        // .DEF(getSegmentsForOutput)
        .DEF(isCanonical);
  }

  // Concrete classes.

  {
    DERIVED_RESOURCE_CLASS_(
        capnp::FlatArrayMessageReader,
        capnp::MessageReader,
        "FlatArrayMessageReader",
        boost::python::init<
            kj::ArrayPtr<const capnp::word>,
            boost::python::optional<capnp::ReaderOptions>>()  //
    );
  }

  {
    DERIVED_RESOURCE_CLASS_(
        capnp::PackedMessageReader,
        capnp::MessageReader,
        "PackedMessageReader",
        boost::python::no_init  // For now, expose no constructor.
    );
  }

  {
    DERIVED_RESOURCE_CLASS_(
        capnp::MallocMessageBuilder,
        capnp::MessageBuilder,
        "MallocMessageBuilder",
        boost::python::init<>()  // For now, use default arg values.
    );
  }

#include "resource-types-undef-macros.h"

  // Helper functions.

  boost::python::def("makePackedMessageReader", makePackedMessageReader);

  boost::python::def(
      "initMessageBuilderFromFlatArrayCopy", capnp::initMessageBuilderFromFlatArrayCopy);
  boost::python::def("initMessageBuilderFromFlatArrayCopy", initMessageBuilderFromFlatArrayCopy_2);

  boost::python::def("messageToFlatArray", messageToFlatArray);

  boost::python::def(
      "computeSerializedSizeInWords",
      static_cast<size_t (*)(capnp::MessageBuilder&)>(capnp::computeSerializedSizeInWords)  //
  );

  boost::python::def(
      "initMessageBuilderFromPackedArrayCopy", initMessageBuilderFromPackedArrayCopy);
  boost::python::def(
      "initMessageBuilderFromPackedArrayCopy", initMessageBuilderFromPackedArrayCopy_2);

  boost::python::def("messageToPackedArray", messageToPackedArray);

  boost::python::def("computeUnpackedSizeInWords", capnp::computeUnpackedSizeInWords);
}

}  // namespace capnp_python
