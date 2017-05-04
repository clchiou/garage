import unittest

from tests.availability import startup_available

if startup_available:
    from startup import Startup
    from garage import components

# Import everything under garage.startups
module_available = True
try:
    # XXX: You will have import error inside `requests` package if you
    # run this unit test with `python3 tests/test_startups.py`, but you
    # will be fine if you run it with `python3 -m unittest`.
    import garage.startups.asyncs.servers
    import garage.startups.formatters
    import garage.startups.http.clients
    import garage.startups.logging
    import garage.startups.metry
    import garage.startups.metry.reporters.logging
    import garage.startups.multiprocessing
    import garage.startups.spiders
    import garage.startups.sql
    import garage.startups.threads.executors
    import garage.startups.v8
except ImportError as e:
    module_available = False


@unittest.skipUnless(startup_available, 'startup unavailable')
@unittest.skipUnless(module_available , 'not all modules are unavailable')
class StartupsTest(unittest.TestCase):

    @staticmethod
    def iter_comp_classes(modules):
        for module in modules:
            for comp_class in vars(module).values():
                if (isinstance(comp_class, type) and
                        issubclass(comp_class, components.Component)):
                    yield comp_class

    def test_all_components(self):
        """Smoke test all components."""
        modules = (
            garage.startups.asyncs.servers,
            garage.startups.formatters,
            garage.startups.http.clients,
            garage.startups.logging,
            garage.startups.metry,
            garage.startups.metry.reporters.logging,
            garage.startups.multiprocessing,
            garage.startups.spiders,
            garage.startups.sql,
            garage.startups.threads.executors,
            garage.startups.v8,
        )

        # Find components by class
        comps1 = components.find_closure(
            *self.iter_comp_classes(modules),
            # White list components that user has to provide
            ignore=tuple(map(
                components.Fqname.parse,
                (
                    'garage.startups.asyncs.servers:make_server',
                    'garage.startups.spiders:spider_parser',
                ),
            )),
        )
        self.assertNotEqual(0, len(comps1))

        # Find components by instance
        comps2 = components.find_closure(
            *(
                comp_class()
                for comp_class in self.iter_comp_classes(modules)
            ),
            # White list components that user has to provide
            ignore=tuple(map(
                components.Fqname.parse,
                (
                    'garage.startups.asyncs.servers:make_server',
                    'garage.startups.spiders:spider_parser',
                ),
            )),
        )
        self.assertNotEqual(0, len(comps2))

        self.assertEqual(len(comps1), len(comps2))

        # Bind all components by class
        startup = Startup()
        for comp_class in self.iter_comp_classes(modules):
            components.bind(comp_class, startup)

        # Bind all components by instance
        startup = Startup()
        for comp_class in self.iter_comp_classes(modules):
            components.bind(comp_class(), startup)


if __name__ == '__main__':
    unittest.main()
