from foreman import define_parameter, define_rule, get_relpath


if __name__ != 'pkg1.pkg2':
    raise AssertionError('incorrect __name__: %s' % __name__)


if not __file__.endswith('tests/testdata/path1/pkg1/pkg2/build.py'):
    raise AssertionError('incorrect __file__: %s' % __file__)


if str(get_relpath()) != 'pkg1/pkg2':
    raise AssertionError('incorrect relpath: %s' % get_relpath())


COUNT = 0
if COUNT > 0:
    raise AssertionError('load more than once')
COUNT += 1


define_parameter('par_x')


define_rule('rule_x').depend('//pkg1:pkg1')
