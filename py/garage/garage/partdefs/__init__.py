"""Part definitions.

As a convention, every garage.<module> (called source module) may have a
corresponding garage.partdefs.<module> that defines the parts that the
source module provides.

We prefer part definitions to be out of source modules because it seems
to be desirable that source module is not dependent on garage.parts.

There are generally two kinds of part definition module:

  * The straightforward kind that defines the part list and a default
    part maker, which you may override with your own.  These modules
    generally just expose a part list, conventionally named `PARTS`.
    They are good for globally unique parts, such as the `exit_stack`.

  * The template kind that lets you dynamically create part definition.
    Each module that instantiates the template generally receives a part
    list and a parameter namespace, which are nested inside module's own
    part list and parameter namespace.
"""
