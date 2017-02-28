@0x9b9cdec2dea9acaa;

using Cxx = import "/capnp/c++.capnp";
$Cxx.namespace("examples::books");

struct Book {
  title @0 :Text;
  authors @1 :List(Text);
}
