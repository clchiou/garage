### Logging

These rules are not absolute, but just rules of thumb.

* Generally, log at INFO level to record application progress.  However,
  for request handling library codes, log at DEBUG level to prevent INFO
  log messages growing at `O(number of request)` scale (but application
  codes can still log at INFO level).

* When something goes wrong, log at ERROR level to prompt immediate
  human action; otherwise log at WARNING level.  When in doubt, log at
  ERROR level since you can always lower the level to WARNING later.
