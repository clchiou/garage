#include <array>
#include <cstdint>
#include <exception>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>

#include <Python.h>

#include <boost/python/class.hpp>
#include <boost/python/def.hpp>
#include <boost/python/errors.hpp>
#include <boost/python/exception_translator.hpp>
#include <boost/python/extract.hpp>
#include <boost/python/handle.hpp>
#include <boost/python/init.hpp>
#include <boost/python/module.hpp>
#include <boost/python/object.hpp>
#include <boost/python/return_arg.hpp>
#include <boost/python/scope.hpp>

#include "include/libplatform/libplatform.h"
#include "include/v8.h"

namespace v8_python {

/**
 * Raise a Python exception if predicate is false.
 */
void Assert(bool predicate, PyObject* exc_type, const char* message) {
  if (!predicate) {
    if (PyErr_Occurred()) {
      PySys_WriteStderr("assertion failed after an exception was raised\n");
      PyErr_Print();
    }
    PyErr_SetString(exc_type, message);
    throw boost::python::error_already_set();
  }
}

//
// Macro definitions.
//

/**
 * Arguments of __exit__.
 */
#define EXIT_ARGS() \
  boost::python::object exc_type, boost::python::object exc_value, boost::python::object traceback

//
// Global variables and module-level initializer/finalizer.
//

/**
 * Module name, loaded in module initialization function.
 */
static std::string MODULE_NAME;

/**
 * Lock for guarding global variables.
 */
static std::mutex MUTEX;

/**
 * True if V8 has been initialized.
 *
 * This state is never reset even after Shutdown is called because
 * v8::V8::Dispose is permanent (V8 cannot be re-initialized).
 */
static bool INITIALIZED = false;

/**
 * Python JavaScriptError type, set by Initialize.
 */
static PyObject* JAVASCRIPT_ERROR_TYPE;

/**
 * Container of the v8::Platform object.
 */
static std::unique_ptr<v8::Platform> PLATFORM;

/**
 * Shared parameters for a new v8::Isolate.
 *
 * For now we create all v8::Isolate objects with the same parameters.
 */
static v8::Isolate::CreateParams CREATE_PARAMS;

/**
 * Container of v8::ArrayBuffer allocator.
 *
 * NOTE: This is a global variable because I assume that we can share
 * (and should?) this allocator across v8::Isolate objects.
 */
static std::unique_ptr<v8::ArrayBuffer::Allocator> ALLOCATOR;

/**
 * Return __file__ attribute from module `MODULE_NAME`.
 */
std::optional<std::string> GetLibraryPath(void) {
  PyObject* name = nullptr;
  PyObject* module = nullptr;

  name = PyUnicode_FromString(MODULE_NAME.c_str());
  if (!name) {
    goto error;
  }

  module = PyImport_GetModule(name);
  if (!module) {
    goto error;
  }

  {
    boost::python::object module_object(boost::python::handle<>(boost::python::borrowed(module)));
    std::string library_path =
        boost::python::extract<std::string>(module_object.attr("__file__"))();

    Py_DECREF(name);
    Py_DECREF(module);
    return library_path;
  }

error:
  Py_XDECREF(name);
  Py_XDECREF(module);
  return {};
}

static constexpr const char* InitializeDoc =
    R"(Initialize V8.

NOTE: We expose this as a method that __init__.py must call, rather
than calling it directly in the module initialization function below,
because Python/importdl.c:_PyImport_LoadDynamicModuleWithSpec only
adds __file__ to the module object after the module initialization
function is called, and we need __file__ when calling
InitializeICUDefaultLocation.)";
void Initialize(boost::python::object java_script_error_type) {
  std::lock_guard<std::mutex> _(MUTEX);

  if (PLATFORM) {
    return;
  }
  if (INITIALIZED) {
    throw std::runtime_error("V8 cannot be re-initialized");
  }

  JAVASCRIPT_ERROR_TYPE = java_script_error_type.ptr();
  Py_INCREF(JAVASCRIPT_ERROR_TYPE);

  std::optional<std::string> library_path = GetLibraryPath();
  Assert(library_path.has_value(), PyExc_RuntimeError, "unable to get __file__");
  v8::V8::InitializeICUDefaultLocation(library_path->c_str());
  v8::V8::InitializeExternalStartupData(library_path->c_str());

  PLATFORM = v8::platform::NewDefaultPlatform();
  v8::V8::InitializePlatform(PLATFORM.get());
  v8::V8::Initialize();

  ALLOCATOR.reset(v8::ArrayBuffer::Allocator::NewDefaultAllocator());
  CREATE_PARAMS.array_buffer_allocator = ALLOCATOR.get();

  INITIALIZED = true;
}

static constexpr const char* ShutdownDoc =
    R"(Shutdown V8.

Generally you do not need to call this unless you need the resources
taken up by V8.

NOTE: This is "permanent" in the sense that V8 cannot be
re-initialized.)";
void Shutdown(void) {
  std::lock_guard<std::mutex> _(MUTEX);

  if (!PLATFORM) {
    return;
  }

  v8::V8::Dispose();
  v8::V8::ShutdownPlatform();

  PLATFORM.reset();
  ALLOCATOR.reset();
}

//
// Error handling.
//

class JavaScriptError : public std::exception {
 public:
  explicit JavaScriptError(const std::string& message) : message_(message) {}

  virtual const char* what() const throw() override { return message_.c_str(); }

 private:
  std::string message_;
};

void TranslateException(const JavaScriptError& exc) {
  PyErr_SetString(JAVASCRIPT_ERROR_TYPE, exc.what());
}

/**
 * Private helper of FormatException.
 */
void FormatExceptionSourceLine(v8::Isolate* isolate,
                               v8::Local<v8::Context> context,
                               v8::Local<v8::Message> message,
                               std::string* output) {
  constexpr const char* INDENT = "  ";

  v8::Local<v8::String> source_line;
  if (!message->GetSourceLine(context).ToLocal(&source_line)) {
    return;
  }
  if (source_line->Length() <= 0) {
    return;
  }
  v8::String::Utf8Value source_line_utf8(isolate, source_line);
  if (!*source_line_utf8) {
    return;
  }

  v8::String::Utf8Value filename(isolate, message->GetScriptResourceName());
  if (*filename) {
    output->append("\n");
    output->append(INDENT);
    output->append("File \"");
    output->append(*filename);
    output->append("\"");
    v8::Maybe<int> line_number = message->GetLineNumber(context);
    if (line_number.IsJust()) {
      output->append(", line ");
      output->append(std::to_string(line_number.FromJust()));
    }
  }

  // Always format source line in the next line.
  output->append("\n");
  output->append(INDENT);
  output->append(*source_line_utf8);

  v8::Maybe<int> start = message->GetStartColumn(context);
  v8::Maybe<int> end = message->GetEndColumn(context);
  if (start.IsNothing() || end.IsNothing()) {
    return;
  }
  output->append("\n");
  output->append(INDENT);
  output->append(start.FromJust(), ' ');
  output->append(end.FromJust() - start.FromJust(), '^');
}

/**
 * Format JavaScript exception to a std::string.
 *
 * The format is (without the trailing newline):
 * ```
 * {exception}
 *   File "{filename}", line {line_number}
 *   {source_line}
 *   ^^^^
 * ```
 *
 * We do not format stack trace for now because V8 does not seem to
 * provide much useful info there.
 */
std::string FormatException(v8::Isolate* isolate, v8::TryCatch* try_catch) {
  std::string output;
  v8::String::Utf8Value exception(isolate, try_catch->Exception());
  if (*exception) {
    output.append(*exception);
  }
  v8::Local<v8::Message> message = try_catch->Message();
  if (!message.IsEmpty()) {
    FormatExceptionSourceLine(isolate, isolate->GetCurrentContext(), message, &output);
  }
  return output;
}

//
// Resource types.
//

/**
 * Templated mixin class providing Python context manager interface.
 *
 * The resource is managed by shared_ptr `resource_` that is exposed to
 * child classes.
 *
 * The context manager allows Enter to be called once.  Otherwise the
 * innermost Exit will clean up the resource, which is generally not
 * what you expect.  Also, since Exit clean up the resource, it make no
 * much sense to allow re-entering this manager.
 */
template <class T>
class ContextManagerMixin {
 public:
  ContextManagerMixin() : entered_(false) {}

  void Enter() {
    if (entered_) {
      throw std::runtime_error("this context manager only allows being entered once");
    }
    entered_ = true;
  }

  void Exit(EXIT_ARGS()) { resource_.reset(); }

 protected:
  std::shared_ptr<T> resource_;

 private:
  bool entered_;
};

static constexpr const char* IsolateDoc =
    R"(Wrapper of v8::Isolate.

It supports context manager interface for disposing the v8::Isolate
object.)";
class Isolate : public ContextManagerMixin<v8::Isolate> {
 public:
  static constexpr const char* ScopeDoc =
      R"(Helper context manager that enters and exits an isolate.

Re-entering an isolate is allowed.)";
  class Scope {
   public:
    explicit Scope(const Isolate& isolate) : isolate_(isolate.Get()) {}

    void Enter() { isolate_->Enter(); }
    void Exit(EXIT_ARGS()) { isolate_->Exit(); }

   private:
    // NOTE: We deliberately take a raw pointer here rather than Isolate
    // object's shared_ptr so that even when a Scope object is leaked or
    // retained, v8::Isolate will still be disposed.  The downside is
    // that a leaked or retained Scope object might access an invalid
    // v8::Isolate pointer.
    v8::Isolate* isolate_;
  };

  static int num_alive;

  Isolate() {
    std::lock_guard<std::mutex> _(MUTEX);
    if (!PLATFORM) {
      throw std::runtime_error("V8 is not initialized");
    }
    resource_ = std::shared_ptr<v8::Isolate>(v8::Isolate::New(CREATE_PARAMS), &Isolate::Dispose);
    num_alive++;
  }

  Scope MakeScope() { return Scope(*this); }

 private:
  friend class Context;
  friend class GlobalContext;
  friend class HandleScope;

  static void Dispose(v8::Isolate* isolate) {
    isolate->Dispose();
    num_alive--;
  }

  v8::Isolate* Get() const { return resource_.get(); }
};

int Isolate::num_alive = 0;

static constexpr const char* HandleScopeDoc =
    R"(Wrapper of v8::HandleScope.

It supports context manager interface for releasing its handles.)";
class HandleScope : public ContextManagerMixin<v8::HandleScope> {
 public:
  explicit HandleScope(const Isolate& isolate) {
    // By the way, V8 bans `operator new` in  HandleScope, but luckily
    // std::make_shared does not call `operator new`.
    resource_ = std::make_shared<v8::HandleScope>(isolate.Get());
  }
};

class Context;

static constexpr const char* GlobalContextDoc =
    R"(Wrapper of v8::Global<v8::Context>>.

It supports context manager interface for releasing the context.)";
// Use ContextManagerMixin (shared_ptr) because v8::Global bans copy.
class GlobalContext : public ContextManagerMixin<v8::Global<v8::Context>> {
 public:
  GlobalContext(const Isolate& isolate, const Context& context);

  Context Get(const Isolate& isolate) const;
};

//
// The `undefined` type.
//
// We define it similar to how NoneType is defined.
//
// NOTE: Since C++ does not not fully support C designated initializers,
// we cannot define UNDEFINED_TYPE and UNDEFINED_AS_NUMBER in the
// idiomatic way.
//

PyTypeObject UNDEFINED_TYPE;

PyNumberMethods UNDEFINED_AS_NUMBER;

PyObject UNDEFINED_OBJECT = {_PyObject_EXTRA_INIT 1, &UNDEFINED_TYPE};

PyObject* UndefinedNew(PyTypeObject*, PyObject* args, PyObject* kwargs) {
  if (PyTuple_GET_SIZE(args) || (kwargs && PyDict_GET_SIZE(kwargs))) {
    PyErr_SetString(PyExc_TypeError, "UndefinedType takes no arguments");
    return NULL;
  }
  Py_INCREF(&UNDEFINED_OBJECT);
  return &UNDEFINED_OBJECT;
}

PyObject* UndefinedRepr(PyObject*) {
  return PyUnicode_FromString("Undefined");
}

int UndefinedBool(PyObject*) {
  return 0;
}

void UndefinedDealloc(PyObject*) {
  Py_FatalError("deallocating Undefined");
}

void DefineUndefined(void) {
  UNDEFINED_TYPE = {PyVarObject_HEAD_INIT(&PyType_Type, 0)};
  UNDEFINED_TYPE.tp_name = "v8._v8.UndefinedType";
  UNDEFINED_TYPE.tp_new = UndefinedNew;
  UNDEFINED_TYPE.tp_flags = Py_TPFLAGS_DEFAULT;
  UNDEFINED_TYPE.tp_repr = UndefinedRepr;
  UNDEFINED_TYPE.tp_as_number = &UNDEFINED_AS_NUMBER;
  UNDEFINED_TYPE.tp_dealloc = UndefinedDealloc;

  UNDEFINED_AS_NUMBER.nb_bool = UndefinedBool;

  boost::python::scope().attr("UndefinedType") =
      boost::python::handle<>(boost::python::borrowed(&UNDEFINED_TYPE));
  boost::python::scope().attr("UNDEFINED") =
      boost::python::handle<>(boost::python::borrowed(&UNDEFINED_OBJECT));
}

//
// Value types.
//
// Our basic strategy is to:
//
// * Auto-convert "primitive" JSON types to their Python counterparts:
//   None, bool, int, float, and str.
//
// * Provide read and write accessors for container JSON types.  Note
//   that for write accessors, we restrict them to accept "primitive"
//   Python types for now.
//
// * Wrap other types in an opaque wrapper.
//
// It appears that v8::Local<T> follows value semantics.  We should be
// able to wrap them without shared_ptr.
//
// NOTE: Due to weird requirements of Boost.Python on constructors that
// I do not fully understand, I still have to wrap value types in a thin
// class if they use custom constructors.
//

v8::Local<v8::Value> FromPython(boost::python::object object, v8::Local<v8::Context> context);

boost::python::object ToPython(v8::Local<v8::Value> value, v8::Local<v8::Context> context);

/**
 * Make a v8::Local<v8::String> in the given isolate.
 */
v8::Local<v8::String> MakeString(v8::Isolate* isolate, const std::string& string) {
  v8::Local<v8::String> output;
  if (!v8::String::NewFromUtf8(isolate, string.c_str(), v8::NewStringType::kNormal, string.length())
           .ToLocal(&output)) {
    throw std::runtime_error("unable to allocate memory for string");
  }
  return output;
}

static constexpr const char* ValueDoc = R"(Wrapper of v8::Local<v8::Value>.)";
class Value {
 public:
  // While this is not strictly required, but we also store a copy of
  // v8::Context for convenience.
  Value(const v8::Local<v8::Value>& self, const v8::Local<v8::Context>& context)
      : self_(self), context_(context) {}

  virtual ~Value() {}

  virtual std::string Repr() const { return ReprImpl("Value"); }

  template <bool (v8::Value::*is)() const>
  bool Is() const {
    return std::invoke(is, *self_);
  }

 private:
  friend class Array;
  friend class Object;
  friend v8::Local<v8::Value> FromPython(boost::python::object object,
                                         v8::Local<v8::Context> context);

  /**
   * Call v8::Object::Get.
   *
   * Key type must be either v8::Local<v8::Value> or uint32_t.
   */
  template <typename T>
  v8::Local<v8::Value> Get(T&& key) const {
    v8::Local<v8::Value> output;
    if (!self_.As<v8::Object>()->Get(context_, key).ToLocal(&output)) {
      PyErr_SetString(PyExc_KeyError, "Object::Get call fails");
      throw boost::python::error_already_set();
    }
    return output;
  }

  /**
   * Call v8::Object::Set.
   *
   * Key type must be either v8::Local<v8::Value> or uint32_t.
   */
  template <typename T>
  void Set(T&& key, v8::Local<v8::Value> value) {
    v8::Maybe<bool> output = self_.As<v8::Object>()->Set(context_, key, value);
    Assert(output.IsJust() && output.FromJust(), PyExc_ValueError, "Object::Set call fails");
  }

  std::string ReprImpl(const char* class_name) const {
    std::string output;
    output.append("<");
    output.append(MODULE_NAME);
    output.append(".");
    output.append(class_name);
    output.append(" object ");
    std::optional<std::string> detail = GetDetailString();
    if (detail) {
      output.append(*detail);
    } else {
      output.append("[?]");
    }
    output.append(">");
    return output;
  }

  std::optional<std::string> GetDetailString() const {
    v8::Local<v8::String> detail;
    if (!self_->ToDetailString(context_).ToLocal(&detail)) {
      return {};
    }
    if (detail->Length() <= 0) {
      return {};
    }
    v8::String::Utf8Value detail_utf8(context_->GetIsolate(), detail);
    if (!*detail_utf8) {
      return {};
    }
    return *detail_utf8;
  }

  v8::Local<v8::Value> self_;
  v8::Local<v8::Context> context_;
};

static constexpr const char* ArrayDoc =
    R"(Wrapper of v8::Local<v8::Array>.

Note that for __setitem__, we restrict them to accept only "primitive"
value types for now.)";
class Array : public Value {
 public:
  class Iterator : public Value {
   public:
    Iterator(const v8::Local<v8::Value>& self, const v8::Local<v8::Context>& context)
        : Value(self, context), index_(0) {
      Assert(self_->IsArray(), PyExc_TypeError, "expect an array value");
    }

    virtual ~Iterator() {}

    virtual std::string Repr() const override { return ReprImpl("Array.Iterator"); }

    boost::python::object Next() {
      if (index_ >= self_.As<v8::Array>()->Length()) {
        PyErr_SetNone(PyExc_StopIteration);
        throw boost::python::error_already_set();
      }
      return ToPython(Get(index_++), context_);
    }

   private:
    v8::Local<v8::Array> array_;
    uint32_t index_;
  };

  Array(const v8::Local<v8::Value>& self, const v8::Local<v8::Context>& context)
      : Value(self, context), push_(LoadPush(context)) {
    Assert(self_->IsArray(), PyExc_TypeError, "expect an array value");
  }

  explicit Array(const Context& context);

  virtual ~Array() {}

  virtual std::string Repr() const override { return ReprImpl("Array"); }

  uint32_t Len() const { return self_.As<v8::Array>()->Length(); }

  boost::python::object Iter() const { return boost::python::object(Iterator(self_, context_)); }

  bool Contains(boost::python::object value) const {
    v8::Local<v8::Value> target = FromPython(value, context_);
    uint32_t length = Len();
    for (uint32_t index = 0; index < length; index++) {
      // Should we use JS == instead?
      if (Get(index)->StrictEquals(target)) {
        return true;
      }
    }
    return false;
  }

  boost::python::object Getitem(uint32_t index) const {
    CheckIndexRange(index);
    return ToPython(Get(index), context_);
  }

  void Setitem(uint32_t index, boost::python::object value) {
    CheckIndexRange(index);
    Set(index, FromPython(value, context_));
  }

  void Append(boost::python::object value) {
    v8::Local<v8::Value> argv[] = {FromPython(value, context_)};
    if (push_->Call(context_, self_, 1, argv).IsEmpty()) {
      PyErr_SetString(PyExc_ValueError, "Array.prototype.push call fails");
      throw boost::python::error_already_set();
    }
  }

 private:
  static v8::Local<v8::Function> LoadPush(v8::Local<v8::Context> context) {
    v8::Isolate* isolate = context->GetIsolate();
    v8::Local<v8::Value> output = context->Global();
    for (const v8::Local<v8::String>& key :
         std::array{v8::String::NewFromUtf8Literal(isolate, "Array"),
                    v8::String::NewFromUtf8Literal(isolate, "prototype"),
                    v8::String::NewFromUtf8Literal(isolate, "push")}) {
      Assert(output->IsObject(), PyExc_AssertionError, "expect an object");
      if (!output.As<v8::Object>()->Get(context, key).ToLocal(&output)) {
        PyErr_SetString(PyExc_KeyError, "Object::Get call fails");
        throw boost::python::error_already_set();
      }
    }
    Assert(output->IsFunction(), PyExc_AssertionError, "expect a function");
    return output.As<v8::Function>();
  }

  void CheckIndexRange(uint32_t index) const {
    uint32_t length = Len();
    if (!(0 <= index && index < length)) {
      std::string message;
      message.append("expect array index 0 <= x < ");
      message.append(std::to_string(length));
      message.append(", not ");
      message.append(std::to_string(index));
      throw std::out_of_range(message);
    }
  }

  v8::Local<v8::Function> push_;
};

static constexpr const char* ObjectDoc =
    R"(Wrapper of v8::Local<v8::Object>.

We treat v8::Object like a container and expose a dict-like interface,
rather than attribute accessors.  But there is one key difference in the
interface vs Python's dict: JavaScript only accepts strings and symbols
as property names.  If you provide any other type of property name, it
**will be coerced** into a string!  This behavior is very different from
Python dict's, and quite confusing in my opinion.  Anyway, this is why
the wrapper raises TypeError on non-string key types.

Note that for __setitem__, we restrict them to accept only "primitive"
value types for now.)";
class Object : public Value {
 private:
  /**
   * Call v8::Object::GetOwnPropertyNames.
   */
  v8::Local<v8::Array> GetOwnPropertyNames() const {
    v8::Local<v8::Array> output;
    if (!self_.As<v8::Object>()->GetOwnPropertyNames(context_).ToLocal(&output)) {
      PyErr_SetString(PyExc_ValueError, "Object::GetOwnPropertyNames call fails");
      throw boost::python::error_already_set();
    }
    return output;
  }

  /**
   * Call v8::Object::HasOwnProperty.
   */
  bool HasOwnProperty(v8::Local<v8::String> key) const {
    v8::Maybe<bool> output = self_.As<v8::Object>()->HasOwnProperty(context_, key);
    Assert(output.IsJust(), PyExc_ValueError, "Object::HasOwnProperty call fails");
    return output.FromJust();
  }

 public:
  Object(const v8::Local<v8::Value>& self, const v8::Local<v8::Context>& context)
      : Value(self, context) {
    Assert(self_->IsObject(), PyExc_TypeError, "expect an object value");
  }

  explicit Object(const Context& context);

  virtual ~Object() {}

  virtual std::string Repr() const override { return ReprImpl("Object"); }

  uint32_t Len() const { return GetOwnPropertyNames()->Length(); }

  boost::python::object Iter() const { return Array(GetOwnPropertyNames(), context_).Iter(); }

  bool Contains(const std::string& key) const {
    return HasOwnProperty(MakeString(context_->GetIsolate(), key));
  }

  boost::python::object Getitem(const std::string& key) const {
    v8::Local<v8::String> k = MakeString(context_->GetIsolate(), key);
    if (!HasOwnProperty(k)) {
      std::string message;
      message.append("'");
      message.append(key);
      message.append("'");
      PyErr_SetString(PyExc_KeyError, message.c_str());
      throw boost::python::error_already_set();
    }
    return ToPython(Get(k), context_);
  }

  void Setitem(const std::string& key, boost::python::object value) {
    Set(MakeString(context_->GetIsolate(), key), FromPython(value, context_));
  }
};

template <typename T, v8::Maybe<T> (v8::Value::*to)(v8::Local<v8::Context> context) const>
T To(v8::Local<v8::Value> value, v8::Local<v8::Context> context) {
  v8::Maybe<T> output = std::invoke(to, *value, context);
  Assert(output.IsJust(), PyExc_ValueError, "unable to convert value to target type");
  return output.FromJust();
}

//
// As for native integer types, V8 accepts int32_t for Integer, and
// int64_t for BigInt.  Python may exports long long for PyLong_Type.
// Here we check that int64_t is larger than long long.
//
static_assert(INT64_MIN <= LLONG_MIN && LLONG_MAX <= INT64_MAX, "expect long long <= int64_t");

/**
 * Convert a Python object to its JavaScript counterpart.
 *
 * Note we only convert "primitive" Python types for now.
 */
v8::Local<v8::Value> FromPython(boost::python::object object, v8::Local<v8::Context> context) {
  PyObject* x = object.ptr();

  if (x == &UNDEFINED_OBJECT) {
    return v8::Undefined(context->GetIsolate());
  }

  if (x == Py_None) {
    return v8::Null(context->GetIsolate());
  }

  if (PyBool_Check(x)) {
    return (x == Py_True ? v8::True : v8::False)(context->GetIsolate());
  }

  // TODO: Use v8::BigInt::NewFromWords when x exceeds 64-bits range.
  if (PyLong_Check(x)) {
    long long ll = PyLong_AsLongLong(x);
    if (PyErr_Occurred()) {
      throw boost::python::error_already_set();
    }
    if (INT32_MIN <= ll && ll <= INT32_MAX) {
      return v8::Integer::New(context->GetIsolate(), static_cast<int32_t>(ll));
    } else if (0 <= ll && ll <= UINT32_MAX) {
      return v8::Integer::NewFromUnsigned(context->GetIsolate(), static_cast<uint32_t>(ll));
    } else {
      return v8::BigInt::New(context->GetIsolate(), ll);
    }
  }

  if (PyFloat_Check(x)) {
    double d = PyFloat_AsDouble(x);
    if (PyErr_Occurred()) {
      throw boost::python::error_already_set();
    }
    return v8::Number::New(context->GetIsolate(), d);
  }

  if (PyUnicode_Check(x)) {
    const char* buffer = PyUnicode_AsUTF8(x);
    if (PyErr_Occurred()) {
      throw boost::python::error_already_set();
    }
    return MakeString(context->GetIsolate(), std::string(buffer));
  }

  //
  // We should not add an extract<Value> to avoid (accidentally) slicing
  // object... I guess?
  //
  boost::python::extract<Array> array_extractor(object);
  if (array_extractor.check()) {
    return array_extractor().self_;
  }
  boost::python::extract<Object> object_extractor(object);
  if (object_extractor.check()) {
    return object_extractor().self_;
  }

  PyErr_Format(PyExc_TypeError, "to-JavaScript conversion is unsupported: %R", x);
  throw boost::python::error_already_set();
}

/**
 * Convert a v8::Value object to its Python counterpart.
 *
 * We map JavaScript/JSON null to Python None.  As for JavaScript
 * undefined, we map it to our custom singleton value defined above.
 */
boost::python::object ToPython(v8::Local<v8::Value> value, v8::Local<v8::Context> context) {
  if (value->IsUndefined()) {
    return boost::python::object(
        boost::python::handle<>(boost::python::borrowed(&UNDEFINED_OBJECT)));
  }

  if (value->IsNull()) {
    return boost::python::object();
  }

  if (value->IsBoolean()) {
    return boost::python::object(value->IsTrue());
  }

  // NOTE: You must check int before float because the latter is a
  // superclass of the former.
  if (value->IsInt32() || value->IsUint32()) {
    return boost::python::object(To<int64_t, &v8::Value::IntegerValue>(value, context));
  }
  if (value->IsBigInt()) {
    bool lossless = false;
    int64_t output = value.As<v8::BigInt>()->Int64Value(&lossless);
    if (lossless) {
      return boost::python::object(output);
    } else {
      // TODO: Handle BigInt-to-PyLong_Type when value exceeds 64-bit range.
      return boost::python::object(To<double, &v8::Value::NumberValue>(value, context));
    }
  }

  if (value->IsNumber()) {
    return boost::python::object(To<double, &v8::Value::NumberValue>(value, context));
  }

  if (value->IsString()) {
    v8::Local<v8::String> output;
    if (!value->ToString(context).ToLocal(&output)) {
      throw std::invalid_argument("unable to convert value to string");
    }
    v8::String::Utf8Value output_utf8(context->GetIsolate(), output);
    if (!*output_utf8) {
      throw std::invalid_argument("unable to convert value to UTF-8 string");
    }
    return boost::python::object(std::string(*output_utf8));
  }

  // NOTE: You must check array before object because the latter is a
  // superclass of the former.
  if (value->IsArray()) {
    return boost::python::object(Array(value, context));
  }

  // Are there any type that is not an object?
  if (value->IsObject()) {
    return boost::python::object(Object(value, context));
  }

  return boost::python::object(Value(value, context));
}

//
// Local context and script type.
//

static constexpr const char* ContextDoc =
    R"(Wrapper of v8::Local<v8::Context>>.

It supports context manager interface for entering and exiting the
context (can be nested).)";
class Context {
 public:
  explicit Context(v8::Local<v8::Context> context) : context_(context) {}
  explicit Context(const Isolate& isolate) : context_(v8::Context::New(isolate.Get())) {}

  void Enter() { context_->Enter(); }
  void Exit(EXIT_ARGS()) { context_->Exit(); }

  uint32_t Len() const { return Global().Len(); }

  boost::python::object Iter() const { return Global().Iter(); }

  bool Contains(const std::string& key) const { return Global().Contains(key); }

  boost::python::object Getitem(const std::string& key) const { return Global().Getitem(key); }

  void Setitem(const std::string& key, boost::python::object value) {
    return Global().Setitem(key, value);
  }

 private:
  friend class Array;
  friend class GlobalContext;
  friend class Object;
  friend class Script;

  /**
   * Return the global object proxy, wrapped in Object.
   */
  Object Global() const { return Object(context_->Global(), context_); }

  v8::Local<v8::Context> context_;
};

static constexpr const char* ScriptDoc = R"(Wrapper of v8::Local<v8::Script>.)";
class Script {
 public:
  Script(const Context& context, const std::string& name, const std::string& script)
      : script_(Compile(context.context_, name, script)) {}

  boost::python::object Run(const Context& context) const {
    return ToPython(RunImpl(context.context_), context.context_);
  }

 private:
  static v8::Local<v8::Script> Compile(v8::Local<v8::Context> context,
                                       const std::string& name,
                                       const std::string& script) {
    v8::Isolate* isolate = context->GetIsolate();
    v8::TryCatch try_catch(isolate);
    v8::ScriptOrigin origin(MakeString(isolate, name));

    v8::MaybeLocal<v8::Script> maybe_output;
    Py_BEGIN_ALLOW_THREADS;  // Add `;` to make clang-format happy.
    maybe_output = v8::Script::Compile(context, MakeString(isolate, script), &origin);
    Py_END_ALLOW_THREADS;  // Add `;` to make clang-format happy.

    v8::Local<v8::Script> output;
    if (!maybe_output.ToLocal(&output)) {
      throw JavaScriptError(FormatException(isolate, &try_catch));
    }
    return output;
  }

  v8::Local<v8::Value> RunImpl(v8::Local<v8::Context> context) const {
    v8::Isolate* isolate = context->GetIsolate();
    v8::TryCatch try_catch(isolate);

    v8::MaybeLocal<v8::Value> maybe_output;
    Py_BEGIN_ALLOW_THREADS;  // Add `;` to make clang-format happy.
    maybe_output = script_->Run(context);
    Py_END_ALLOW_THREADS;  // Add `;` to make clang-format happy.

    v8::Local<v8::Value> output;
    if (!maybe_output.ToLocal(&output)) {
      throw JavaScriptError(FormatException(isolate, &try_catch));
    }
    return output;
  }

  v8::Local<v8::Script> script_;
};

//
// Member functions.
//
// Define them here in case you cannot define them in-class due to
// forward declarations.
//

GlobalContext::GlobalContext(const Isolate& isolate, const Context& context) {
  resource_ = std::make_shared<v8::Global<v8::Context>>(isolate.Get(), context.context_);
}

Context GlobalContext::Get(const Isolate& isolate) const {
  return Context(resource_->Get(isolate.Get()));
}

Array::Array(const Context& context)
    : Value(v8::Array::New(context.context_->GetIsolate()), context.context_),
      push_(LoadPush(context.context_)) {}

Object::Object(const Context& context)
    : Value(v8::Object::New(context.context_->GetIsolate()), context.context_) {}

//
// Macro un-definitions.
//

#undef EXIT_ARGS

}  // namespace v8_python

#define _GET_7TH_ARG(A1, A2, A3, A4, A5, A6, A7, ...) A7

#define _INIT_1_PAIR(T1, N1) boost::python::init<T1>(boost::python::args(#N1))

#define _INIT_2_PAIR(T1, N1, T2, N2) \
  boost::python::init<T1, T2>((boost::python::args(#N1), boost::python::args(#N2)))

#define _INIT_3_PAIR(T1, N1, T2, N2, T3, N3) \
  boost::python::init<T1, T2, T3>(           \
      (boost::python::args(#N1), boost::python::args(#N2), boost::python::args(#N3)))

#define INIT(...)                                                                               \
  _GET_7TH_ARG(__VA_ARGS__, _INIT_3_PAIR, _INIT_ERROR, _INIT_2_PAIR, _INIT_ERROR, _INIT_1_PAIR) \
  (__VA_ARGS__)

#define ENTER(T) def("__enter__", &T::Enter, boost::python::return_self<>())
#define EXIT(T)                                                         \
  def("__exit__", &T::Exit,                                             \
      (boost::python::arg("exc_type"), boost::python::arg("exc_value"), \
       boost::python::arg("traceback")))

BOOST_PYTHON_MODULE(_v8) {
  v8_python::MODULE_NAME =
      boost::python::extract<std::string>(boost::python::scope().attr("__name__"))();

  boost::python::def("initialize", v8_python::Initialize, v8_python::InitializeDoc);
  boost::python::def("shutdown", v8_python::Shutdown, v8_python::ShutdownDoc);

  boost::python::register_exception_translator<v8_python::JavaScriptError>(
      v8_python::TranslateException);

  v8_python::DefineUndefined();

  //
  // For container types (Context, Array, and Object) We choose not to
  // provide __bool__ because that seems to introduce unexpected
  // behaviors to users...?
  //

  {
    boost::python::scope _ =
        boost::python::class_<v8_python::Isolate>("Isolate", v8_python::IsolateDoc)
            .def_readonly("num_alive", v8_python::Isolate::num_alive)
            .ENTER(v8_python::Isolate)
            .EXIT(v8_python::Isolate)
            .def("scope", &v8_python::Isolate::MakeScope);

    boost::python::class_<v8_python::Isolate::Scope>("Scope", v8_python::Isolate::ScopeDoc,
                                                     INIT(const v8_python::Isolate&, isolate))
        .setattr("__qualname__", "Isolate.Scope")
        .ENTER(v8_python::Isolate::Scope)
        .EXIT(v8_python::Isolate::Scope);
  }

  {
    boost::python::class_<v8_python::HandleScope>("HandleScope", v8_python::HandleScopeDoc,
                                                  INIT(const v8_python::Isolate&, isolate))
        .ENTER(v8_python::HandleScope)
        .EXIT(v8_python::HandleScope);
  }

  {
    auto init = INIT(const v8_python::Isolate&, isolate, const v8_python::Context&, context);
    boost::python::class_<v8_python::GlobalContext>("GlobalContext", v8_python::GlobalContextDoc,
                                                    init)
        .ENTER(v8_python::GlobalContext)
        .EXIT(v8_python::GlobalContext)
        .def("get", &v8_python::GlobalContext::Get, boost::python::arg("isolate"));
  }

  {
    boost::python::class_<v8_python::Context>("Context", v8_python::ContextDoc,
                                              INIT(const v8_python::Isolate&, isolate))
        .ENTER(v8_python::Context)
        .EXIT(v8_python::Context)
        .def("__len__", &v8_python::Context::Len)
        .def("__iter__", &v8_python::Context::Iter)
        .def("__contains__", &v8_python::Context::Contains)
        .def("__getitem__", &v8_python::Context::Getitem)
        .def("__setitem__", &v8_python::Context::Setitem);
  }

  {
    auto init = INIT(const v8_python::Context&, context, const std::string&, name,
                     const std::string&, script);
    boost::python::class_<v8_python::Script>("Script", v8_python::ScriptDoc, init)
        .def("run", &v8_python::Script::Run, boost::python::args("context"));
  }

  {
    boost::python::class_<v8_python::Value>("Value", v8_python::ValueDoc, boost::python::no_init)
        .def("__repr__", &v8_python::Value::Repr)
#define DEF_IS(N, F) def(#N, &v8_python::Value::Is<&v8::Value::F>)
        //
        // JavaScript type predicates.
        //
        .DEF_IS(is_undefined, IsUndefined)
        .DEF_IS(is_null, IsNull)
        .DEF_IS(is_null_or_undefined, IsNullOrUndefined)
        .DEF_IS(is_true, IsTrue)
        .DEF_IS(is_false, IsFalse)
        .DEF_IS(is_name, IsName)
        .DEF_IS(is_string, IsString)
        .DEF_IS(is_symbol, IsSymbol)
        .DEF_IS(is_function, IsFunction)
        .DEF_IS(is_array, IsArray)
        .DEF_IS(is_object, IsObject)
        .DEF_IS(is_big_int, IsBigInt)
        .DEF_IS(is_boolean, IsBoolean)
        .DEF_IS(is_number, IsNumber)
        .DEF_IS(is_external, IsExternal)
        .DEF_IS(is_int32, IsInt32)
        .DEF_IS(is_uint32, IsUint32)
        .DEF_IS(is_date, IsDate)
        .DEF_IS(is_arguments_object, IsArgumentsObject)
        .DEF_IS(is_big_int_object, IsBigIntObject)
        .DEF_IS(is_boolean_object, IsBooleanObject)
        .DEF_IS(is_number_object, IsNumberObject)
        .DEF_IS(is_string_object, IsStringObject)
        .DEF_IS(is_symbol_object, IsSymbolObject)
        .DEF_IS(is_native_error, IsNativeError)
        .DEF_IS(is_reg_exp, IsRegExp)
        .DEF_IS(is_async_function, IsAsyncFunction)
        .DEF_IS(is_generator_function, IsGeneratorFunction)
        .DEF_IS(is_generator_object, IsGeneratorObject)
        .DEF_IS(is_promise, IsPromise)
        .DEF_IS(is_map, IsMap)
        .DEF_IS(is_set, IsSet)
        .DEF_IS(is_map_iterator, IsMapIterator)
        .DEF_IS(is_set_iterator, IsSetIterator)
        .DEF_IS(is_weak_map, IsWeakMap)
        .DEF_IS(is_weak_set, IsWeakSet)
        .DEF_IS(is_array_buffer, IsArrayBuffer)
        .DEF_IS(is_array_buffer_view, IsArrayBufferView)
        .DEF_IS(is_typed_array, IsTypedArray)
        .DEF_IS(is_uint8_array, IsUint8Array)
        .DEF_IS(is_uint8_clamped_array, IsUint8ClampedArray)
        .DEF_IS(is_int8_array, IsInt8Array)
        .DEF_IS(is_uint16_array, IsUint16Array)
        .DEF_IS(is_int16_array, IsInt16Array)
        .DEF_IS(is_uint32_array, IsUint32Array)
        .DEF_IS(is_int32_array, IsInt32Array)
        .DEF_IS(is_float32_array, IsFloat32Array)
        .DEF_IS(is_float64_array, IsFloat64Array)
        .DEF_IS(is_big_int64_array, IsBigInt64Array)
        .DEF_IS(is_big_uint64_array, IsBigUint64Array)
        .DEF_IS(is_data_view, IsDataView)
        .DEF_IS(is_shared_array_buffer, IsSharedArrayBuffer)
        .DEF_IS(is_proxy, IsProxy)
        .DEF_IS(is_wasm_module_object, IsWasmModuleObject)
        .DEF_IS(is_module_namespace_object, IsModuleNamespaceObject);
#undef DEF_IS
  }

  {
    boost::python::scope _ =
        boost::python::class_<v8_python::Array, boost::python::bases<v8_python::Value>>(
            "Array", v8_python::ArrayDoc, INIT(const v8_python::Context&, context))
            .def("__len__", &v8_python::Array::Len)
            .def("__iter__", &v8_python::Array::Iter)
            .def("__contains__", &v8_python::Array::Contains)
            .def("__getitem__", &v8_python::Array::Getitem)
            .def("__setitem__", &v8_python::Array::Setitem)
            .def("append", &v8_python::Array::Append);

    boost::python::class_<v8_python::Array::Iterator, boost::python::bases<v8_python::Value>>(
        "Iterator", boost::python::no_init)
        .setattr("__qualname__", "Array.Iterator")
        .def("__next__", &v8_python::Array::Iterator::Next);
  }

  {
    boost::python::class_<v8_python::Object, boost::python::bases<v8_python::Value>>(
        "Object", v8_python::ObjectDoc, INIT(const v8_python::Context&, context))
        .def("__len__", &v8_python::Object::Len)
        .def("__iter__", &v8_python::Object::Iter)
        .def("__contains__", &v8_python::Object::Contains)
        .def("__getitem__", &v8_python::Object::Getitem)
        .def("__setitem__", &v8_python::Object::Setitem);
  }
}

#undef _GET_7TH_ARG

#undef _INIT_1_PAIR
#undef _INIT_2_PAIR
#undef _INIT_3_PAIR
#undef INIT

#undef ENTER
#undef EXIT
