"""Build (standard) Elasticsearch image.

Elasticsearch requires lots of configurations to function efficiently;
this "standard" image might not be effective most of the time, but it is
probably a good starting point.
"""

from foreman import define_parameter, get_relpath, rule

from garage import scripts

from templates import common, pods


common.define_archive(
    uri='https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-5.6.3.tar.gz',
    filename='elasticsearch-5.6.3.tar.gz',
    output='elasticsearch-5.6.3',
    checksum='md5-8dd1558d3535705d20a5129cac30ce5a',
)


@rule
@rule.depend('//base:build')
@rule.depend('//java/java:build')
@rule.depend('download')
def build(parameters):
    pass  # Nothing here for now.


@rule
@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
@rule.reverse_depend('//java/java:tapeout')
def tapeout(parameters):
    with scripts.using_sudo():
        input = (
            parameters['//base:drydock'] / get_relpath() /
            parameters['archive_info'].output
        )

        output = parameters['//base:drydock/rootfs'] / 'opt/elasticsearch'
        scripts.mkdir(output)

        # Elasticsearch requires an (though empty) `bin` directory (this
        # is a part of its bootstrap check).
        scripts.mkdir(output / 'bin')

        # `config`, `data`, and `logs` are provided by application pod.
        scripts.mkdir(output / 'config')
        scripts.mkdir(output / 'data')
        scripts.mkdir(output / 'logs')

        # Copy `lib`, `modules`, and `plugins`.
        scripts.rsync(
            [
                input / 'lib',
                input / 'modules',
                input / 'plugins',
            ],
            output,
        )


(define_parameter('jvm_heap_size')
 .with_doc('set JVM heap size for Elasticsearch.')
 .with_default('2g'))


@pods.app_specifier
def elasticsearch_app(parameters):
    # TODO: Should we define `ELASTIC_CONTAINER=true`?
    # TODO: Should we set `es.cgroups.hierarchy.override=/`?
    return pods.App(
        name='elasticsearch',
        exec=[
            str(parameters['//java/java:jre'] / 'bin/java'),

            #
            # NOTE: The JVM configuration below are derived from
            # elasticsearch/config/jvm.options.
            #

            # Set JVM heap size.
            '-Xms%s' % parameters['jvm_heap_size'],
            '-Xmx%s' % parameters['jvm_heap_size'],

            # Configure GC.
            '-XX:+UseConcMarkSweepGC',
            '-XX:CMSInitiatingOccupancyFraction=75',
            '-XX:+UseCMSInitiatingOccupancyOnly',

            # Pre-touch memory pages used by the JVM during
            # initialization.
            '-XX:+AlwaysPreTouch',

            # Force the server VM (remove on 32-bit client JVMs).
            '-server',

            # Explicitly set the stack size (reduce to 320k on 32-bit
            # client JVMs).
            '-Xss1m',

            # Set to headless, just in case.
            '-Djava.awt.headless=true',

            # Ensure UTF-8 encoding by default (e.g. filenames).
            '-Dfile.encoding=UTF-8',

            # Use our provided JNA always versus the system one.
            '-Djna.nosys=true',

            # Use old-style file permissions on JDK9.
            '-Djdk.io.permissionsUseCanonicalPath=true',

            # Configure Netty.
            '-Dio.netty.noUnsafe=true',
            '-Dio.netty.noKeySetOptimization=true',
            '-Dio.netty.recycler.maxCapacityPerThread=0',

            # Configure log4j 2.
            '-Dlog4j.shutdownHookEnabled=false',
            '-Dlog4j2.disable.jmx=true',
            '-Dlog4j.skipJansi=true',

            # Generate heap dump on allocation failures.
            '-XX:+HeapDumpOnOutOfMemoryError',
            '-XX:HeapDumpPath=/tmp',

            # Configure Elasticsearch.
            '-Des.path.home=/opt/elasticsearch',

            # JVM accepts wildcard notation in classpaths.
            '-classpath', '/opt/elasticsearch/lib/*',

            'org.elasticsearch.bootstrap.Elasticsearch',
        ],
        working_directory='/opt/elasticsearch',
        volumes=[
            pods.Volume(
                name='config-volume',
                path='/opt/elasticsearch/config',
                data='config-volume/config.tar.gz',
            ),
            pods.Volume(
                name='data-volume',
                path='/opt/elasticsearch/data',
                read_only=False,
            ),
            pods.Volume(
                name='logs-volume',
                path='/opt/elasticsearch/logs',
                read_only=False,
            ),
        ],
        ports=[
            pods.Port(
                name='restful',
                protocol='tcp',
                port=9200,
                host_port=9200,
            ),
            pods.Port(
                name='native',
                protocol='tcp',
                port=9300,
                host_port=9300,
            ),
        ],
        # Work around a Elasticsearch bug prior to v5.6.4.
        # https://github.com/rkt/rkt/issues/3121
        # https://github.com/elastic/elasticsearch/issues/20179
        extra_app_entry_fields={
            'isolators': [
                {
                    'name': 'os/linux/seccomp-retain-set',
                    'value': {
                        'set': [
                            '@rkt/default-whitelist',
                        ],
                        'errno': 'ENOSYS',
                    },
                },
            ],
        },
    )


@pods.image_specifier
def elasticsearch_image(parameters):
    return pods.Image(
        name='elasticsearch',
        app=parameters['elasticsearch_app'],
    )


elasticsearch_image.specify_image.depend('elasticsearch_app/specify_app')


elasticsearch_image.write_manifest.depend('//base:tapeout')
elasticsearch_image.write_manifest.depend('//java/java:tapeout')
elasticsearch_image.write_manifest.depend('tapeout')
