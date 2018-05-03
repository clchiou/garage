"""Build V8 from source."""

from foreman import define_parameter, get_relpath, rule

from garage import scripts

from templates import common


# Find the current releases here: https://omahaproxy.appspot.com/
# In Chromium's DEPS file you may find V8's revision.
(define_parameter('revision')
 .with_doc('V8 revision.')
 .with_type(str)
 # Version 6.6.346.
 .with_default('d500271571b92cb18dcd7b15885b51e8f437d640'))


common.define_distro_packages([
    'g++',
    'libc6-dev',
    'libglib2.0-dev',
    'libicu-dev',
])


# Help //py/v8 find out where build artifacts are
(define_parameter.path_typed('output')
 .with_doc('Path to V8 build output directory.')
 .with_derive(
     lambda ps:
     ps['//base:drydock'] / get_relpath() /
     'out.gn' /
     ('x64.release' if ps['//base:release'] else 'x64.debug')
 )
)


LIBRARIES = [
    'libc++.so',
    'libicui18n.so',
    'libicuuc.so',
    'libv8_libbase.so',
    'libv8_libplatform.so',
    'libv8.so',
]


@rule
@rule.depend('//base:build')
@rule.depend('//host/depot_tools:install')
def fetch(parameters):
    """Fetch source repo."""
    drydock_src = parameters['//base:drydock'] / get_relpath()
    if not drydock_src.exists():
        scripts.mkdir(drydock_src.parent)
        with scripts.directory(drydock_src.parent):
            scripts.execute(['fetch', 'v8'])
            scripts.execute([
                'gclient',
                'sync',
                '--revision', parameters['revision'],
            ])


@rule
@rule.depend('fetch')
@rule.depend('install_packages')
def build(parameters):
    drydock_src = parameters['//base:drydock'] / get_relpath()
    output = parameters['output']
    if not (output / 'args.gn').exists():
        scripts.mkdir(output)
        if parameters['//base:release']:
            config = 'x64.release'
            # FIXME: Due to still unknown reasons, when combining
            # is_component_build=true and is_official_build=true in
            # x64.release build, `mksnapshot` will crash with signal 4
            # ILL_ILLOPN.  We will disable is_official_build for now.
            # (Alternatively, if I could make py/v8 be able to link to
            # v8 statically, we may drop is_component_build.)
            #official_build = 'is_official_build=true'
            official_build = 'is_official_build=false'
        else:
            config = 'x64.debug'
            official_build = 'is_official_build=false'
        with scripts.directory(drydock_src):
            scripts.execute([
                'tools/dev/v8gen.py',
                'gen',
                config,
                '--',
                'is_component_build=true',
                official_build,
            ])
            scripts.execute(['ninja', '-C', 'out.gn/%s' % config])
    with scripts.using_sudo(), scripts.directory(output):
        scripts.rsync(LIBRARIES, '/usr/local/lib')
        scripts.execute(['ldconfig'])


@rule
@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
def tapeout(_):
    # Nothing here as //base:tapeout will tapeout /usr/local/lib for us
    pass
