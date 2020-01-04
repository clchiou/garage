"""Meta build rules."""

import foreman

(foreman.define_rule('all').with_doc('build everything')\
 .depend('//py/g1/apps:build')
 .depend('//py/g1/asyncs/bases:build')
 .depend('//py/g1/asyncs/kernels:build')
 .depend('//py/g1/asyncs/servers:build')
 .depend('//py/g1/bases:build')
 .depend('//py/g1/databases:build')
 .depend('//py/g1/devtools/buildtools:build')
 .depend('//py/g1/http/clients:build')
 .depend('//py/g1/http/servers:build')
 .depend('//py/g1/messaging:build')
 .depend('//py/g1/networks/servers:build')
 .depend('//py/g1/scripts:build')
 .depend('//py/g1/third-party/capnp:build')
 .depend('//py/g1/third-party/nng:build')
 .depend('//py/g1/threads:build')
 .depend('//py/startup:build')
 .depend('third-party')
 )

(foreman.define_rule('third-party').with_doc('build third-party codes')\
 .depend('//third-party/cpython:build').depend('//third-party/cpython:trim')
 # C++ libraries.
 .depend('config-boost').depend('//third-party/boost:build')
 .depend('//third-party/capnproto:build')
 .depend('//third-party/nng:build')
 # Third-party Python packages.
 .depend('//third-party/lxml:build')
 .depend('//third-party/pyyaml:build')
 .depend('//third-party/requests:build')
 .depend('//third-party/sqlalchemy:build')
 )

# In addition to set `boost:libraries` parameter, `config-boost` also
# imposes ordering between boost:config and boost:build (the former is
# run before the latter).
(foreman.define_rule('config-boost')\
 .depend('//third-party/boost:config',
         parameters={'//third-party/boost:libraries': ['python']})
 .reverse_depend('//third-party/boost:build')
 )
