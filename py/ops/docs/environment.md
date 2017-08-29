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

### Create a new environment

This example generates a staging-like environment.

* Generate basic skeleton and keys of an environment:
  ```
  ops-mob envs --root /path/to/ops gen staging
  cd /path/to/ops/envs/staging
  source scripts/env.sh
  ```
  This step generates:
  * SSH key (for logging into remote machines)
  * SSH host keys.
  * Easy RSA CA directory.
  * `env.sh`.

* Create symlink to pod release channel (this is for deploying pods with
  Ansible playbook):
  ```
  ln -s /path/to/ops/releases/channels/staging pods
  ```

* Configure OpenVPN server:
  * Edit `openvpn/cadir/vars`.
  * Generate credentials.
  * Run `ops-mob envs copy-server`.
  * We will generate OpenVPN client configuration later because TLS auth
    key is not generated yet - it will be generated at server.

### Create a new machine

* Prepare for creating new machine on your VPS provider; let's call this
  new machine `staging-001`.

  * Edit `cloud-init/staging-001-config.yaml`:
    ```
    ---

    # Relative path to the generated cloud-init config file.
    output: staging-001.yaml

    # Provide this section only if it is a local virtual machine.
    #local-vm:
    #  hostname: testbed-001
    #  network-interface: enp0s8
    #  ip-address: ...  # Set up
    ```

  * Generate cloud-init config file:
    ```
    ops-mob envs gen-user-data cloud-init/staging-001-config.yaml
    ```

* Now, create a new machine on your VPS provider; you will need:
  * `keys/current/id_ecdsa.pub`.
  * `cloud-init/staging-001.yaml`.

* Add the new machine's IP address to `/etc/hosts`.

* Add the new machine's IP address to `~/.ssh/config`:
  ```
  Host staging-001
      HostName ${IP_ADDRESS}
      User plumber
      IdentityFile /path/to/ops/envs/staging/keys/current/id_ecdsa
  ```

* Add the new machine to Ansible's `hosts` file:
  ```
  # Inventory of staging environment.

  [staging]
  staging-001
  ```

* Now, use your configuration management tool to provision the new
  machine; I assume that you are using Ansible:
  ```
  cd /path/to/your/ansible/playbook
  ansible-playbook staging.yaml
  ```

* Now, back to OpenVPN; we now have the TLS auth key, and may generate
  client configuration.  Let's call this client `laptop`.

  * Back to staging environment directory:
    ```
    cd /path/to/ops/envs/staging
    ```

  * Generate client key:
    ```
    cd openvpn/cadir
    source vars
    ./build-key laptop
    # Or use `./build-key-pass` with password.
    ops-mob envs copy-client laptop
    ```
    This generates `laptop.key` and `laptop.crt` and copies them to
    `openvpn/clients`.

  * Generate `laptop.ovpn` file:
    ```
    ops-mob envs make-ovpn staging-001.conf laptop
    ```

* That's it!
