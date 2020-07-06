For each pod, key space under `/service/<pod-label>/<pod-id>` is
assigned to the pod.  A pod may read from, write to, or subscribe to
keys of this key space.

Note that operations database keys are a part of the public interface,
and so they should be documented and versioned; e.g., `v1/...` for all
v1 keys.
