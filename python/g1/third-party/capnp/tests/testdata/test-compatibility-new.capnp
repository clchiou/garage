@0x8304375a0deaf839;

using Cxx = import "/capnp/c++.capnp";
$Cxx.namespace("unittest::test_compatibility");

struct TestStruct {
  enum TestEnum {
    oldMember @0;
    newMember @1;
  }
  enumField @0 :TestEnum;
  union {
    noOptionalEnumField @1 :Void;
    optionalEnumField @2 :TestEnum;
  }
  extraField @3 :Bool;
}
