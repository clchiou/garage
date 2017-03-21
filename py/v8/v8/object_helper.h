#ifndef V8_PYTHON_OBJECT_HELPER_H_
#define V8_PYTHON_OBJECT_HELPER_H_

#include "include/v8.h"

// Unfortunately, in generated code, Cython declares variables
// uninitialized (which is a problem when the object's default
// constructor is private).
namespace v8_python {
  static bool ObjectHas(
      v8::Local<v8::Context> context,
      v8::Local<v8::Object> object,
      v8::Local<v8::String> name,
      bool *out) {
    v8::Maybe<bool> has = object->Has(
        context, v8::Local<v8::Value>::Cast(name));
    if (has.IsNothing()) {
      return false;
    } else {
      *out = has.FromJust();
      return true;
    }
  }
}

#endif  // V8_PYTHON_OBJECT_HELPER_H_
