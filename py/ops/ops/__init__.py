"""Operation tools."""

import argparse
import logging
import sys

from ops import (
    deps,
    pods,
    ports,
    utils,
    scripting,
)


logging.getLogger(__name__).addHandler(logging.NullHandler())


def main():
    """Driver of each entity's main function."""
    scripting.ensure_not_root()

    parser = argparse.ArgumentParser(prog='ops', description=__doc__)

    entity_parsers = parser.add_subparsers(help="""system entities""")
    # http://bugs.python.org/issue9253
    entity_parsers.dest = 'entity'
    entity_parsers.required = True

    (entity_parsers
     .add_parser('deps', help="""external dependencies""")
     .set_defaults(entity=deps.main)
    )
    (entity_parsers
     .add_parser('pods', help="""application pods""")
     .set_defaults(entity=pods.main)
    )
    (entity_parsers
     .add_parser('ports', help="""network ports""")
     .set_defaults(entity=ports.main)
    )
    (entity_parsers
     .add_parser('utils', help="""non-locking utilities""")
     .set_defaults(entity=utils.main)
    )

    args = parser.parse_args(sys.argv[1:2])

    sys.exit(args.entity(sys.argv[1:]))
