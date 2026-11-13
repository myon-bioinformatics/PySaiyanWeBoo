"""web_ui: PySaiyanWeBoo's old module name, kept so ``import web_ui`` and ``python -S web_ui.py ...`` still work.

The code is ``pysaiyanweboo.py`` (it outgrew a web UI). This file only forwards to it: the same module object, so
private helpers and monkeypatches are shared. A repository that copies the file must copy ``pysaiyanweboo.py``.
It goes once the repositories have moved to ``import pysaiyanweboo``.
"""
import sys
from pathlib import Path

_here = str(Path(__file__).resolve().parent)
if _here not in sys.path:                      # python -I / -P do not add the script's directory
    sys.path.insert(0, _here)
try:
    import pysaiyanweboo as _module
except ImportError as exc:
    raise ImportError("web_ui.py only forwards to pysaiyanweboo.py, which is not next to it: copy pysaiyanweboo.py "
                      "(PySaiyanWeBoo's single file) instead") from exc
if __name__ == "__main__":
    raise SystemExit(_module.main())
sys.modules[__name__] = _module
