Operations repository layout:

* `pods/...`
  + `active/<pod-label-and-version>` are pod operations directories.
    To reduce directory nested levels while keeping uniqueness among
    directory names, we combine pod label and version into the directory
    name.
  + `graveyard` is the directory of pod operations directories to be
    removed.
  + `tmp` is a scratchpad for preparing pod operations directory.
* `xars/...`
  + `active/<xar-name-and-version>` are XAR operations directories.
    (See `pod-label-and-version` above.)
  + `graveyard` is the directory of XAR operations directories to be
    removed.
  + `tmp` is a scratchpad for preparing XAR operations directory.

Pod operations directory layout:

* `metadata` is pod operations metadata (JSON-formatted).
* `volumes/<volume-name>` are directories of volume data.

XAR operations directory layout:

* `metadata` is XAR operations metadata (JSON-formatted).

For bundle layout, please refer to the pod directory layout specified in
[release doc](../../../../shipyard2/docs/release.md).
