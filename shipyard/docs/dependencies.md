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

base system
  ubuntu                                    18.04

thrid party
  boost             x                       1.67.0
  capnproto         x                       v0.6.1
  cpython           x                       3.7.0b3
  curio                 x                   0.7
  jdk                               x       8u172
  libjpeg-turbo     x                       version bundled with distro
  lxml                      x               4.2.1
  mako                  x                   1.0.7
    markupsafe          x
  nanomsg           x                       1.1.2
  nghttp2           x                       v1.31.1
  pyyaml                    x               b6cbfeec35e019734263a8f4e6a3340e94fe0a4f (recent master that supports python 3.7)
  requests              x                   2.18.4
    chardet
    idna
    urllib3
    certifi
  sqlalchemy                x               1.2.7
  v8                x                       6.6.346 (revision d500271571b92cb18dcd7b15885b51e8f437d640)
  wand                      x               0.4.4

thrid party host tools
  capnproto-java                    x       v0.1.2
  cython                        x           0.28.2
  depot_tools           x                   master
  gradle                            x       4.7
  node              x                       version bundled with distro
    npm                                 x

C  = C/C++

P  = Pure Python (maybe use ctypes)
PE = Python + extension module
CY = Cython

J  = Java

JS = JavaScript
```
