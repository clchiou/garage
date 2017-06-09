@0xcd9f4c2c27cfeec6;

using Cxx = import "/capnp/c++.capnp";
$Cxx.namespace("unittest::test_1");

struct SomeStruct $Cxx.name("AliasForSomeStruct") {

  b @0 :Bool = true;

  i8 @1 :Int8 = 1;
  i16 @2 :Int16 = 2;
  i32 @3 :Int32 = 3;
  i64 @4 :Int64 = 4;

  u8 @5 :UInt8;
  u16 @6 :UInt16;
  u32 @7 :UInt32;
  u64 @8 :UInt64;

  f32 @9 :Float32;
  f64 @10 :Float64;

  t @11 :Text = "string with \"quotes\"";
  d @12 :Data = 0x"ab cd ef";

  e @13 :SomeEnum = e1;

  l @14 :List(List(List(SomeEnum)));

  u :union {
    v @15 :Void;
    b @16 :Bool;
  }

  g :group {
    i8 @17 :Int8;
    f32 @18 :Float32;
  }

  s1 @19 :EmbeddedStruct1 = (s2 = (s3 = (i32 = 999)));
  ls1 @20 :List(EmbeddedStruct1) = [(ls2 = [(ls3 = [(i32 = 999)])])];

  struct EmbeddedStruct1 {
    s2 @0 :EmbeddedStruct2;
    ls2 @1 :List(EmbeddedStruct2);
  }

  struct EmbeddedStruct2 {
    s3 @0 :EmbeddedStruct3;
    ls3 @1 :List(EmbeddedStruct3);
  }

  struct EmbeddedStruct3 {
    i32 @0 :Int32;
  }
}

enum SomeEnum {
  e0 @0;
  e1 @1;
}

# TODO: Test const.
