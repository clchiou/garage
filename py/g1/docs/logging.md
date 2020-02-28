### Logging

These rules are **not absolute**, but just rules of thumb.

* A log message should stand by itself; you do not have to scroll up and
  down for its context.

* Generally, log at INFO level to record application progress.  However,
  for request handling library codes, log at DEBUG level to prevent INFO
  log messages growing at `O(number of request)` scale (but application
  codes can still log at INFO level).

* When an error happens:

  * If the program can reasonably proceed, it could log it and carry on;
    otherwise, raise (or re-raise) an exception (note that in this case,
    the error should not be logged to avoid double logging).

  * If immediate human action is required to mitigate or fix the error,
    log at ERROR level; otherwise, log at WARNING level.

  * However, if this error is expected to happen, such as invalid user
    input, log at DEBUG level, or even not log it at all.

  * When in doubt, log at ERROR level since you can always lower the
    level to WARNING or DEBUG later.

* While stack trace from an exception is very useful, there are some
  cases that I think you might not want to log them:

  * When your try-block only encloses a call to a third-party library.
    In this case the stack trace is entirely in the library's code.
    Unless you want to debug the library, this trace might not be very
    useful.

  * When an error is expected and/or well-known, such as invalid user
    input or HTTP status 4xx/5xx, stack traces might not be useful or
    give you much new information.
