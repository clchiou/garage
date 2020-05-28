@0xd97751c104fe5d50;

using Java = import "/capnp/java.capnp";
$Java.package("g1.messaging");
$Java.outerClassname("Calculator");

struct InternalError {
}

struct InvalidRequestError {
}

struct CalculatorRequest {
  struct Add {
    x @0 :Float64;
    y @1 :Float64;
  }
  struct Sub {
    x @0 :Float64;
    y @1 :Float64;
  }
  struct Mul {
    x @0 :Float64;
    y @1 :Float64;
  }
  struct Div {
    x @0 :Float64;
    y @1 :Float64;
  }
  struct Args {
    union {
      add @0 :Add;
      sub @1 :Sub;
      mul @2 :Mul;
      div @3 :Div;
    }
  }
  args @0 :Args;
}

struct CalculatorResponse {
  struct Result {
    union {
      add @0 :Float64;
      sub @1 :Float64;
      mul @2 :Float64;
      div @3 :Float64;
    }
  }
  struct Error {
    union {
      internalError @0 :InternalError;
      invalidRequestError @1 :InvalidRequestError;
    }
  }
  union {
    result @0 :Result;
    error @1 :Error;
  }
}
