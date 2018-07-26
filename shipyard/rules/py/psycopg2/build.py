from templates import common, py


common.define_git_repo(
    repo='https://github.com/psycopg/psycopg2.git',
    treeish='2_7_5',
)


common.define_distro_packages(['libpq-dev'])


rules = py.define_source_package(package='psycopg2')
rules.build.depend('git_clone')
rules.build.depend('install_packages')
