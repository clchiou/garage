# This script is generated at {generated_at}

if [[ -n "$OPS_ENV" ]]; then
  echo "Another environment is active: $OPS_ENV"
  return
fi

deactivate() {{
  export PS1="$__LAST_PS1"
  unset __LAST_PS1

  unset ANSIBLE_PRIVATE_KEY_FILE
  unset ANSIBLE_INVENTORY

  unset OPS_ENV

  # Self destruct!
  unset -f deactivate
}}

export OPS_ENV="{env}"

export ANSIBLE_PRIVATE_KEY_FILE="{private_key}"
export ANSIBLE_INVENTORY="{inventory}"

export __LAST_PS1="$PS1"
export PS1="$PS1\[\033[01;31m\]{env}\[\033[00m\]: "
