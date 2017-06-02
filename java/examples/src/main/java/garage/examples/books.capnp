@0xf96857cbff3abebf;

using Java = import "/capnp/java.capnp";
$Java.package("garage.examples");
$Java.outerClassname("Books");

struct Book {
  id @0 :UInt32;
  title @1 :Text;
  authors @2 :List(Text);
}
