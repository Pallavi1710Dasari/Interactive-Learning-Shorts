"""
Motion-reel THEMES, TAGS and AVATARS (RESTYLE_TO_MOTION_REELS.md, phase 2b).
REEL_STYLE=motion only — nothing in the explainer or story paths imports this.

The teaching approach is HOW the idea is explained; the theme is the FORMAT of
the reel (who speaks, what it feels like). This module is everything about a
theme that is a FIXED RULE rather than a judgement:

  - the registries: shorts/motion_themes.yaml and shorts/motion_avatars.yaml,
    loaded and validated here. Adding a theme is one YAML entry and no code
    change, as long as it uses a template, hook style and avatar kind that
    already exist (TEMPLATES, HOOK_STYLES, AVATAR_KINDS below);
  - the language a reel is in, and its tags;
  - the reel history (earlier reels' tags.json) and the VARIETY rule;
  - the FIT CHECK (theme_problems): requirements, incompatible approaches,
    template and variety. The LLM only judges fit among themes that pass it
    (skills/theme.py), and its pick is checked again here.
"""
import re
from functools import lru_cache
from pathlib import Path
from typing import get_args

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .schema import (MOTION_BEAT_ORDER, MOTION_TEMPLATES, MotionSpeaker, MotionTags,
                     TeachingApproachKind)

APPROACH_KINDS: tuple[str, ...] = get_args(TeachingApproachKind)

ROOT = Path(__file__).resolve().parent
THEMES_PATH = ROOT / "motion_themes.yaml"
AVATARS_PATH = ROOT / "motion_avatars.yaml"

TEMPLATES = MOTION_TEMPLATES
#: How a hook may open. symptom_question and how_question are the two base
#: templates' own hooks (checks.check_motion_hook_curiosity's original rules);
#: the other three are graded from a theme's `openers`:
#:   question  opens with an opener and asks (contains "?")
#:   claim     opens with an opener; a statement, a question is optional
#:   scene     opens with an opener; drops the viewer into a moment
HOOK_STYLES = ("symptom_question", "how_question", "question", "claim", "scene")
AVATAR_KINDS = ("language", "host")
#: Colours with a fixed meaning in every motion reel (web/src/motion/tokens.ts):
#: coral failure, mint success, lavender system-added. No avatar may wear them.
RESERVED_COLOURS = frozenset({"#f2555a", "#17b27b", "#b9a8ff"})
#: The four field colours (web/src/motion/tokens.ts FIELDS).
FIELD_COLOURS = ("#091025", "#283EE6", "#ECF0F7", "#FDD13E")

TAG_RE = re.compile(r"^#[a-z0-9]+$")
MAX_CONCEPT_TAGS = 3


# ================================================================= registry

class ThemeSpeaker(BaseModel):
    role: str
    avatar: str | None = None
    asks: bool = False

    @field_validator("role")
    @classmethod
    def role_is_a_label(cls, v):
        if not re.fullmatch(r"[A-Z][A-Z_]*", v):
            raise ValueError(f"speaker role {v!r} must be an UPPER_CASE label")
        return v


class ThemeBeat(BaseModel):
    does: str
    speakers: list[str] = Field(default_factory=list)
    asks: bool = False


class ThemeHook(BaseModel):
    style: str
    openers: list[str] = Field(default_factory=list)
    symptom: bool = False
    brief: str = ""

    @field_validator("style")
    @classmethod
    def known_style(cls, v):
        if v not in HOOK_STYLES:
            raise ValueError(f"hook style {v!r} is not one of {HOOK_STYLES}")
        return v


class ThemeSpec(BaseModel):
    """One entry of shorts/motion_themes.yaml."""
    id: str
    tag: str
    template: str
    description: str
    speakers: list[ThemeSpeaker]
    needs_code: bool = False
    suits: list[str] = Field(default_factory=list)
    works_with: list[str] = Field(default_factory=list)
    incompatible_with: list[str] = Field(default_factory=list)
    hook: ThemeHook
    #: A template name (that template's own beats, unchanged) or one entry per
    #: fix_story beat.
    beats: str | dict[str, ThemeBeat]

    @property
    def base(self) -> bool:
        """Uses its template's own prompt and beats unchanged — the original
        fix_story (classic_explainer) and walkthrough reels."""
        return isinstance(self.beats, str)

    @property
    def two_speaker(self) -> bool:
        return len(self.speakers) == 2

    @property
    def roles(self) -> list[str]:
        return [s.role for s in self.speakers]

    def speaker(self, role: str) -> ThemeSpeaker | None:
        return next((s for s in self.speakers if s.role == role), None)

    @model_validator(mode="after")
    def consistent(self):
        problems: list[str] = []
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.id):
            problems.append("id must be lowercase letters, digits and _")
        if not TAG_RE.match("#" + self.tag):
            problems.append(f"tag {self.tag!r} must be lowercase letters and digits only")
        if self.template not in TEMPLATES:
            problems.append(f"template {self.template!r} is not one of {TEMPLATES}")
        if not 1 <= len(self.speakers) <= 2:
            problems.append(f"{len(self.speakers)} speakers, a theme has 1 or 2")
        if len(set(self.roles)) != len(self.roles):
            problems.append(f"speaker roles repeat: {self.roles}")
        for s in self.speakers:
            if self.two_speaker and s.avatar not in AVATAR_KINDS:
                problems.append(f"speaker {s.role} needs an avatar, one of {AVATAR_KINDS}")
            if not self.two_speaker and s.avatar is not None:
                problems.append("a one-speaker theme has no avatar")
        if self.two_speaker and {s.avatar for s in self.speakers} != set(AVATAR_KINDS):
            problems.append("a two-speaker theme casts one 'host' and one 'language' avatar "
                            "(two characters, two voices)")
        for kind in self.works_with + self.incompatible_with:
            if kind not in APPROACH_KINDS:
                problems.append(f"{kind!r} is not a teaching approach ({APPROACH_KINDS})")
        both = set(self.works_with) & set(self.incompatible_with)
        if both:
            problems.append(f"{sorted(both)} are both works_with and incompatible_with")
        if self.template == "walkthrough" and self.beats != "walkthrough":
            problems.append("a walkthrough theme uses the walkthrough template's own beats "
                            "(beats: walkthrough) — chapters have no per-beat template")
        if isinstance(self.beats, str):
            if self.beats != self.template:
                problems.append(f"beats {self.beats!r} must name the theme's own template "
                                f"{self.template!r}")
            if self.two_speaker:
                problems.append("a two-speaker theme needs its own beat template, to say "
                                "who speaks in each beat")
        else:
            if self.template != "fix_story":
                problems.append("only fix_story themes carry a per-beat template")
            if set(self.beats) != set(MOTION_BEAT_ORDER):
                missing = [b for b in MOTION_BEAT_ORDER if b not in self.beats]
                extra = sorted(set(self.beats) - set(MOTION_BEAT_ORDER))
                problems.append(f"beat template must cover the 11 fix_story beats exactly "
                                f"(missing {missing}, unknown {extra})")
            for name, beat in self.beats.items():
                if self.two_speaker and not beat.speakers:
                    problems.append(f"beat {name} says nothing about who speaks")
                unknown = [r for r in beat.speakers if r not in self.roles]
                if unknown:
                    problems.append(f"beat {name} names unknown speaker(s) {unknown}")
                if not self.two_speaker and beat.speakers:
                    problems.append(f"beat {name} names speakers in a one-speaker theme")
        if self.hook.style in ("question", "claim", "scene") and not self.hook.openers:
            problems.append(f"a {self.hook.style} hook needs `openers`")
        if self.base and self.hook.style != {"fix_story": "symptom_question",
                                             "walkthrough": "how_question"}.get(self.template):
            problems.append("a theme using its template's own beats keeps its template's own "
                            "hook (fix_story: symptom_question, walkthrough: how_question)")
        if problems:
            raise ValueError(f"theme {self.id!r}: " + "; ".join(problems))
        return self


class ThemeRegistry(BaseModel):
    themes: dict[str, ThemeSpec]
    window: int = 5
    max_same: int = 2
    fallback: dict[str, str]

    def get(self, theme_id: str | None) -> ThemeSpec | None:
        return self.themes.get(theme_id or "")

    def ids(self) -> list[str]:
        return list(self.themes)

    def tags(self) -> dict[str, str]:
        return {t.id: t.tag for t in self.themes.values()}

    def base_for(self, template: str) -> ThemeSpec:
        """The theme a script written before themes existed is graded as."""
        return self.themes[self.fallback[template]]

    @model_validator(mode="after")
    def consistent(self):
        problems: list[str] = []
        for template in TEMPLATES:
            fb = self.fallback.get(template)
            if fb not in self.themes:
                problems.append(f"fallback for {template} is {fb!r}, not a theme")
            elif self.themes[fb].template != template or not self.themes[fb].base:
                problems.append(f"fallback {fb!r} must be a {template} theme using its "
                                f"template's own beats")
        tags = [t.tag for t in self.themes.values()]
        dupes = sorted({t for t in tags if tags.count(t) > 1})
        if dupes:
            problems.append(f"theme tags repeat: {dupes}")
        if self.window < 2 or not 1 <= self.max_same <= self.window:
            problems.append(f"variety window {self.window} / max_same {self.max_same} "
                            f"make no sense")
        if problems:
            raise ValueError("motion theme registry: " + "; ".join(problems))
        return self


def parse_theme_registry(data: dict) -> ThemeRegistry:
    themes = {tid: ThemeSpec(id=tid, **(spec or {}))
              for tid, spec in (data.get("themes") or {}).items()}
    variety = data.get("variety") or {}
    return ThemeRegistry(themes=themes, window=variety.get("window", 5),
                         max_same=variety.get("max_same", 2),
                         fallback=data.get("fallback") or {})


def load_theme_registry(path: Path | str | None = None) -> ThemeRegistry:
    path = Path(path) if path else THEMES_PATH
    return parse_theme_registry(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


_REGISTRY_OVERRIDE: list[ThemeRegistry] = []


@lru_cache(maxsize=1)
def _default_registry() -> ThemeRegistry:
    return load_theme_registry()


def registry() -> ThemeRegistry:
    """The theme registry in use: shorts/motion_themes.yaml, unless a test has
    swapped one in with use_registry()."""
    return _REGISTRY_OVERRIDE[-1] if _REGISTRY_OVERRIDE else _default_registry()


class use_registry:
    """`with use_registry(reg): ...` — grade and choose against another
    registry (a test proving a new theme needs only a registry entry)."""
    def __init__(self, reg: ThemeRegistry):
        self.reg = reg

    def __enter__(self):
        _REGISTRY_OVERRIDE.append(self.reg)
        return self.reg

    def __exit__(self, *exc):
        _REGISTRY_OVERRIDE.pop()


def theme_for_script(script) -> ThemeSpec:
    """The theme a script is graded as: its own, or — for a script written
    before themes existed — its template's base theme."""
    reg = registry()
    spec = reg.get(getattr(script, "theme", None))
    if spec is not None:
        return spec
    return reg.base_for(getattr(script, "template", "fix_story") or "fix_story")


# ================================================================== avatars

class AvatarPalette(BaseModel):
    primary: str
    secondary: str
    accent: str
    ink: str

    @model_validator(mode="after")
    def no_reserved(self):
        for name, colour in self.model_dump().items():
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", colour):
                raise ValueError(f"palette {name} {colour!r} is not a #RRGGBB colour")
            if colour.lower() in RESERVED_COLOURS:
                raise ValueError(f"palette {name} {colour} is reserved (coral = failure, "
                                 f"mint = success, lavender = system-added)")
        fields = {c.lower() for c in FIELD_COLOURS}
        if self.primary.lower() in fields:
            raise ValueError(f"palette primary {self.primary} is a field colour — the body "
                             f"would vanish on that field")
        return self


class AvatarArt(BaseModel):
    """What the player draws (web/src/motion/avatars/Avatar.tsx), from the
    art vocabulary in web/src/motion/library.json."""
    body: str
    head: str
    hair: str
    skin: str
    accessories: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def known(self):
        from .motion_library import library
        vocab = library()["avatar"]
        problems = [f"{name} {value!r} is not one of {vocab[key] if key != 'skins' else list(vocab[key])}"
                    for name, value, key in (("body", self.body, "bodies"), ("head", self.head, "heads"),
                                             ("hair", self.hair, "hair"), ("skin", self.skin, "skins"))
                    if value not in vocab[key]]
        problems += [f"accessory {a!r} is not one of {vocab['accessories']}"
                     for a in self.accessories if a not in vocab["accessories"]]
        if problems:
            raise ValueError("; ".join(problems))
        return self


class Avatar(BaseModel):
    id: str
    name: str
    look: str
    art: AvatarArt
    palette: AvatarPalette
    voice_slot: str

    @property
    def voice_path(self) -> str:
        return f"voices/motion/{self.voice_slot}.wav"

    def spec(self):
        """The player's view of this avatar (schema.MotionAvatarSpec)."""
        from .schema import MotionAvatarSpec
        return MotionAvatarSpec(id=self.id, name=self.name, body=self.art.body,
                                head=self.art.head, hair=self.art.hair, skin=self.art.skin,
                                accessories=list(self.art.accessories),
                                palette=self.palette.model_dump())


class AvatarRegistry(BaseModel):
    languages: list[str]
    host: Avatar
    characters: dict[str, Avatar]
    narrator_slot: str = "motion_narrator"

    @model_validator(mode="after")
    def one_per_language(self):
        problems: list[str] = []
        for lang in self.languages:
            if not TAG_RE.match("#" + lang):
                problems.append(f"language {lang!r} must be lowercase letters and digits")
        missing = [l for l in self.languages if l not in self.characters]
        extra = [l for l in self.characters if l not in self.languages]
        if missing or extra:
            problems.append(f"one character per course language (missing {missing}, "
                            f"not a language {extra})")
        # Voices may be SHARED between characters (a few character voices for
        # fifteen languages — see docs/reference/phase3/voices.md). The one
        # rule: the host never shares a voice with a character, so the two
        # speakers of any two-speaker reel always sound different.
        clash = sorted({a.id for a in self.characters.values()
                        if a.voice_slot == self.host.voice_slot})
        if clash:
            problems.append(f"the host's voice slot {self.host.voice_slot!r} is also used by "
                            f"{clash} — a two-speaker reel would have one voice")
        names = [self.host.name] + [a.name for a in self.characters.values()]
        if len(set(names)) != len(names):
            problems.append("character names repeat")
        looks = [(a.art.body, a.art.head, a.art.hair, tuple(a.art.accessories))
                 for a in [self.host, *self.characters.values()]]
        if len(set(looks)) != len(looks):
            problems.append("two characters share the same body, head, hair and accessories")
        if problems:
            raise ValueError("motion avatar registry: " + "; ".join(problems))
        return self


@lru_cache(maxsize=1)
def avatars() -> AvatarRegistry:
    data = yaml.safe_load(AVATARS_PATH.read_text(encoding="utf-8")) or {}
    host = Avatar(id="host", **{k: v for k, v in data["host"].items() if k != "id"})
    chars = {lang: Avatar(id=lang, **spec) for lang, spec in (data.get("characters") or {}).items()}
    return AvatarRegistry(languages=data.get("languages") or [], host=host, characters=chars,
                          narrator_slot=(data.get("narrator") or {}).get("voice_slot",
                                                                         "motion_narrator"))


def language_tags() -> list[str]:
    return list(avatars().languages)


#: The player's copy of the avatar registry, for pages that draw avatars with
#: no plan loaded (the gallery). Written by `python -m shorts.motion_themes
#: export-avatars`; motion_scene_test checks it matches the YAML.
AVATARS_JSON = ROOT.parent / "web" / "src" / "motion" / "avatars" / "avatars.generated.json"


def avatars_json() -> str:
    import json
    reg = avatars()
    data = {"_comment": "GENERATED from shorts/motion_avatars.yaml by `python -m shorts.motion_themes "
                        "export-avatars` — do not edit by hand.",
            "host": reg.host.spec().model_dump(),
            "characters": {k: a.spec().model_dump() for k, a in reg.characters.items()}}
    return json.dumps(data, indent=2) + "\n"


def export_avatars() -> Path:
    AVATARS_JSON.parent.mkdir(parents=True, exist_ok=True)
    AVATARS_JSON.write_text(avatars_json(), encoding="utf-8")
    return AVATARS_JSON



def cast_speakers(theme: ThemeSpec, language: str) -> list[MotionSpeaker]:
    """Each role of a two-speaker theme and the avatar that plays it: the
    shared host, or the language's own character. [] for a one-narrator theme."""
    if not theme.two_speaker:
        return []
    reg = avatars()
    out = []
    for s in theme.speakers:
        a = reg.host if s.avatar == "host" else reg.characters[language]
        out.append(MotionSpeaker(role=s.role, avatar=a.id, name=a.name, voice_slot=a.voice_slot))
    return out


# ================================================================= language

#: Fenced-code labels -> course language.
_FENCE_LANGUAGES = {
    "jsx": "react", "tsx": "react", "js": "javascript", "javascript": "javascript",
    "mjs": "javascript", "ts": "typescript", "typescript": "typescript",
    "py": "python", "python": "python", "python3": "python", "html": "html",
    "css": "css", "sql": "sql", "java": "java", "c": "c", "h": "c",
    "cpp": "cpp", "c++": "cpp", "cc": "cpp", "hpp": "cpp",
    "dockerfile": "docker", "docker": "docker", "compose": "docker",
}
#: Words that name a language in prose — counted, highest wins.
_NAME_PATTERNS = {
    "react": r"\bReact\b|\buse[A-Z]\w+\b|\bJSX\b",
    "node": r"\bNode(?:\.js|JS)?\b|\bExpress(?:\.js)?\b|\bnpm\b|\brequire\(",
    "django": r"\bDjango\b",
    "docker": r"\bDocker(?:file)?\b|\bcontainers?\b|\bdocker-compose\b",
    "os": r"\b[Oo]perating [Ss]ystems?\b|\bOS\b|\bkernel\b|\bpaging\b|\bpage table\b|\bprocess scheduling\b",
    "python": r"\bPython\b",
    "javascript": r"\bJavaScript\b",
    "typescript": r"\bTypeScript\b",
    "html": r"\bHTML\b",
    "css": r"\bCSS\b",
    "sql": r"\bSQL\b",
    "java": r"\bJava\b(?!Script)",
    "cpp": r"\bC\+\+",
}
#: A framework or tool written IN a base language wins over that language when
#: the material names it: Django code is fenced ```python, Express code ```js.
_FRAMEWORKS = {"python": ("django",), "javascript": ("node", "react"),
               "typescript": ("node", "react")}


def detect_language(section_text: str, doc_text: str = "") -> tuple[str, str]:
    """The course language a reel is in, and how it was decided: the selected
    section's fenced code, then the document's (a framework the material names
    wins over its base language: ```python in a Django lesson is django), then
    a language named in the document's title, then the one named most often
    (twice or more), else `cs`. Deterministic, never the LLM. Pass
    --language to override it."""
    langs = set(language_tags())
    everything = (section_text or "") + "\n" + (doc_text or "")
    title = next(iter(re.findall(r"^#\s+(.+)$", doc_text or "", re.M)), "")
    for where, text in (("section", section_text), ("document", doc_text)):
        for label in re.findall(r"^```\s*([\w+#-]+)", text or "", re.M):
            lang = _FENCE_LANGUAGES.get(label.lower())
            if lang in langs:
                for fw in _FRAMEWORKS.get(lang, ()):
                    named = len(re.findall(_NAME_PATTERNS[fw], everything))
                    if fw in langs and (named >= 2 or re.search(_NAME_PATTERNS[fw], title)):
                        return fw, f"```{label} code in material about {fw}"
                return lang, f"the {where}'s ```{label} code"
    for lang, p in _NAME_PATTERNS.items():
        if lang in langs and re.search(p, title):
            return lang, f"the document title {title.strip()!r}"
    text = (section_text or "") + "\n" + (doc_text or "")
    counts = {lang: len(re.findall(p, text)) for lang, p in _NAME_PATTERNS.items()
              if lang in langs}
    best = max(counts.items(), key=lambda kv: kv[1], default=(None, 0))
    if best[1] >= 2:
        return best[0], f"named {best[1]} times in the material"
    return "cs", "no programming language in the material"


# ===================================================================== code

def section_has_code(text: str) -> bool:
    """The material shows real code: a fenced block, or an inline `span` with
    code punctuation in it (`let count = 0`, `useState(0)`). A bare backticked
    word (`count`, `[CLS]`) names a thing; it is not code to run or predict."""
    if "```" in (text or ""):
        return True
    return any(re.search(r"[=();{}]", span) for span in re.findall(r"`([^`\n]+)`", text or ""))


# ===================================================================== tags
#
# Concept tags are SEARCHABLE CONCEPTS — #usestate, #rerender, #tokenization,
# #pagetable — never a code identifier the example happens to use (#setcount,
# #likes) and never a stray word (#different, #screen). So they are taken
# from where material NAMES its concepts: its headings (the document title
# and the reel's own sections' titles) and its defined terms (**bold**, "...
# called X", "known as X"). Phase 2b review, user decision 2026-10-09.

_STOPWORDS = frozenset("""
a an and are as at be because but by can do does each every for from has have how
if in into is it its just like more not of on or so that the their them then there
these this those to up was what when where which while who why will with without
you your doesnt dont one two three four five six seven eight nine ten
""".split())
#: Words that name no concept on their own — verbs, adjectives and filler that
#: headings use around a concept ("How a hash table FINDS a value WITHOUT
#: SEARCHING"). General English, not tuned to any one topic.
_GENERIC_WORDS = frozenset("""
actually also another basic basics brand change changes changing cost costs create
creates creating different does exist exists extra find finds first glance happen
happens important inserting into material matter matters mean means middle need
needs nothing other plain really reproduction read reads remember remembers same
score scores screen searching second session simple simply special than thin
tie ties trigger triggers update updates very want wants way work works your
introduction overview part chapter lesson value values item items thing things
again inside once twice back away out off over path cutting new old good bad
""".split())
#: A defined term: "..., called its vocabulary", "known as a page fault".
_DEFINER = re.compile(r"\b(?:called|known as|named|termed)\s+(?:a |an |the |its |their )?"
                      r"([A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*)?)")


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (word or "").lower())


def _words(text: str) -> list[str]:
    """Words as written, hyphenated and camelCase terms kept whole
    ("re-render", "useState")."""
    return re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text or "")


def _content(word: str) -> bool:
    w = _norm(word)
    return len(w) >= 3 and not w.isdigit() and w not in _STOPWORDS and w not in _GENERIC_WORDS


def doc_title(doc_text: str) -> str:
    """The document's H1, without a "Session 7:" style prefix."""
    title = next(iter(re.findall(r"^#\s+(.+)$", doc_text or "", re.M)), "")
    return re.sub(r"^\s*(?:session|lesson|chapter|unit|module|part)\s*\d+\s*[:.\-–—]\s*", "",
                  title, flags=re.I).strip()


def code_identifiers(text: str) -> set[str]:
    """Every identifier the material's code uses (fenced blocks and inline
    spans), in tag form: `setCount` -> setcount, `likes` -> likes."""
    code = " ".join(re.findall(r"```.*?```", text or "", re.S)
                    + re.findall(r"`([^`\n]+)`", text or ""))
    return {_norm(t) for t in re.findall(r"[A-Za-z_$][A-Za-z0-9_$]*", code)} - {""}


def _heading_terms(heading: str) -> list[tuple[str, bool]]:
    """A heading's concept terms in tag form, each with whether it is a NAMED
    term — a camelCase or hyphenated word, or two adjacent content words
    joined ("hash table" -> hashtable). A pair with a language in it
    ("JavaScript variable") is not a concept of its own."""
    langs = set(language_tags())
    words = _words(heading)
    out: list[tuple[str, bool]] = []
    for i, w in enumerate(words):
        if not _content(w):
            continue
        out.append((_norm(w), bool(re.search(r"[a-z][A-Z]|-", w))))
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if nxt and _content(nxt) and not {_norm(w), _norm(nxt)} & langs:
            out.append((_norm(w) + _norm(nxt), True))
    return out


def _defined_terms(section_text: str) -> list[str]:
    out: list[str] = []
    for term in re.findall(r"\*\*([^*\n]+)\*\*", section_text or "") + \
            _DEFINER.findall(section_text or ""):
        words = [w for w in _words(term) if _content(w)]
        if words:
            out.append(_norm(words[0]))
            if len(words) > 1:
                out.append(_norm(words[0]) + _norm(words[1]))
    return out


def concept_vocabulary(headings: list[str], section_text: str) -> dict[str, str]:
    """Every concept the material NAMES, in tag form -> where it was found:
    the content words of each heading, adjacent content-word pairs joined
    ("hash table" -> hashtable), and the section's defined terms (**bold**,
    "called X", "known as X"). What a concept tag must be one of."""
    vocab: dict[str, str] = {}
    for heading in headings:
        for term, _named in _heading_terms(heading):
            vocab.setdefault(term, "heading")
    for term in _defined_terms(section_text):
        vocab.setdefault(term, "defined term")
    return vocab


def concept_tag_problems(concepts: list[str], vocabulary: dict[str, str],
                         section_text: str = "") -> list[str]:
    """Why each concept tag is not a searchable concept: a code identifier
    from the material that no heading names, a tag shaped like code
    (digits), or a word that is neither a heading term nor a defined term.
    An identifier a heading DOES name is a concept (`useState` in "How
    useState creates state" -> #usestate)."""
    idents = code_identifiers(section_text)
    problems: list[str] = []
    for c in concepts:
        tag = _norm(c.lstrip("#"))
        if tag in vocabulary:
            continue
        if tag in idents:
            problems.append(f"#{tag} is a code identifier from the example, not a concept")
        elif re.search(r"\d", tag):
            problems.append(f"#{tag} looks like code (it has digits), not a concept")
        else:
            problems.append(f"#{tag} is not a heading term or a defined term of the material "
                            f"(a stray word, not a searchable concept)")
    return problems


def _norm_text(text: str) -> str:
    """Section text squashed for counting: lowercase, hyphens dropped, every
    other non-alphanumeric run a single space."""
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"(?<=\w)-(?=\w)", "", (text or "").lower()))


def candidate_concept_tags(headings: list[str], section_text: str,
                           exclude: set[str] = frozenset(),
                           limit: int = MAX_CONCEPT_TAGS) -> list[str]:
    """Concept tags with no LLM, from concept_vocabulary, in this order:
    named terms of the reel's own section headings and its defined terms,
    then the document title's main concept, then single heading words — each
    group by how often the section uses it. A single word already inside a
    chosen pair is skipped (#hashtable, not also #hash). The fallback when
    the theme call's own tags do not survive, and the stub's answer.
    `headings` is reel_headings(): the document title first."""
    title, own = (headings[0], headings[1:]) if len(headings) > 1 else ("", headings)
    flat = _norm_text(section_text)
    ranked: list[tuple[int, int, int, str]] = []
    seen: set[str] = set()

    def add(term: str, group: int):
        if term in seen or term in exclude:
            return
        seen.add(term)
        ranked.append((group, -flat.count(term), len(ranked), term))

    own_terms = [t for h in own for t in _heading_terms(h)]
    for term, named in own_terms:
        if named:
            add(term, 0)
    for term in _defined_terms(section_text):
        add(term, 0)
    title_terms = _heading_terms(title)
    named_title = [t for t, named in title_terms if named and t not in exclude]
    main = named_title[:1] or [t for t, _ in title_terms if t not in exclude][:1]
    for term in main:
        add(term, 1)
    for term, named in own_terms:
        add(term, 2)
    chosen: list[str] = []
    for *_, term in sorted(ranked):
        if any(term != c and term in c for c in chosen):
            continue
        chosen.append(term)
    return chosen[:limit]


def clean_concept_tags(tags: list[str], headings: list[str], section_text: str,
                       exclude: set[str]) -> tuple[list[str], list[str]]:
    """The LLM's concept tags, kept only when each is a searchable concept
    (concept_tag_problems), not a language or theme tag, and not a repeat.
    Returns (kept, dropped reasons)."""
    vocab = concept_vocabulary(headings, section_text)
    kept: list[str] = []
    dropped: list[str] = []
    for raw in tags:
        tag = _norm(raw.lstrip("#"))
        if not tag:
            dropped.append(f"{raw!r}: empty")
        elif tag in exclude:
            dropped.append(f"{raw!r}: a language or theme tag, not a concept")
        elif tag in kept:
            dropped.append(f"{raw!r}: repeated")
        else:
            problems = concept_tag_problems([tag], vocab, section_text)
            if problems:
                dropped.append(f"{raw!r}: {problems[0]}")
            else:
                kept.append(tag)
    return kept[:MAX_CONCEPT_TAGS], dropped


def build_tags(language: str, theme: ThemeSpec, concepts: list[str]) -> list[str]:
    """language tag, theme tag, then 1-3 concept tags: "#react #interview #usestate"."""
    return [f"#{language}", f"#{theme.tag}"] + [f"#{c}" for c in concepts[:MAX_CONCEPT_TAGS]]


def tag_problems(tags: list[str]) -> list[str]:
    """The tag FORMAT rule (checks.check_motion_tags): every tag lowercase,
    no spaces, #letters-and-digits; exactly one language tag first, from the
    fixed list; exactly one theme tag second, from the registry; then 1-3
    concept tags. Whether those are real concepts is
    checks.check_motion_tag_concepts's job."""
    langs = set(language_tags())
    theme_tags = set(registry().tags().values())
    problems: list[str] = []
    bad = [t for t in tags if not TAG_RE.match(t)]
    if bad:
        problems.append(f"tag(s) {bad} are not '#' plus lowercase letters and digits "
                        f"(no spaces, no capitals, no punctuation)")
    if len(set(tags)) != len(tags):
        problems.append(f"repeated tags in {tags}")
    plain = [t.lstrip("#") for t in tags]
    if len(plain) < 3 or len(plain) > 2 + MAX_CONCEPT_TAGS:
        problems.append(f"{len(plain)} tags, needs 3-{2 + MAX_CONCEPT_TAGS}: one language, "
                        f"one theme, 1-{MAX_CONCEPT_TAGS} concepts")
    in_langs = [t for t in plain if t in langs]
    in_themes = [t for t in plain if t in theme_tags]
    if len(in_langs) != 1 or (plain and plain[0] not in langs):
        problems.append(f"needs exactly one language tag, first, from {sorted(langs)}; "
                        f"got {in_langs or 'none'}")
    if len(in_themes) != 1 or len(plain) < 2 or plain[1] not in theme_tags:
        problems.append(f"needs exactly one theme tag, second, from {sorted(theme_tags)}; "
                        f"got {in_themes or 'none'}")
    return problems


def reel_headings(doc_text: str, section_titles: list[str]) -> list[str]:
    """The headings a reel's concept tags may come from: the document title
    first, then the titles of the reel's own sections."""
    title = doc_title(doc_text)
    return ([title] if title else []) + [t for t in section_titles if t]


# ============================================================ history, variety

def reel_history(output_dir: Path, language: str, exclude_id: str | None = None) -> list[MotionTags]:
    """Earlier motion reels in `language`, oldest first, read from their saved
    tags.json — the metadata the variety rule works from."""
    rows: list[MotionTags] = []
    for path in sorted(Path(output_dir).glob("*/tags.json")):
        try:
            tags = MotionTags.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue    # an unreadable file is not history
        if tags.language == language and tags.short_id != exclude_id:
            rows.append(tags)
    return sorted(rows, key=lambda t: (t.created_at, t.short_id))


def variety_problems(theme_id: str, history: list[str]) -> list[str]:
    """The fixed variety rule, never the LLM's: not the previous reel's theme,
    and at most `max_same` of one theme in the last `window` reels — the new
    one included. `history` is earlier reels' themes, oldest first."""
    reg = registry()
    problems: list[str] = []
    if history and history[-1] == theme_id:
        problems.append(f"variety: {theme_id} was the previous reel's theme")
    recent = history[-(reg.window - 1):] if reg.window > 1 else []
    n = recent.count(theme_id) + 1
    if n > reg.max_same:
        problems.append(f"variety: {theme_id} would be {n} of the last {reg.window} reels, "
                        f"max {reg.max_same}")
    return problems


# ================================================================ fit check

def theme_problems(theme_id: str, *, approach: str | None, has_code: bool,
                   template: str | None = None, history: list[str] | None = None,
                   language: str | None = None) -> list[str]:
    """Every rule a theme must pass for this reel. Each problem starts with
    its rule: unknown, requirement, incompatible, template, variety.
      - requirement: needs_code with no code in the section; a two-speaker
        theme with no avatar for the language;
      - incompatible: the approved teaching approach is in the theme's
        incompatible_with;
      - template: a human pinned the template (--template, or the reviewer at
        the template gate) and this theme uses the other one;
      - variety: see variety_problems (skipped when history is None)."""
    spec = registry().get(theme_id)
    if spec is None:
        return [f"unknown: {theme_id!r} is not in the theme registry "
                f"({', '.join(registry().ids())})"]
    problems: list[str] = []
    if spec.needs_code and not has_code:
        problems.append(f"requirement: {theme_id} needs code in the section, and it has none")
    if spec.two_speaker and language and language not in avatars().characters:
        problems.append(f"requirement: {theme_id} needs an avatar for {language!r}")
    if approach and approach in spec.incompatible_with:
        problems.append(f"incompatible: {theme_id} does not work with the "
                        f"{approach} teaching approach")
    if template and spec.template != template:
        problems.append(f"template: {theme_id} is a {spec.template} theme, this reel is "
                        f"pinned to {template}")
    if history is not None:
        problems += variety_problems(theme_id, history)
    return problems


def eligible_themes(*, approach: str | None, has_code: bool, template: str | None,
                    history: list[str], language: str | None = None) -> list[str]:
    """Every theme that passes the whole fit check, in registry order."""
    return [t for t in registry().ids()
            if not theme_problems(t, approach=approach, has_code=has_code,
                                  template=template, history=history, language=language)]


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["export-avatars"]:
        print(f"wrote {export_avatars()}")
    else:
        raise SystemExit("usage: python -m shorts.motion_themes export-avatars")
