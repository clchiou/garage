from pathlib import Path
import json

from foreman import REMOVE, define_parameter, get_relpath, rule

from garage import scripts

from templates import common


(define_parameter
 .list_typed('libraries')
 .with_doc('Select Boost libraries that you want to build.'))


common.define_archive(
    uri='https://sourceforge.net/projects/boost/files/boost/1.63.0/boost_1_63_0.tar.bz2/download',
    filename='boost_1_63_0.tar.bz2',
    output='boost_1_63_0',
    checksum='md5-1c837ecd990bb022d07e7aab32b09847',
)


common.define_distro_packages(['g++', 'libstdc++-6-dev'])


@rule
@rule.depend('//base:build', configs=REMOVE)
@rule.depend(
    '//py/cpython:build',
    when=lambda ps: 'python' in (ps['libraries'] or ()),
    configs=REMOVE,
)
# This is a strange self-reverse-depend trick
@rule.reverse_depend('config', configs=REMOVE)
def config(parameters):
    """Configure Boost build."""

    drydock = parameters['//base:drydock'] / get_relpath()
    scripts.mkdir(drydock)

    config_path = drydock / 'config.json'
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {}

    more_libraries = parameters['libraries']
    if not more_libraries:
        return

    libraries = sorted(config.get('libraries', ()))
    new_libraries = sorted(set(libraries).union(more_libraries))
    if new_libraries != libraries:
        config['libraries'] = new_libraries
        scripts.ensure_contents(config_path, json.dumps(config))


@rule
@rule.depend('//base:build')
@rule.depend('config')
@rule.depend('download')
@rule.depend('install_packages')
def build(parameters):
    """Build Boost from source."""

    drydock = parameters['//base:drydock'] / get_relpath()

    config_path = drydock / 'config.json'
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {}

    libraries = config.get('libraries')
    if not libraries:
        raise RuntimeError('no libraries to build')

    drydock_src = drydock / parameters['archive_info'].output
    with scripts.directory(drydock_src):

        if not (drydock_src / 'stage').exists():

            bootstrap = [
                './bootstrap.sh',
                '--with-libraries=%s' % ','.join(libraries),
            ]
            if 'python' in libraries:
                bootstrap.append(
                    '--with-python=%s' % parameters['//py/cpython:python'])
            if parameters['//base:release']:
                bootstrap.append('variant=release')
            else:
                bootstrap.append('variant=debug')
            bootstrap.append('link=shared')
            bootstrap.append('threading=multi')

            scripts.execute(bootstrap)
            scripts.execute(['./b2', 'stage'])

        if not Path('/usr/local/include/boost').exists():
            with scripts.using_sudo():
                scripts.execute(['./b2', 'install'])


@rule
@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    """Copy build artifacts."""
    # Nothing here as //base:tapeout will tapeout /usr/local/lib for us
    pass
