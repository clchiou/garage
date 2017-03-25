## Pods

Containers are deployed in a tightly-coupled group called "pod".  A pod
is described by ops tool -specific metadata and an "abstract" Appc pod
manifest, which ops will insert "realized" deployment-time data into.
The deployment-time includes, for example, filesystem path of volumes
and allocated port numbers.

Here is an example of the pod description:

    {
        # Required.
        "name": "example-pod",

        # Required, integer or string.
        "version": 1001,

        # Optional: Series of systemd units.
        "systemd-units": [
            {
                # Required: Location of the unit file, either a path or
                # an URI.
                "unit-file": "path/to/unit-file",

                # Optional: Location of signature, either path or URI.
                "signature": "path/to/unit-file.asc",

                # Optional: Instances of a templated unit, which could
                # be either as an array or as the number of instances.
                "instances": [8080, 8081, 8082],
            },
            ...
        ],

        # Optional: Series of image locations.
        "images": [
            {
                # Required: Image ID.
                # https://github.com/appc/spec/blob/master/spec/types.md#image-id-type
                "id": "sha512-XXX",

                # Required: Location of the image file, either a path or
                # an URI.
                "image": "path/to/image.aci",

                # Optional: Location of signature, either path or URI.
                "signature": "path/to/image.aci.asc",
            },
            ...
        ],

        # Optional: Series of stateful volumes.
        #
        # Each volume entry here must have a corresponding host-kind
        # volume entry in the pod manifest of which "source" attribute
        # must not be set and will be inserted by ops tool.
        #
        # They are _NOT_ shared across versions of pod, though; if you
        # want to share stateful data across versions of pod, you
        # probably should use things like RDBMS.
        "volumes": [
            {
                # Required.
                "name": "volume-name",

                # Optional: Default to "nobody" and "nogroup".
                "user": "root",
                "group": "root",

                # Optional: Initial contents of the volume, which could
                # be either path or URI.
                "data": "path/to/data.tar.gz",

                # Optional: Location of signature, either path or URI.
                "signature": "path/to/data.tar.gz.asc",
            },
            ...
        ],

        # Required: The "abstract" Appc pod manifest.
        "manifest": {
            "acVersion": "0.8.10",
            "acKind": "PodManifest",
            ...
        }
    }
