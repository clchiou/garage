For each pod, key space under `/service/<pod-label>/<pod-id>` is
assigned to the pod.  Extra `/` in the pod label is removed, and the `:`
in pod label is replaced by `/`.

A pod may read from, write to, or subscribe to keys of this key space.

Note that operations database keys are a part of the public interface,
and so they should be documented and versioned; e.g., `v1/...` for all
v1 keys.

To avoid ambiguity, key space and keys within the key space should be
joined by `:`, i.e., the final key should look like:
`/service/<pod-label>/<pod-id>:v1/...`.
