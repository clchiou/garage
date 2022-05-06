### Create a new machine

(TODO: `ops-mob` is deprecated; we should implement its replacement.)

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

* (Optional) Add the new machine's IP address to `/etc/hosts`.

* Add the new machine's IP address to `~/.ssh/config`:
  ```
  Host staging-001
      HostName ${IP_ADDRESS}
      User plumber
      IdentityFile /path/to/ops/envs/staging/keys/current/id_ecdsa
  ```

* Add machine's public and private IP address to Ansible's inventory.

* Add the new machine to Ansible's `hosts.yaml` file:
  ```
  # Inventory of staging environment.
  all:
    hosts:
      staging-001:
    children:
      staging:
        hosts:
          staging-001:
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
