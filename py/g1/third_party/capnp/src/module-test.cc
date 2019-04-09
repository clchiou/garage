#include <boost/python/module.hpp>

namespace capnp_python {
namespace test {

void defineStringTypesForTesting(void);

}  // namespace test
}  // namespace capnp_python

BOOST_PYTHON_MODULE(_capnp_test) {
  capnp_python::test::defineStringTypesForTesting();
}
