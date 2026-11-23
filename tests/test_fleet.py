"""🚢 Fleet contracts through the parent's shared checks (vendor/fleet_check.py): its locked bytes, and scripts."""
import unittest
from pathlib import Path

from support import fleet

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED = {"vendor/fleet_check.py": "bc57f08a590ee1cb33a8bb37c1bb3b8f28a2f3c9", "vendor/cli_args.py": "5ae22b1a1b808eca93e3c385a8db867fbeb8ee32"}


class VendorLock(unittest.TestCase):
    def test_fleet_check_is_the_accepted_parent_commit(self):
        fleet.check_lock(ROOT, commits=ACCEPTED)


# 🧰 Scripts: 📝 each one describes itself and ⌨️ one that reads sys.argv declares its arguments (argparse /
# cli_args). Read with ast, never run; the portfolio's script catalog reads the same facts.

class ScriptsDescribeThemselves(unittest.TestCase):
    def test_every_script_has_a_description_and_declared_arguments(self):
        fleet.check_scripts(ROOT)
