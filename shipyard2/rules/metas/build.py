"""Meta build rules."""

import foreman

(foreman.define_rule('all').with_doc('build everything')\
 .depend('//python/g1/apps:build')
 .depend('//python/g1/asyncs/agents:build')
 .depend('//python/g1/asyncs/bases:build')
 .depend('//python/g1/asyncs/kernels:build')
 .depend('//python/g1/backgrounds:build')
 .depend('//python/g1/bases:build')
 .depend('//python/g1/containers:build')
 .depend('//python/g1/databases:build')
 .depend('//python/g1/devtools/buildtools:build')
 .depend('//python/g1/files:build')
 .depend('//python/g1/http/clients:build')
 .depend('//python/g1/http/http1_servers:build')
 # TODO: Re-enable this after nghttp2 below is re-enabled.
 #.depend('//python/g1/http/http2_servers:build')
 .depend('//python/g1/messaging:build')
 .depend('//python/g1/networks/servers:build')
 .depend('//python/g1/operations/cores:build')
 .depend('//python/g1/operations/databases/bases:build')
 .depend('//python/g1/operations/databases/clients:build')
 .depend('//python/g1/operations/databases/servers:build')
 .depend('//python/g1/operations/databases/subscribers:build')
 .depend('//python/g1/scripts:build')
 .depend('//python/g1/texts:build')
 .depend('//python/g1/third-party/capnp:build')
 .depend('//python/g1/third-party/nng:build')
 .depend('//python/g1/third-party/v8:build')
 .depend('//python/g1/threads:build')
 .depend('//python/g1/webs:build')
 .depend('//python/startup:build')
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
 # TODO: It appears that ax_python_devel.m4 of nghttp2 cannot detect
 # Python 3.10; so we disable this for now.
 #.depend('//third-party/nghttp2:build')
 .depend('//third-party/nng:build')
 .depend('//third-party/v8:build')
 # Third-party Python packages.
 .depend('//third-party/lxml:build')
 .depend('//third-party/mako:build')
 .depend('//third-party/numpy:build')
 .depend('//third-party/pandas:build')
 .depend('//third-party/pyyaml:build')
 .depend('//third-party/requests:build')
 .depend('//third-party/sqlalchemy:build')
 .depend('//third-party/wand:build')
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

# NOTE: ``austerity`` removes most of the local repositories to free up
# disk space.  After austerity you cannot build from them.  (So we only
# add austerity to a few big ones.)
(foreman.define_rule('austerity').with_doc('free up disk space drastically')\
 .depend('//bases:cleanup')
 .depend('//third-party/boost:austerity')
 .depend('//third-party/cpython:austerity')
 .depend('//third-party/v8:austerity')
 )
