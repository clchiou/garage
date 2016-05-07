from foreman import define_parameter, define_rule


COUNT = 0
if COUNT > 0:
    raise AssertionError('load more than once')
COUNT += 1


define_parameter('par_x')


define_rule('rule_x')
