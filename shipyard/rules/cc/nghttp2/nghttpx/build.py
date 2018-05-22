from foreman import rule

from templates.utils import tapeout_files


@rule
@rule.depend('//cc/nghttp2:build')
def build(_):
    pass  # Nothing here.


@rule
@rule.depend('build')
@rule.depend('//cc/nghttp2:tapeout')
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    tapeout_files(parameters, ['/usr/local/bin/nghttpx'])
