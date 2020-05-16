@0xfbf00478e12cc4ce;

using Java = import "/capnp/java.capnp";
$Java.package("g1.example");
$Java.outerClassname("Books");

struct Book {
  id @0 :UInt32;
  title @1 :Text;
  authors @2 :List(Text);
}
