// Definition of resource types

#include "hack.h"

#include <boost/python/bases.hpp>
#include <boost/python/class.hpp>
#include <boost/python/def.hpp>
#include <boost/python/init.hpp>
#include <boost/python/overloads.hpp>

#include <kj/io.h>

#include <capnp/dynamic.h>
#include <capnp/message.h>
#include <capnp/schema.h>
#include <capnp/schema-loader.h>
#include <capnp/serialize.h>
#include <capnp/serialize-packed.h>

#include "common.h"

namespace capnp_python {

BOOST_PYTHON_MEMBER_FUNCTION_OVERLOADS(SchemaLoader_get_overloads, get, 1, 1)
BOOST_PYTHON_MEMBER_FUNCTION_OVERLOADS(SchemaLoader_getType_overloads, getType, 1, 1)

BOOST_PYTHON_FUNCTION_OVERLOADS(initMessageBuilderFromFlatArrayCopy_overloads,
                                capnp::initMessageBuilderFromFlatArrayCopy,
                                2,
                                3)

void defineResourceTypes(void) {
  // kj/io.h

  AbstractType<kj::InputStream>("InputStream", boost::python::no_init);

  AbstractType<kj::OutputStream>("OutputStream", boost::python::no_init);

  AbstractType<kj::BufferedInputStream, boost::python::bases<kj::InputStream>>(
      "BufferedInputStream", boost::python::no_init);

  AbstractType<kj::BufferedOutputStream, boost::python::bases<kj::OutputStream>>(
      "BufferedOutputStream", boost::python::no_init);

  ResourceType<kj::BufferedInputStreamWrapper, boost::python::bases<kj::BufferedInputStream>>(
      "BufferedInputStreamWrapper", boost::python::init<kj::InputStream&>())
      .DEF_RESET(kj::BufferedInputStreamWrapper);

  ResourceType<kj::BufferedOutputStreamWrapper, boost::python::bases<kj::BufferedOutputStream>>(
      "BufferedOutputStreamWrapper", boost::python::init<kj::OutputStream&>())
      .DEF_RESET(kj::BufferedOutputStreamWrapper);

  ResourceType<kj::ArrayInputStream, boost::python::bases<kj::BufferedInputStream>>(
      "ArrayInputStream", boost::python::init<kj::ArrayPtr<const kj::byte>>())
      .DEF_RESET(kj::ArrayInputStream);

  ResourceType<kj::VectorOutputStream, boost::python::bases<kj::BufferedOutputStream>>(
      "VectorOutputStream", boost::python::init<boost::python::optional<size_t>>())
      .DEF_RESET(kj::VectorOutputStream)
      .def("getArray", &kj::VectorOutputStream::getArray);

  ResourceType<kj::FdInputStream, boost::python::bases<kj::InputStream>>("FdInputStream",
                                                                         boost::python::init<int>())
      .DEF_RESET(kj::FdInputStream);

  ResourceType<kj::FdOutputStream, boost::python::bases<kj::OutputStream>>(
      "FdOutputStream", boost::python::init<int>())
      .DEF_RESET(kj::FdOutputStream);

  // capnp/message.h

  ValueType<capnp::ReaderOptions>("ReaderOptions")
      .def_readwrite("traversalLimitInWords", &capnp::ReaderOptions::traversalLimitInWords)
      .def_readwrite("nestingLimit", &capnp::ReaderOptions::nestingLimit);

  boost::python::class_<capnp::MessageReader, boost::noncopyable>("MessageReader",
                                                                  boost::python::no_init)
      .def("getRoot", &capnp::MessageReader::getRoot<capnp::schema::CodeGeneratorRequest>)
      .def("getRoot", &capnp::MessageReader::getRoot<capnp::DynamicStruct, capnp::StructSchema>)
      .def("isCanonical", &capnp::MessageReader::isCanonical);

  boost::python::class_<capnp::MessageBuilder, boost::noncopyable>("MessageBuilder",
                                                                   boost::python::no_init)
      // TODO: Boost doesn't seem to support rvalue reference
      //.def("setRoot", &capnp::MessageBuilder::setRoot<capnp::DynamicStruct::Reader>)
      .def("getRoot", &capnp::MessageBuilder::getRoot<capnp::DynamicStruct, capnp::StructSchema>)
      .def("initRoot", &capnp::MessageBuilder::initRoot<capnp::DynamicStruct, capnp::StructSchema>)
      .def("isCanonical", &capnp::MessageBuilder::isCanonical);

  ResourceType<capnp::MallocMessageBuilder, boost::python::bases<capnp::MessageBuilder>>
      // Don't expose constructor arguments for now
      ("MallocMessageBuilder", boost::python::init<>()).DEF_RESET(capnp::MallocMessageBuilder);

  // capnp/schema-loader.h

  ResourceType<capnp::SchemaLoader>
      // Don't expose constructor arguments for now
      ("SchemaLoader", boost::python::init<>())
          .DEF_RESET(capnp::SchemaLoader)
          .def("get", &capnp::SchemaLoader::get, SchemaLoader_get_overloads())
          .def("getType", &capnp::SchemaLoader::getType, SchemaLoader_getType_overloads())
          .def("load", &capnp::SchemaLoader::load)
          .def("loadOnce", &capnp::SchemaLoader::loadOnce)
          .def("getAllLoaded", &capnp::SchemaLoader::getAllLoaded);

  // capnp/serialize.h

  ResourceType<capnp::FlatArrayMessageReader, boost::python::bases<capnp::MessageReader>>(
      "FlatArrayMessageReader",
      boost::python::init<kj::ArrayPtr<const capnp::word>,
                          boost::python::optional<capnp::ReaderOptions>>())
      .DEF_RESET(capnp::FlatArrayMessageReader)
      // TODO: Figure out a how to safely handle raw pointer
      //.def("getEnd", &capnp::FlatArrayMessageReader::getEnd)
      ;

  ResourceType<capnp::InputStreamMessageReader, boost::python::bases<capnp::MessageReader>>(
      "InputStreamMessageReader",
      boost::python::init<kj::InputStream&, boost::python::optional<capnp::ReaderOptions>>())
      .DEF_RESET(capnp::InputStreamMessageReader);

  ResourceType<capnp::StreamFdMessageReader, boost::python::bases<capnp::InputStreamMessageReader>>(
      "StreamFdMessageReader",
      boost::python::init<int, boost::python::optional<capnp::ReaderOptions>>())
      .DEF_RESET(capnp::StreamFdMessageReader);

  boost::python::def("initMessageBuilderFromFlatArrayCopy",
                     capnp::initMessageBuilderFromFlatArrayCopy,
                     initMessageBuilderFromFlatArrayCopy_overloads());

  DEF_FUNC(capnp, messageToFlatArray, kj::Array<capnp::word>, capnp::MessageBuilder&);

  DEF_FUNC(capnp, writeMessage, void, kj::OutputStream&, capnp::MessageBuilder&);
  DEF_FUNC(capnp, writeMessageToFd, void, int, capnp::MessageBuilder&);

  DEF_FUNC(capnp, computeSerializedSizeInWords, size_t, capnp::MessageBuilder&);

  // capnp/serialize-packed.h

  ResourceType<capnp::PackedMessageReader, boost::python::bases<capnp::InputStreamMessageReader>>(
      "PackedMessageReader", boost::python::init<kj::BufferedInputStream&,
                                                 boost::python::optional<capnp::ReaderOptions>>())
      .DEF_RESET(capnp::PackedMessageReader);

  ResourceType<capnp::PackedFdMessageReader, boost::python::bases<capnp::PackedMessageReader>>(
      "PackedFdMessageReader",
      boost::python::init<int, boost::python::optional<capnp::ReaderOptions>>())
      .DEF_RESET(capnp::PackedFdMessageReader);

  DEF_FUNC(capnp, writePackedMessage, void, kj::BufferedOutputStream&, capnp::MessageBuilder&);
  DEF_FUNC(capnp, writePackedMessageToFd, void, int, capnp::MessageBuilder&);

  boost::python::def("computeUnpackedSizeInWords", capnp::computeUnpackedSizeInWords);
}

}  // namespace capnp_python
