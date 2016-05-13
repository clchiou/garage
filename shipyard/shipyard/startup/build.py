"""Build startup."""

from pathlib import Path

from foreman import define_parameter, define_rule
from shipyard import (
    python_copy_and_build_package,
    python_copy_package,
)


(define_parameter('src')
 .with_doc("""Location of the startup source repo.""")
 .with_type(Path)
 .with_default(Path.home() / 'startup')
)


(define_rule('build')
 .with_doc(__doc__)
 .with_build(lambda ps: \
     python_copy_and_build_package(ps, 'startup', src=ps['src']))
 .depend('//base:build')
 .depend('//cpython:build')
)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: python_copy_package(ps, 'startup'))
 .depend('build')
 .reverse_depend('//base:tapeout')
 .reverse_depend('//cpython:tapeout')
)
