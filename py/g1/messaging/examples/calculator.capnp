@0xd97751c104fe5d50;

using Cxx = import "/capnp/c++.capnp";
$Cxx.namespace("examples::calculator");

struct CalculatorRequest {
  args :union {
    add :group {
      x @0 :Float64;
      y @1 :Float64;
    }
    sub :group {
      x @2 :Float64;
      y @3 :Float64;
    }
    mul :group {
      x @4 :Float64;
      y @5 :Float64;
    }
    div :group {
      x @6 :Float64;
      y @7 :Float64;
    }
  }
}

struct CalculatorResponse {
  union {
    result :union {
      add @0 :Float64;
      sub @1 :Float64;
      mul @2 :Float64;
      div @3 :Float64;
    }
    error :group {
      zeroDivisionError :group {
        message @4 :Text;
      }
    }
  }
}
