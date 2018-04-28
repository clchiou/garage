## Version of all packages

Currently we have build files for these packages:

```
                    C   P   PE  CY  J   JS  REV
first party
  capnp                     x
  garage                x
  http2                 x
  imagetools                x
  nanomsg               x
  startup               x
  v8                            x

first party host tools
  buildtools            x

thrid party
  boost             x                       1.67.0
  capnproto         x                       v0.6.1
  cpython           x                       3.7.0b3
  curio                 x                   0.7
  envoy             x                       f8dbb065177e61d3b6fc74eda59c59732b07dfbd (not far from v1.4.0)
  libjpeg-turbo     x                       version bundled with distro
  lxml                      x               3.7.3
  mako                  x                   1.0.6
    markupsafe          x
  nanomsg           x                       b7fd165c20f2fa86192a19e3db2bed46bfadd025 (not far from 1.0.0)
  nghttp2           x                       v1.20.0
  pyyaml                    x               3.12
  requests              x                   2.13.0
  sqlalchemy                x               1.1.6
  v8                x                       5.9.61

thrid party host tools
  capnproto-java                    x       v0.1.2
  cython                        x           0.28.2
  depot_tools           x                   master
  node              x                       4.2.6 (distributed with Ubuntu 16.10)
    npm                                 x   3.5.2

C  = C/C++

P  = Pure Python (maybe use ctypes)
PE = Python + extension module
CY = Cython

J  = Java

JS = JavaScript
```
