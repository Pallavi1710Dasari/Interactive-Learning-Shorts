"""
The Python side of the motion-reel scene library (RESTYLE_TO_MOTION_REELS.md
section 3). REEL_STYLE=motion only — nothing in the explainer or story paths
imports this.

The LLM never draws in motion mode: it picks names out of a fixed library and
the React components in web/src/motion draw them. This module is where Python
learns those names, so a grader can reject a script or scene that picks
something the player cannot draw — before anything is voiced or rendered.

Phase 1 needs only the icon names. Scene objects, timeline actions and layout
slots join this module in phase 3, when SceneSpec exists.
"""
import json
from functools import lru_cache
from pathlib import Path

#: ONE file for both sides — see its own _comment. Read from web/src so that
#: adding an icon there is the whole change; there is no second list here to
#: forget to update.
ICONS_PATH = Path(__file__).resolve().parent.parent / "web" / "src" / "motion" / "icons.json"


@lru_cache(maxsize=1)
def icon_names() -> frozenset[str]:
    """Every icon name the motion player can draw."""
    data = json.loads(ICONS_PATH.read_text(encoding="utf-8"))
    return frozenset(data["icons"])
