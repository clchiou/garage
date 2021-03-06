"""Meta build rules."""

import foreman

(foreman.define_rule('all').with_doc('build everything')\
 .depend('//py/g1/apps:build')
 .depend('//py/g1/asyncs/agents:build')
 .depend('//py/g1/asyncs/bases:build')
 .depend('//py/g1/asyncs/kernels:build')
 .depend('//py/g1/backgrounds:build')
 .depend('//py/g1/bases:build')
 .depend('//py/g1/containers:build')
 .depend('//py/g1/databases:build')
 .depend('//py/g1/devtools/buildtools:build')
 .depend('//py/g1/files:build')
 .depend('//py/g1/http/clients:build')
 .depend('//py/g1/http/http1_servers:build')
 .depend('//py/g1/http/http2_servers:build')
 .depend('//py/g1/messaging:build')
 .depend('//py/g1/networks/servers:build')
 .depend('//py/g1/operations/cores:build')
 .depend('//py/g1/operations/databases/bases:build')
 .depend('//py/g1/operations/databases/clients:build')
 .depend('//py/g1/operations/databases/servers:build')
 .depend('//py/g1/operations/databases/subscribers:build')
 .depend('//py/g1/scripts:build')
 .depend('//py/g1/texts:build')
 .depend('//py/g1/third-party/capnp:build')
 .depend('//py/g1/third-party/nng:build')
 .depend('//py/g1/third-party/v8:build')
 .depend('//py/g1/threads:build')
 .depend('//py/g1/webs:build')
 .depend('//py/startup:build')
 .depend('third-party')
 )

(foreman.define_rule('third-party').with_doc('build third-party codes')\
 .depend('//third-party/cpython:build').depend('//third-party/cpython:trim')
 .depend('//third-party/gradle:build')
 .depend('//third-party/nodejs:build')
 .depend('//third-party/openjdk:build')
 # C++ libraries.
 .depend('config-boost').depend('//third-party/boost:build')
 .depend('//third-party/capnproto:build')
 .depend('//third-party/capnproto-java:build')
 .depend('//third-party/depot_tools:build')
 .depend('//third-party/nghttp2:build')
 .depend('//third-party/nng:build')
 .depend('//third-party/v8:build')
 # Third-party Python packages.
 .depend('//third-party/lxml:build')
 .depend('//third-party/mako:build')
 .depend('//third-party/pyyaml:build')
 .depend('//third-party/requests:build')
 .depend('//third-party/sqlalchemy:build')
 .depend('//third-party/zstandard:build')
 )

# In addition to set `boost:libraries` parameter, `config-boost` also
# imposes ordering between boost:config and boost:build (the former is
# run before the latter).
(foreman.define_rule('config-boost')\
 .depend('//third-party/boost:config',
         parameters={'//third-party/boost:libraries': ['python']})
 .reverse_depend('//third-party/boost:build')
 )
