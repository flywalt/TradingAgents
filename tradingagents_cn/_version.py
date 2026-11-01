"""Single source of the downstream version string.

Kept in its own module so ``config`` and ``__init__`` can both import it without
a cycle: the version must reach the run config (checkpoint identity, report
metadata), and the package initialiser must not depend on the config layer.
"""

VERSION = "0.1.0.dev0"
