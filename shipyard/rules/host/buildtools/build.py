from foreman import get_relpath, rule

from garage import scripts

from templates import common


common.define_copy_src(src_relpath='py/buildtools')


@rule
@rule.depend('//base:build')
@rule.depend('copy_src')
def install(parameters):
    drydock_src = parameters['//base:drydock'] / get_relpath()
    scripts.ensure_file(drydock_src / 'setup.py')  # Sanity check
    scripts.insert_path(drydock_src, var='PYTHONPATH')
