"""Build V8 from source."""

from foreman import define_parameter, get_relpath, rule

from garage import scripts

from templates import common


(define_parameter('version')
 .with_doc('V8 version.')
 .with_type(str)
 .with_default('5.9.61'))


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
     lambda ps: ps['//base:drydock'] / get_relpath() / 'out.gn/x64.release'))


ARGS_GN_FORMAT = '''\
allow_posix_link_time_opt = {release}
is_component_build = true
is_debug = false
is_official_build = {release}
target_cpu = "x64"
'''


LIBRARIES = [
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
        with scripts.directory(drydock_src):
            scripts.execute(['git', 'checkout', parameters['version']])
            scripts.execute(['gclient', 'sync'])


@rule
@rule.depend('fetch')
@rule.depend('install_packages')
def build(parameters):
    drydock_src = parameters['//base:drydock'] / get_relpath()
    output = drydock_src / 'out.gn/x64.release'
    if not (output / 'args.gn').exists():
        scripts.mkdir(output)
        #
        # TODO: Fix release build
        # 2017-03-23: I encountered two issues during release build:
        #
        # * LLVMgold.so was not downloaded by the build tool; I solved
        #   this by manually running:
        #   GYP_DEFINES='cfi_vptr=1' v8/gypfiles/download_gold_plugin.py
        #
        # * Build crashed when generating sanpshot_blob.bin with:
        #   python ../../tools/run.py ./mksnapshot --startup_src gen/snapshot.cc --random-seed 314159265 --startup_blob snapshot_blob.bin
        #
        #release = 'true' if parameters['//base:release'] else 'false'
        release = 'false'
        scripts.ensure_contents(
            output / 'args.gn', ARGS_GN_FORMAT.format(release=release))
        with scripts.directory(drydock_src):
            scripts.execute(['buildtools/linux64/gn',
                             'gen', 'out.gn/x64.release', '--check'])
            scripts.execute(['ninja', '-C', 'out.gn/x64.release'])
    with scripts.using_sudo(), scripts.directory(output):
        scripts.rsync(LIBRARIES, '/usr/local/lib')


@rule
@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    # Nothing here as //base:tapeout will tapeout /usr/local/lib for us
    pass
