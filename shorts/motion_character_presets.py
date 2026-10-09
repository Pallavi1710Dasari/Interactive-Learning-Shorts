"""
Character presets for motion reels' optional animated-character layer.

Ours, not the copied rig's: shorts/motion_character_presets.yaml holds the
DEFAULTS (the shared host, one character per course language, and a few
extras), and shorts/motion_character_presets.saved.yaml holds what the
designer (#motion/characters/designer) saved over them. A preset's effective
config is its saved entry if there is one, else its default; "reset to
default" deletes the saved entry. Neither file lives under
web/src/motion/characters/, so updating the copied rig never touches them.

Each preset is the rig's CharacterConfig (web/src/motion/characters/skins/
config.ts), validated here against the same option lists, so a preset that
saves is one the rig can draw.

A plan carries the config it was built with (MotionCharacterTrack.config), so
editing a preset changes the reels made after the edit, never one already made.

    python -m shorts.motion_character_presets export
        writes web/src/motion/cast/presets.generated.json (the defaults and the
        option lists, for the player's pages); a test checks it is current
"""
import json
import os
import re
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

ROOT = Path(__file__).resolve().parent
DEFAULTS_PATH = ROOT / "motion_character_presets.yaml"
EXPORT = ROOT.parent / "web" / "src" / "motion" / "cast" / "presets.generated.json"

#: The rig's option lists (skins/config.ts types). A named skin tone or hair
#: colour, or any #RRGGBB.
SKIN_TONES = ("fair", "wheatish", "medium", "dusky", "deep")
HAIR_COLORS = ("black", "darkBrown", "brown", "auburn", "grey")
HAIR_STYLES = ("short", "sidePart", "quiff", "curly", "buzz", "braid", "ponytail", "bob", "long", "bun", "wavy")
TOPS = ("shirt", "shirtTie", "tshirt", "kurta", "hoodie", "blouse", "polo")
BOTTOMS = ("trousers", "jeans", "skirt", "salwar", "shorts")
OPTIONS = {
    "gender": ("male", "female"), "art": ("soft", "line"), "shading": ("flat", "lit"),
    "skinTone": SKIN_TONES, "hairStyle": HAIR_STYLES, "hairColor": HAIR_COLORS,
    "jaw": ("round", "oval", "square"), "brows": ("thin", "medium", "thick"), "eyes": ("oval", "dot"),
    "mouth": ("full", "line"), "top": TOPS, "bottom": BOTTOMS,
    "glasses": ("none", "round", "rect"), "beard": ("none", "stubble", "short"),
    "flags": ("earrings", "bindi", "watch", "flower", "necklace", "belt"),
}

_HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def _hex(v):
    if v is not None and not _HEX.fullmatch(str(v)):
        raise ValueError(f"{v!r} is not a #RRGGBB colour")
    return v


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Hair(_Strict):
    style: Literal[HAIR_STYLES]          # type: ignore[valid-type]
    color: str

    @field_validator("color")
    @classmethod
    def colour(cls, v):
        return v if v in HAIR_COLORS else _hex(v)


class Face(_Strict):
    jaw: Literal["round", "oval", "square"]
    brows: Literal["thin", "medium", "thick"]
    eyes: Literal["oval", "dot"]
    mouth: Literal["full", "line"]
    lip: Optional[str] = None
    blush: Optional[float] = Field(default=None, ge=0, le=1)

    _lip = field_validator("lip")(classmethod(lambda cls, v: _hex(v)))


class Outfit(_Strict):
    top: Literal[TOPS]                   # type: ignore[valid-type]
    topColor: str
    bottom: Literal[BOTTOMS]             # type: ignore[valid-type]
    bottomColor: str
    shoeColor: Optional[str] = None
    accentColor: Optional[str] = None

    _colours = field_validator("topColor", "bottomColor", "shoeColor", "accentColor")(
        classmethod(lambda cls, v: _hex(v)))


class Accessories(_Strict):
    glasses: Optional[Literal["none", "round", "rect"]] = None
    earrings: Optional[bool] = None
    bindi: Optional[bool] = None
    beard: Optional[Literal["none", "stubble", "short"]] = None
    watch: Optional[bool] = None
    flower: Optional[bool] = None
    necklace: Optional[bool] = None
    belt: Optional[bool] = None


class Build(_Strict):
    height: float = Field(ge=0.9, le=1.1)
    shoulders: float = Field(ge=0.9, le=1.1)


class CharacterConfig(_Strict):
    """The rig's CharacterConfig."""
    name: str = Field(min_length=1, max_length=40)
    gender: Literal["male", "female"]
    art: Literal["soft", "line"]
    shading: Optional[Literal["flat", "lit"]] = None
    skinTone: str
    hair: Hair
    face: Face
    outfit: Outfit
    accessories: Accessories = Field(default_factory=Accessories)
    build: Build

    @field_validator("skinTone")
    @classmethod
    def tone(cls, v):
        return v if v in SKIN_TONES else _hex(v)

    def dump(self) -> dict:
        return self.model_dump(exclude_none=True)


# ================================================================ loading

def saved_path() -> Path:
    """Where the designer saves (MOTION_CHARACTER_PRESETS_SAVED moves it, for tests)."""
    return Path(os.environ.get("MOTION_CHARACTER_PRESETS_SAVED")
                or ROOT / "motion_character_presets.saved.yaml")


def _load(path: Path) -> dict:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}


def defaults() -> dict[str, dict]:
    """Every default preset by id: 'host', each language id, each extra."""
    from .motion_identities import languages
    data = _load(DEFAULTS_PATH)
    out: dict[str, dict] = {}
    problems: list[str] = []
    entries = [("host", data.get("host"))] + list((data.get("languages") or {}).items()) \
        + list((data.get("extras") or {}).items())
    for pid, raw in entries:
        if pid in out:
            problems.append(f"preset {pid!r} is defined twice")
            continue
        try:
            out[pid] = CharacterConfig(**(raw or {})).dump()
        except Exception as e:            # noqa: BLE001 — reported with its id
            problems.append(f"{pid}: {e}")
    for lang in languages():
        if lang not in (data.get("languages") or {}):
            problems.append(f"language {lang!r} has no default character preset")
    for lang in data.get("languages") or {}:
        if lang not in languages():
            problems.append(f"{lang!r} is not a language in motion_identities.yaml")
    if problems:
        raise ValueError("motion character presets: " + "; ".join(problems))
    return out


def saved() -> dict[str, dict]:
    """The designer's saved presets (only ids that have a default)."""
    known = defaults()
    out = {}
    for pid, raw in (_load(saved_path()) or {}).items():
        if pid in known:
            out[pid] = CharacterConfig(**raw).dump()
    return out


def ids() -> list[str]:
    return list(defaults())


def preset(pid: str) -> dict:
    """A preset's effective config: saved over default."""
    d = defaults()
    if pid not in d:
        raise KeyError(f"no character preset {pid!r} (have: {', '.join(d)})")
    return saved().get(pid) or d[pid]


def is_saved(pid: str) -> bool:
    return pid in saved()


def save(pid: str, config: dict) -> dict:
    """Validate and save a preset over its default; returns the saved config."""
    if pid not in defaults():
        raise KeyError(f"no character preset {pid!r}")
    cfg = CharacterConfig(**config).dump()
    data = _load(saved_path()) or {}
    data[pid] = cfg
    _write(data)
    return cfg


def reset(pid: str) -> dict:
    """Drop a saved preset, so its default applies again; returns the default."""
    d = defaults()
    if pid not in d:
        raise KeyError(f"no character preset {pid!r}")
    data = _load(saved_path()) or {}
    if pid in data:
        del data[pid]
        _write(data)
    return d[pid]


def _write(data: dict) -> None:
    path = saved_path()
    head = ("# Character presets saved by the designer (#motion/characters/designer) over\n"
            "# the defaults in motion_character_presets.yaml. Written by the API server;\n"
            "# 'reset to default' removes an entry.\n")
    path.write_text(head + yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


# ================================================================ export

def export_json() -> str:
    from .motion_identities import languages
    d = defaults()
    data = {"_comment": "GENERATED from shorts/motion_character_presets.yaml by `python -m "
                        "shorts.motion_character_presets export` — do not edit by hand. "
                        "Defaults only; the designer's saved presets come from the API.",
            "host": d["host"],
            "languages": {k: d[k] for k in languages()},
            "extras": {k: v for k, v in d.items() if k != "host" and k not in languages()},
            "options": {k: list(v) for k, v in OPTIONS.items()}}
    return json.dumps(data, indent=1) + "\n"


def export() -> Path:
    EXPORT.parent.mkdir(parents=True, exist_ok=True)
    EXPORT.write_text(export_json(), encoding="utf-8")
    return EXPORT


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["export"]:
        print(f"wrote {export()}")
    else:
        raise SystemExit("usage: python -m shorts.motion_character_presets export")
