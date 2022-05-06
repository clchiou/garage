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
  struct Args {
  }
  args @0 :Args;
}

struct NullResponse {
  struct Result {
  }
  struct Error {
  }
  union {
    result @0 :Result;
    error @1 :Error;
  }
}

struct Interface1Request {
  struct Args {
    struct Func1 {
      x @0 :Int32;
      y @1 :List(Text);
    }
    func1 @0 :Func1;
  }
  args @0 :Args;
}

struct Interface1Response {
  struct Result {
    func1 @0 :Foo;
  }
  struct Error {
    someError @0 :SomeError;
  }
  union {
    result @0 :Result;
    error @1 :Error;
  }
}

struct Interface2Request {
  struct Func2 {
  }
  struct Func3 {
    x @0 :Data;
  }
  args :union {
    func2 @0 :Func2;
    func3 @1 :Func3;
  }
}

struct Interface2Response {
  struct Result {
    union {
      func2 @0 :Int32;
      func3 @1 :Void;
    }
  }
  struct Error {
    union {
      someError @0 :SomeError;
      someOtherError @1 :SomeOtherError;
    }
  }
  union {
    result @0 :Result;
    error @1 :Error;
  }
}
