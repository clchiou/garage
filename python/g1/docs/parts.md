### Parts

Basically we want a way to:

* Declare parts of a program in the dependent packages.
* Create and assemble parts in the main program.
* Parts can be nested.

We have iterated through a few designs.  The current design is called
**parts**.  It is merely a convention on top of `startup` plus some
helper libraries (this "convention approach" is more flexible than the
"framework approach" that we migrated away from).

In each dependent package, create a module named `parts` (more on this
`parts` module below), in which you declare parts.  You usually do not
create part instances there.

In the main program, create and assemble part instances.  It may create
multiple part instances per part declaration.

Parts are best for creating a static hierarchy of parts during program
startup.  By "static" we mean that the number of part instances is not a
variable on program input.

#### Parts module

Parts modules generally follows the convention below.  To declare a part
X, you would do these:

* Define a list of strings `X_LABEL_NAMES`.  These names will be used
  for constructing labels of a part instance.  You usually add these
  names to the list:

  * `X`, which refers to the part instance you are going to create.
  * `X_params`, which refers to the parameter namespace for creating
    this instance.
  * Dependent part names.

  Also:

  * In more complex parts modules, `X_LABEL_NAMES` may actually be a
    tree rather than a list of strings.
  * For documentation, you may organize names of `X_LABEL_NAMES` into
    "Input", "Output", and "Private" sections.

* Define a function `make_X_params` that creates parameter namespace of
  a part instance.

* Define a function `make_X` that creates a part instance.  It usually
  takes a parameter namespace created by `make_X_params` as input.

* Define a function `setup_X` that takes labels and parameter namespace
  of a part instance as input, and adds them to the `startup` dependency
  graph.

* Optionally, define a helper function named `define_X` that combines
  the above.

* Declare an "extras" entry named `parts` in `setup.py` for the parts'
  dependencies, such as other parts and the helper libraries.

#### Composition of parts

The simplest method of composing parts is to fully "embed" one part
inside another part.  Using this method, the embedded part will usually
appear in the "Private" section of the embedding part.

Another method is to define two parts separately, and then bind the
output labels of one part to the input labels of another.
