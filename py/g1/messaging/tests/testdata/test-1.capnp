@0xff831e8e8b53f919;

using Cxx = import "/capnp/c++.capnp";
$Cxx.namespace("g1::messaging::tests::test_1");

struct SomeError {
  code @0 :Int32;
  reason @1 :Text;
}

struct SomeStruct {

  struct NestedEmptyStruct {}

  enum NestedEnum {
    enumMember0 @0;
    enumMember1 @1;
  }

  voidField @0 :Void;
  intField @1 :Int32;
  intWithDefault @2 :Int64 = 42;
  strField @3 :Text;
  intTimestamp @4 :Int64;
  floatTimestamp @5 :Float64;
  enumField @6 :NestedEnum;
  structField @7 :NestedEmptyStruct;
  errorField @8 :SomeError;
  union {
    unionIntField @9 :Int32;
    unionErrorField @10 :SomeError;
  }
  unionField :union {
    boolField @11 :Bool;
    bytesField @12 :Data;
  }
  intListField @13 :List(Int32);
  tupleField :group {
    intGroupField @14 :Int32;
    boolGroupField @15 :Bool;
  }
  noneField @16 :Void;
  unionVoidField :union {
    unionVoidField @17 :Void;
    unionBytesField @18 :Data;
  }
  strWithDefault @19 :Text = "default message";
}
