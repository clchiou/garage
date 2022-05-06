Here are tokens that we should define when we are provisioning a new
machine, and so pods may assume these tokens are always available.
These tokens are named with prefix `ops_`.  Be careful not to conflict
with [environment variables](./ops-envs.md).

* `ops_free_port` is a range token of free port numbers that can be
  assigned to pods.  Generally the range is `[30000, 32768)`, but you
  should check `/proc/sys/net/ipv4/ip_local_port_range` before defining
  this token to avoid conflicting with ephemeral port range.
