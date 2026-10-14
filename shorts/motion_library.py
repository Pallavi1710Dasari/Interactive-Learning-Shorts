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


# ================================================================== scenes
#
# Phase 3: the scene vocabulary — web/src/motion/library.json, the ONE file
# both sides read (see its _comment). Python validates scenes against it and
# lays them out with its heights; the player draws them.

LIBRARY_PATH = ICONS_PATH.parent / "library.json"


@lru_cache(maxsize=1)
def library() -> dict:
    """The whole scene vocabulary: frame regions, fields, tones, transitions,
    object kinds (props, layout, height, max lengths, allowed actions),
    action kinds and the identity symbol vocabulary."""
    return json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))


def object_kinds() -> dict[str, dict]:
    return library()["objects"]


def action_kinds() -> frozenset[str]:
    return frozenset(library()["actions"])


def camera_actions() -> frozenset[str]:
    """The actions every object accepts: the virtual camera's and cursor's
    (shorts/motion_camera.py)."""
    return frozenset(library().get("camera_actions", []))


def transitions() -> tuple[str, ...]:
    return tuple(library()["transitions"])


def fields() -> tuple[str, ...]:
    return tuple(library()["fields"])


def tones() -> tuple[str, ...]:
    return tuple(library()["tones"])
