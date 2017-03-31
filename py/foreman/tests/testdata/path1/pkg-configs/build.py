from foreman import REMOVE, define_parameter, define_rule


COUNT = 0
if COUNT > 0:
    raise AssertionError('load more than once')
COUNT += 1


define_parameter('x').with_default(0)


define_parameter('executed_rules').with_default([])


(define_rule('rule-A')
 .depend('rule-B', configs={'x': 1})
 .depend('rule-C', configs={'x': 2})
 .with_build(lambda ps: ps['executed_rules'].append(('rule-A', ps)))
)


(define_rule('rule-B')
 .depend('rule-D')
 .depend('rule-E')
 .with_build(lambda ps: ps['executed_rules'].append(('rule-B', ps)))
)


(define_rule('rule-C')
 .depend('rule-D')
 .depend('rule-F')
 .depend('rule-G', configs=REMOVE)
 .with_build(lambda ps: ps['executed_rules'].append(('rule-C', ps)))
)


(define_rule('rule-D')
 .with_build(lambda ps: ps['executed_rules'].append(('rule-D', ps)))
)
(define_rule('rule-E')
 .with_build(lambda ps: ps['executed_rules'].append(('rule-E', ps)))
)
(define_rule('rule-F')
 .with_build(lambda ps: ps['executed_rules'].append(('rule-F', ps)))
)
(define_rule('rule-G')
 .with_build(lambda ps: ps['executed_rules'].append(('rule-G', ps)))
)
