from foreman import define_rule


COUNT = 0
if COUNT > 0:
    raise AssertionError('load more than once')
COUNT += 1


# This creates a circular dependency!
define_rule('rule_y').depend('//pkg1/pkg2:rule_x')
