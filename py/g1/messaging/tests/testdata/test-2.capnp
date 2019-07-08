@0x93834e6dd5a992b7;

using Cxx = import "/capnp/c++.capnp";
$Cxx.namespace("g1::messaging::tests::test_2");

struct SomeError {
  message @0 :Text;
}

struct SomeOtherError {
  code @0 :Int32;
  message @1 :Text;
}

struct Foo {
  boolField @0 :Bool;
}

struct NullRequest {
  request @0 :Void;
}

struct NullResponse {
  result @0 :Void;
  error @1 :Void;
}

struct Interface1Request {
  request @0 :Func1Request;
}

struct Interface1Response {
  result :union {
    none @0 :Void;
    foo @2 :Foo;
  }
  error :union {
    none @1 :Void;
    someError @3 :SomeError;
  }
}

struct Func1Request $Cxx.name("func1") {
  x @0 :Int32;
  y @1 :List(Text);
}

struct Interface2Request {
  request :union {
    func2 @0 :Func2Request;
    func3 @1 :Func3Request;
  }
}

struct Interface2Response {
  result :union {
    none @0 :Void;
    int @1 :Int32;
    str @2 :Text;
  }
  error :union {
    none @3 :Void;
    someError @4 :SomeError;
    someOtherError @5 :SomeOtherError;
  }
}

struct Func2Request $Cxx.name("func2") {
}

struct Func3Request $Cxx.name("func3") {
  x @0 :Data;
}
