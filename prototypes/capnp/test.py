import traceback

import extension


def func():
    pass


boom = extension.Boom()
try:
    # Call Boom's dtor.  You expect to get an exception here, but...
    del boom

    # You will actually get the exception until next statement (or
    # PyEval_EvalFrameEx, to be exact), which is very confusing.
    # Furthermore, it's not RuntimeError you expected, but SystemError.
    func()
except SystemError:
    traceback.print_exc()
else:
    raise AssertionError('`del boom` did not raise')
