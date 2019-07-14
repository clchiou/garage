@0x858e39e6f988a695;

using Cxx = import "/capnp/c++.capnp";
$Cxx.namespace("unittest::test_2");

struct TestSimpleStruct {
  # Test code order vs ordinal number not in the same order.

  voidField @0 :Void;

  boolField @2 :Bool;

  int8Field @4 :Int8;
  int16Field @6 :Int16;
  int32Field @8 :Int32;
  int64Field @13 :Int64;

  uint8Field @10 :UInt8;
  uint16Field @14 :UInt16;
  uint32Field @15 :UInt32;
  uint64Field @12 :UInt64;

  float32Field @7 :Float32;
  float64Field @5 :Float64;

  textField1 @11 :Text;
  textField2 @9 :Text;
  dataField1 @3 :Data;
  dataField2 @1 :Data;

  intListField @17 :List(Int32);
  textListField @16 :List(Text);

  enum TestEnum {
    member0 @0;
    member1 @1;
    member2 @2;
  }

  enumField @18 :TestEnum;

  datetimeIntField @19 :Int32;
  datetimeFloatField @20 :Float64;

  struct NestedStruct {
    int @0 :Int32;
  }
  nestedList @21 :List(List(List(NestedStruct)));
}

struct TestInvalidDatetimeIntStruct {
  datetimeField @0 :Int16;
}

struct TestInvalidDatetimeFloatStruct {
  datetimeField @0 :Float32;
}

struct TestPointerStruct {

  struct EmptyStruct {
  }

  struct TestException {
  }

  struct TupleField1 {
    intField @0 :Int32;
  }

  groupField :group {
    groupIntField @0 :Int32;
  }
  tupleField1 @1 :TupleField1;
  tupleField2 :group {
    tuple2IntField @2 :Int32;
  }
  exceptionField1 @3 :TestException;
  exceptionField2 :group {
    exceptionIntField @4 :Int32;
  }
  structField @5 :EmptyStruct;
}

struct TestUnionStruct {
  u0 :union {
    m0 @0 :Void;
    m1 @1 :Text;
  }
  u1 :union {
    m2 @2 :Int32;
    m3 @3 :Void;
    m4 @4 :Data;
  }
  u2 :union {
    m5 @5 :Void;
    m6 @6 :TestPointerStruct.EmptyStruct;
  }
  union {
    m7 @7 :Void;
    m8 @8 :Bool;
  }
}

struct TestNestedUnionStruct {
  union {
    u0 :union {
      m0 @0 :Bool;
      m1 @1 :Int32;
      m2 @2 :Void;
    }
    u1 :union {
      m3 @3 :Text;
      m4 @4 :Data;
    }
  }
}

struct TestMatchUnionMemberStruct {
  struct Struct0 {}
  struct Struct1 {}
  struct Struct2 {}
  struct Struct3 {}
  struct Struct4 {}
  struct Struct5 {}
  struct Struct6 {}
  struct Struct7 {}
  struct Struct8 {}
  struct Struct9 {}
  u0 :union {
    m0 @0 :Struct0;
    m1 @1 :Struct1;
    m2 @2 :Struct2;
    m3 @3 :Struct3;
    m4 @4 :Struct4;
    m5 @5 :Struct5;
    m6 @6 :Struct6;
    m7 @7 :Struct7;
    m8 @8 :Struct8;
    m9 @9 :Struct9;
  }
}

struct RecursiveStruct {
  structField @0 :RecursiveStruct;
}
