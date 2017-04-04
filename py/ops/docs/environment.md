## Environment

We loosely mention "environment" in documents without formally defining
what it is; I can't come up with a good one but I can list how I use the
term "environment" in various contexts:

* When talking about machines, an "environment" is a group of machines,
  and it is usually a broad group, like production or staging, that will
  be further divided into smaller groups, like frontends and backends.

* An environment has its own set of "high value" files, such as SSH keys
  or server configurations (and this is why an environment is usually a
  broad group: generating these "high value" files for a small number of
  machines is usually not worth the effort).

* When I say I am "using" or "switching" an environment, I mean I am
  using or switching those sets of files.

An environment directory may contain not just one but a few variants of
environment (although at the moment I don't have such use case).

### Environment directory structure convention

I define a directory structure convention for environments so that I
don't need to provide all file paths to scripts, and instead scripts may
assume the paths under an environment directory.

* `cloud-init/...`: cloud-init user data
* `host`: Ansible inventory file
* `keys`: SSH keys
  * `keys/current`: symlink to the keys directory
  * `keys/YYYYMM`: keys directory
* `openvpn/...`: OpenVPN credentials
  * `openvpn/cadir`: easy-rsa working directory
  * `openvpn/clients`: (generated) client credentials
  * `openvpn/servers`: (generated) server credentials
* `scripts/env.sh`: set up the environment
* `pods/...`: deployment bundles of pods

### User data configuration file

The `envs gen-user-data` command reads a configuration file to generate
a user data file.  The configuration file format is like this:

    # Required: Output file name of user data
    output: name.yaml

    # Optional: Configure local virtual machine
    local-vm:
      hostname: ...
      network-interface: ...  # Host-only network interface
      ip-address: ...
