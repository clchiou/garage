@0xcd9f4c2c27cfeec6;

using Cxx = import "/capnp/c++.capnp";
$Cxx.namespace("unittest");

struct SomeStruct $Cxx.name("AliasForSomeStruct") {

  boolWithDefault @0 :Bool = true;

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

  e @13 :SomeEnum;

  l @14 :List(List(List(SomeEnum)));

  # TODO: Test nested struct.
}

enum SomeEnum {
  e0 @0;
  e1 @1;
}

# TODO: Test const.
