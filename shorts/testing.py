"""
Test isolation: every *_test.py calls isolate_output() before it imports
anything else from shorts, so the run writes into a temp folder instead of the
real output/ and assets/cast/.

    from shorts.testing import isolate_output
    isolate_output()
    from shorts import config, ...   # config.OUTPUT_DIR is now the temp folder

Two reasons it has to happen before the import and not as a patch after it:
paths derived from config.OUTPUT_DIR at import time (usage.STORE,
server.UPLOADS, story_audio.AUDIO_CACHE_DIR, cast_sheets' folders, ...) would
otherwise keep pointing at the real folder; and a test that starts a
subprocess passes the same environment on, so the child is isolated too.

assets/cast/ gets a COPY of the approved sheets, because story tests need
them to exist and cast_sheets_test deletes and rewrites that folder. Before
this, two suites run at once could see assets/cast/ empty mid-run — the
FileNotFoundError on rahul.png that story_reel_test hit when it ran beside
cast_sheets_test.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_REAL_CAST = _ROOT / "assets" / "cast"
_REAL_OUTPUT = _ROOT / "output"


def isolate_output(name: str = "shorts_test", seed: tuple[str, ...] = ()) -> Path:
    """Point SHORTS_OUTPUT_DIR and SHORTS_CAST_ASSETS_DIR at a fresh temp
    folder, removed when the process exits. Returns the temp output folder.
    A child process that inherits an isolated environment keeps its parent's
    folder rather than making its own.

    `seed` names files or folders of the REAL output/ to copy in first, for a
    test that needs an existing reel to exist (and to prove a run leaves it
    unchanged). They are copied, never linked, so the real ones are only
    ever read."""
    if os.environ.get("SHORTS_OUTPUT_DIR"):
        return Path(os.environ["SHORTS_OUTPUT_DIR"])
    if "shorts.config" in sys.modules:
        raise RuntimeError("isolate_output() must run before shorts.config is imported — "
                           "otherwise paths derived from OUTPUT_DIR still point at output/")
    root = Path(tempfile.mkdtemp(prefix=f"{name}_"))
    out = root / "output"
    out.mkdir()
    cast = root / "cast"
    if _REAL_CAST.is_dir():
        shutil.copytree(_REAL_CAST, cast)
    else:
        cast.mkdir()
    for rel in seed:
        src = _REAL_OUTPUT / rel
        if src.is_dir():
            shutil.copytree(src, out / rel)
        elif src.is_file():
            shutil.copy2(src, out / rel)
    os.environ["SHORTS_OUTPUT_DIR"] = str(out)
    os.environ["SHORTS_CAST_ASSETS_DIR"] = str(cast)
    atexit.register(shutil.rmtree, root, True)
    return out
