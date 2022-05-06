Operations tools, servers, etc.

* `cores` provides the core functionalities of operations.  Side note:
  Since it is also responsible for installing itself to the operations
  repository, to make this bootstrap easier, it is built as a zipapp.
  As a result, `cores` (and its dependencies) must be pure Python code.
  We could switch to other release format (say, XAR) later if we need
  core features that are impossible to implement in pure Python.
