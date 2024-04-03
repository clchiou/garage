@0x935025fbe6cbb3d2;

struct Result(Ok, Err) {
  union {
    ok @0 :Ok;
    err @1 :Err;
  }
}
