#include "include/v8.h"

namespace v8_python {
  // Because v8::HandleScope forbids new/delete directly...
  class HandleScope {
   public:
    explicit HandleScope(v8::Isolate* isolate) : handle_scope_(isolate) {}

   private:
    v8::HandleScope handle_scope_;
  };
}
