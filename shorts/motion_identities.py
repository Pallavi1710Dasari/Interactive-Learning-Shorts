"""
Language identities for motion reels (RESTYLE_TO_MOTION_REELS.md, phase 3
badges). REEL_STYLE=motion only.

shorts/motion_identities.yaml gives every course language a display name, a
signature colour, an original geometric symbol, a code file name and a shared
character voice, plus a neutral grey host identity and the four voice slots.
This module loads and validates it, and derives what the player draws:

  - each colour's TONES: one for the dark fields (navy, blue) and one for the
    light fields (paper, yellow), each at least 3:1 against both of its fields
    — for symbols, waveforms and large titles; the signature colour itself is
    never drawn raw on a field;
  - its TEXT TONES, the same idea at 4.5:1, for small text drawn in the
    identity's colour (role labels, speaker tags) — exempt from the reserved
    rule below, which is about fills and marks;
  - the reserved-colour rule: no signature or tone within 60 RGB units of
    coral, mint or lavender;
  - the symbol's shapes, checked to be simple and inside the 100 x 100 grid.

The player's copy is web/src/motion/identity/identities.generated.json,
written by `python -m shorts.motion_identities export`; a test checks it is
current.
"""
import colorsys
import json
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "motion_identities.yaml"
EXPORT = ROOT.parent / "web" / "src" / "motion" / "identity" / "identities.generated.json"

#: web/src/motion/tokens.ts FIELDS.
FIELDS = {"navy": "#091025", "blue": "#283EE6", "paper": "#ECF0F7", "yellow": "#FDD13E"}
DARK_FIELDS, LIGHT_FIELDS = ("navy", "blue"), ("paper", "yellow")
#: Colours with a fixed meaning in every motion reel: failure, success, system-added.
RESERVED = {"coral": "#F2555A", "mint": "#17B27B", "lavender": "#B9A8FF"}
RESERVED_DISTANCE = 60.0
MIN_CONTRAST = 3.0          #: symbols, waveforms, large titles
MIN_TEXT_CONTRAST = 4.5     #: small text (role labels, speaker tags)
VOICE_KEYS = ("character_1", "character_2")


# ================================================================== colour

def _rgb(hexs: str) -> tuple[int, int, int]:
    return tuple(int(hexs[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(v))) for v in rgb)


def luminance(hexs: str) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(hexs)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def distance(a: str, b: str) -> float:
    return sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b))) ** 0.5


def tones(colour: str, minimum: float = MIN_CONTRAST) -> tuple[str, str]:
    """(on_dark, on_light): the colour lightened until it reaches `minimum`
    (3:1) on navy and blue, and darkened until it reaches it on paper and
    yellow — the same hue and saturation, only the lightness moves."""
    r, g, b = (v / 255 for v in _rgb(colour))
    h, l0, s = colorsys.rgb_to_hls(r, g, b)

    def at(light: float) -> str:
        return _hex(tuple(v * 255 for v in colorsys.hls_to_rgb(h, light, s)))

    light, on_dark = l0, colour
    while min(contrast(on_dark, FIELDS[f]) for f in DARK_FIELDS) < minimum and light < 0.97:
        light += 0.01
        on_dark = at(light)
    light, on_light = l0, colour
    while min(contrast(on_light, FIELDS[f]) for f in LIGHT_FIELDS) < minimum and light > 0.03:
        light -= 0.01
        on_light = at(light)
    return on_dark, on_light


# ================================================================== models

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


class Shape(BaseModel):
    """One shape of a symbol. Exactly one of rect / circle / path."""
    rect: list[float] | None = None
    circle: list[float] | None = None
    path: str | None = None
    r: float = 0
    stroke: float | None = None
    tone: str = "main"

    @model_validator(mode="after")
    def simple(self):
        kinds = [k for k in ("rect", "circle", "path") if getattr(self, k) is not None]
        if len(kinds) != 1:
            raise ValueError(f"a shape is exactly one of rect, circle or path (got {kinds})")
        if self.tone not in ("main", "soft"):
            raise ValueError(f"tone {self.tone!r} is not main or soft")
        if self.rect is not None:
            if len(self.rect) != 4:
                raise ValueError("rect is [x, y, w, h]")
            x, y, w, h = self.rect
            if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > 100 or y + h > 100:
                raise ValueError(f"rect {self.rect} is outside the 100 x 100 grid")
        if self.circle is not None:
            if len(self.circle) != 3:
                raise ValueError("circle is [cx, cy, r]")
            cx, cy, rad = self.circle
            if rad <= 0 or cx - rad < 0 or cy - rad < 0 or cx + rad > 100 or cy + rad > 100:
                raise ValueError(f"circle {self.circle} is outside the 100 x 100 grid")
        if self.path is not None:
            if not re.fullmatch(r"[MLCAZmlcaz0-9 .,\-]+", self.path):
                raise ValueError("a path uses only M L C A Z commands and numbers")
            if self.stroke is None:
                raise ValueError("a path is drawn as a stroke — give it `stroke`")
            nums = [float(n) for n in _NUM.findall(self.path)]
            if any(n < 0 or n > 100 for n in nums):
                raise ValueError(f"path {self.path[:30]!r} leaves the 100 x 100 grid")
        return self


class Identity(BaseModel):
    id: str
    name: str
    colour: str
    symbol: list[Shape]
    file: str = ""
    voice: str = ""

    @field_validator("colour")
    @classmethod
    def hex_colour(cls, v):
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
            raise ValueError(f"colour {v!r} is not #RRGGBB")
        return v.upper()

    @property
    def tones(self) -> tuple[str, str]:
        return tones(self.colour)

    @property
    def text_tones(self) -> tuple[str, str]:
        return tones(self.colour, MIN_TEXT_CONTRAST)

    @model_validator(mode="after")
    def readable_and_unreserved(self):
        problems: list[str] = []
        on_dark, on_light = tones(self.colour)
        for f in DARK_FIELDS:
            if contrast(on_dark, FIELDS[f]) < MIN_CONTRAST:
                problems.append(f"no tone of {self.colour} reaches {MIN_CONTRAST}:1 on {f}")
        for f in LIGHT_FIELDS:
            if contrast(on_light, FIELDS[f]) < MIN_CONTRAST:
                problems.append(f"no tone of {self.colour} reaches {MIN_CONTRAST}:1 on {f}")
        text_dark, text_light = tones(self.colour, MIN_TEXT_CONTRAST)
        for f in DARK_FIELDS:
            if contrast(text_dark, FIELDS[f]) < MIN_TEXT_CONTRAST:
                problems.append(f"no text tone of {self.colour} reaches {MIN_TEXT_CONTRAST}:1 on {f}")
        for f in LIGHT_FIELDS:
            if contrast(text_light, FIELDS[f]) < MIN_TEXT_CONTRAST:
                problems.append(f"no text tone of {self.colour} reaches {MIN_TEXT_CONTRAST}:1 on {f}")
        # The reserved rule covers what is drawn as a fill or a mark (the colour
        # and its 3:1 tones). The 4.5:1 text tones are exempt: to read as small
        # text on navy a tone must be pale, every pale tint sits near lavender,
        # and a role label beside its own badge carries no failure / success /
        # system-added meaning.
        for label, c in (("colour", self.colour), ("dark-field tone", on_dark), ("light-field tone", on_light)):
            for name, reserved in RESERVED.items():
                if distance(c, reserved) < RESERVED_DISTANCE:
                    problems.append(f"{label} {c} is too close to {name} {reserved} "
                                    f"({distance(c, reserved):.0f} < {RESERVED_DISTANCE:.0f})")
        if not 1 <= len(self.symbol) <= 8:
            problems.append(f"{len(self.symbol)} shapes — a symbol is 1-8 simple shapes")
        if problems:
            raise ValueError(f"identity {self.id!r}: " + "; ".join(problems))
        return self

    def spec(self, theme_label: str = "") -> dict:
        """What the player needs (schema.MotionIdentitySpec)."""
        on_dark, on_light = self.tones
        text_dark, text_light = self.text_tones
        return {"id": self.id, "name": self.name, "colour": self.colour, "on_dark": on_dark,
                "on_light": on_light, "text_on_dark": text_dark, "text_on_light": text_light,
                "file": self.file,
                "symbol": [s.model_dump(exclude_none=True) for s in self.symbol]}


class Registry(BaseModel):
    voices: dict[str, str]
    host: Identity
    languages: dict[str, Identity]

    @model_validator(mode="after")
    def consistent(self):
        problems: list[str] = []
        for key in ("narrator", "host", *VOICE_KEYS):
            if not self.voices.get(key):
                problems.append(f"voices.{key} is missing")
        slots = [self.voices.get(k) for k in ("narrator", "host", *VOICE_KEYS)]
        if len(set(slots)) != len(slots):
            problems.append(f"voice slots repeat: {slots} — narrator, host and the two "
                            f"character voices are four different voices")
        for lang, ident in self.languages.items():
            if not re.fullmatch(r"[a-z0-9]+", lang):
                problems.append(f"language {lang!r} must be lowercase letters and digits (it is a tag)")
            if ident.voice not in VOICE_KEYS:
                problems.append(f"{lang}: voice {ident.voice!r} is not one of {VOICE_KEYS}")
            if not ident.file:
                problems.append(f"{lang}: no code file name")
        names = [i.name for i in self.languages.values()]
        if len(set(names)) != len(names):
            problems.append("display names repeat")
        if problems:
            raise ValueError("motion identity registry: " + "; ".join(problems))
        return self


def parse(data: dict) -> Registry:
    host = Identity(id="host", **data["host"])
    langs = {k: Identity(id=k, **v) for k, v in (data.get("languages") or {}).items()}
    return Registry(voices=data.get("voices") or {}, host=host, languages=langs)


@lru_cache(maxsize=1)
def registry() -> Registry:
    return parse(yaml.safe_load(PATH.read_text(encoding="utf-8")) or {})


def languages() -> list[str]:
    return list(registry().languages)


def identity(lang: str) -> Identity:
    return registry().languages[lang]


def voice_slot(identity_id: str) -> str:
    """The voice slot an identity speaks with: the host's, or its language's
    shared character voice."""
    reg = registry()
    if identity_id == "host":
        return reg.voices["host"]
    return reg.voices[reg.languages[identity_id].voice]


def narrator_slot() -> str:
    return registry().voices["narrator"]


def export_json() -> str:
    reg = registry()
    data = {"_comment": "GENERATED from shorts/motion_identities.yaml by `python -m "
                        "shorts.motion_identities export` — do not edit by hand.",
            "host": reg.host.spec(),
            "languages": {k: v.spec() for k, v in reg.languages.items()}}
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
        raise SystemExit("usage: python -m shorts.motion_identities export")
