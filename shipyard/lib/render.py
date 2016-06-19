"""Render a Mako template."""

import argparse
import sys

from mako.lookup import TemplateLookup


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--output', required=True,
        help="""set output path (default to stdout)""")
    parser.add_argument(
        '--dir', action='append', default=('.',),
        help="""add directory for looking up Mako templates""")
    parser.add_argument(
        '--var', metavar='NAME=VALUE', action='append',
        help="""add a variable value.""")
    parser.add_argument('template', help="""set Mako template to render""")
    args = parser.parse_args(argv[1:])

    template_vars = {}
    for pair in args.var or ():
        name, value = pair.split('=', 1)
        template_vars[name] = value

    templates = TemplateLookup(
        directories=args.dir,
        strict_undefined=True,
        input_encoding='utf-8',
        output_encoding='utf-8',
        encoding_errors='replace',
    )

    contents = templates.get_template(args.template).render(**template_vars)

    with open(args.output, 'wb') as output_file:
        output_file.write(contents)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
