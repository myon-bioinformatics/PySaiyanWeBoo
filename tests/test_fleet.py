"""🚢 Fleet contracts through the parent's shared checks (vendor/fleet_check.py): its locked bytes, and scripts."""
import unittest
from pathlib import Path

from support import fleet

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED = {"vendor/fleet_check.py", "vendor/cli_args.py"}  # 🔁 locked destinations; they follow main


class VendorLock(unittest.TestCase):
    def test_fleet_check_is_the_accepted_parent_commit(self):
        fleet.check_lock(ROOT)


# 🧰 Scripts: 📝 each one describes itself and ⌨️ one that reads sys.argv declares its arguments (argparse /
# cli_args). Read with ast, never run; the portfolio's script catalog reads the same facts.

class ScriptsDescribeThemselves(unittest.TestCase):
    def test_every_script_has_a_description_and_declared_arguments(self):
        fleet.check_scripts(ROOT)

    def test_no_top_level_vendor_package_imports(self):
        # 📦 vendored modules load by path under a repo-unique name (cli_args README: Loading a vendored copy)
        self.assertEqual(fleet.check_no_vendor_package_imports(ROOT), [])

    def test_pull_request_ci_stays_quick(self):
        # ⏱ push limited to branches, superseded PR runs cancelled, every job timed (fleet_check.check_ci)
        fleet.check_ci(fleet.repo_root(__file__))
