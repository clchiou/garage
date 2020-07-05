Here are environment variables that we should define when we are
provisioning a new machine.  These environment variables are named with
prefix `ops_`.  Be careful not to conflict with
[tokens](./ops-tokens.md).

* `ops_public_address` is the public IP address of the machine.
* `ops_private_address` is the private IP address of the machine.

* `ops_database_url` is the URL to the operations database server.
* `ops_database_event_url` is the URL to the operations database server
  event publisher.
