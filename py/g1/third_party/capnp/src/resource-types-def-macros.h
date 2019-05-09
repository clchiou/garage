// Helper macros for exposing a resource type.

#define RESOURCE_CLASS_(TYPE, ...)                                                      \
  using Type = TYPE;                                                                    \
  boost::python::class_<Type, ResourceSharedPtr<Type>, boost::noncopyable>(__VA_ARGS__) \
      .def("_reset", &capnp_python::ResourceSharedPtr<Type>::reset)

#define DERIVED_RESOURCE_CLASS_(TYPE, BASE, ...)                                             \
  using Type = TYPE;                                                                         \
  boost::python::                                                                            \
      class_<Type, boost::python::bases<BASE>, ResourceSharedPtr<Type>, boost::noncopyable>( \
          __VA_ARGS__)                                                                       \
          .def("_reset", &capnp_python::ResourceSharedPtr<Type>::reset)

#define DEF(NAME) def(#NAME, &Type::NAME)

#define DEF_LEN() def("__len__", &Type::size)
// This needs special-methods.h.
#define DEF_GETITEM(E) def("__getitem__", &ResourceSpecialMethods<Type, E>::getitem)

// Expose a member function that returns a resource.
#define DEF_R(NAME, R, ...) \
  def(#NAME, &MemberFuncReturningResource<Type, R, ##__VA_ARGS__>::memberFunc<&Type::NAME>)
#define DEF_R_CONST(NAME, R, ...) \
  def(#NAME, &MemberFuncReturningResource<const Type, R, ##__VA_ARGS__>::memberFunc<&Type::NAME>)
