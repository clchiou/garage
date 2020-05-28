@0xfbf00478e12cc4ce;

using Java = import "/capnp/java.capnp";
$Java.package("g1.example");
$Java.outerClassname("Books");

struct Book {
  id @0 :UInt32;
  title @1 :Text;
  authors @2 :List(Text);
}

struct InternalError {
}

struct InvalidRequestError {
}

struct BookRequest {
  struct GetBook {
    id @0 :UInt32;
  }
  struct ListBooks {
  }
  struct Args {
    union {
      getBook @0 :GetBook;
      listBooks @1 :ListBooks;
    }
  }
  args @0 :Args;
}

struct BookResponse {
  struct Result {
    union {
      getBook @0 :Book;
      listBooks @1 :List(Book);
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
