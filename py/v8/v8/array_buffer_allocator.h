#ifndef V8_PYTHON_ARRAY_BUFFER_ALLOCATOR_H_
#define V8_PYTHON_ARRAY_BUFFER_ALLOCATOR_H_

#include <cstdlib>
#include <cstring>

#include "v8.h"

namespace v8_python {
  class ArrayBufferAllocator : public v8::ArrayBuffer::Allocator {
   public:
    virtual void *Allocate(size_t length) {
      void *data = AllocateUninitialized(length);
      return !data ? data : memset(data, 0, length);
    }

    virtual void* AllocateUninitialized(size_t length) {
      return malloc(length);
    }

    virtual void Free(void* data, size_t) {
       free(data);
    }

    static v8::ArrayBuffer::Allocator* GetStatic() {
      static ArrayBufferAllocator allocator;
      return &allocator;
    }
  };
}

#endif  // V8_PYTHON_ARRAY_BUFFER_ALLOCATOR_H_
