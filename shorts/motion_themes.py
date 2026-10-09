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
        return self


class Avatar(BaseModel):
    id: str
    name: str
    look: str
    palette: AvatarPalette
    voice_slot: str

    @property
    def voice_path(self) -> str:
        return f"voices/motion/{self.voice_slot}.wav"


class AvatarRegistry(BaseModel):
    languages: list[str]
    host: Avatar
    characters: dict[str, Avatar]

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
        slots = [self.host.voice_slot] + [a.voice_slot for a in self.characters.values()]
        if len(set(slots)) != len(slots):
            problems.append("voice slots repeat — every character has its own voice")
        names = [self.host.name] + [a.name for a in self.characters.values()]
        if len(set(names)) != len(names):
            problems.append("character names repeat")
        if problems:
            raise ValueError("motion avatar registry: " + "; ".join(problems))
        return self


@lru_cache(maxsize=1)
def avatars() -> AvatarRegistry:
    data = yaml.safe_load(AVATARS_PATH.read_text(encoding="utf-8")) or {}
    host = Avatar(id="host", **{k: v for k, v in data["host"].items() if k != "id"})
    chars = {lang: Avatar(id=lang, **spec) for lang, spec in (data.get("characters") or {}).items()}
    return AvatarRegistry(languages=data.get("languages") or [], host=host, characters=chars)


def language_tags() -> list[str]:
    return list(avatars().languages)


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
}
#: Words that name a language in prose — counted, highest wins.
_NAME_PATTERNS = {
    "react": r"\bReact\b|\buse[A-Z]\w+\b|\bJSX\b",
    "python": r"\bPython\b",
    "javascript": r"\bJavaScript\b",
    "typescript": r"\bTypeScript\b",
    "html": r"\bHTML\b",
    "css": r"\bCSS\b",
    "sql": r"\bSQL\b",
    "java": r"\bJava\b(?!Script)",
    "cpp": r"\bC\+\+",
}


def detect_language(section_text: str, doc_text: str = "") -> tuple[str, str]:
    """The course language a reel is in, and how it was decided: the selected
    section's fenced code, then the document's, then a language named in the
    document's title, then the one named most often (twice or more), else `cs`. Deterministic, never the LLM. Pass
    --language to override it."""
    langs = set(language_tags())
    for where, text in (("section", section_text), ("document", doc_text)):
        for label in re.findall(r"^```\s*([\w+#-]+)", text or "", re.M):
            lang = _FENCE_LANGUAGES.get(label.lower())
            if lang in langs:
                return lang, f"the {where}'s ```{label} code"
    title = next(iter(re.findall(r"^#\s+(.+)$", doc_text or "", re.M)), "")
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

_STOPWORDS = frozenset("""
a an and are as at be because but by can do does each every for from has have how
if in into is it its just like more not of on or so that the their them then there
these this those to up was what when where which while who why will with without
you your why does doesnt dont plain actually value values way thing things one two
work works working update updates change changes changing make makes new old same
different other another first second simply really very also than
""".split())


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (word or "").lower())


def section_terms(text: str) -> set[str]:
    """Every word of the section in tag form, plus each adjacent pair joined
    ("plain variable" -> "plainvariable", "re-render" -> "rerender") — what a
    concept tag must be one of."""
    words = [_norm(w) for w in re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", text or "")]
    words = [w for w in words if w]
    return set(words) | {a + b for a, b in zip(words, words[1:])}


def candidate_concept_tags(section_title: str, section_text: str,
                           exclude: set[str] = frozenset(), limit: int = MAX_CONCEPT_TAGS) -> list[str]:
    """Concept tags taken from the section, with no LLM: code identifiers the
    section names (`useState`), its bold terms, and its title's words, ranked
    by how often the section uses them. The fallback when the theme call's own
    tags do not survive validation, and the stub's answer."""
    text = section_text or ""
    found: list[str] = []
    for span in re.findall(r"`([^`\n]+)`", text):
        m = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(.*\))?\s*", span)
        if m:
            found.append(m.group(1))
    found += re.findall(r"\*\*([^*\n]+)\*\*", text)
    found += re.findall(r"[A-Za-z][A-Za-z0-9-]+", section_title or "")
    flat = text.lower()
    scored: dict[str, int] = {}
    for raw in found:
        tag = _norm(raw)
        if (len(tag) < 3 or tag in _STOPWORDS or tag in exclude or tag in scored
                or not tag.isascii() or tag.isdigit()):
            continue
        spoken = raw.lower()
        scored[tag] = len(re.findall(rf"\b{re.escape(spoken)}\b", flat)) or 1
    ranked = sorted(scored, key=lambda t: -scored[t])
    return ranked[:limit]


def clean_concept_tags(tags: list[str], section_text: str, exclude: set[str]) -> tuple[list[str], list[str]]:
    """The LLM's concept tags, kept only when each is (after lowercasing and
    removing spaces and punctuation) a word or word pair of the section, not a
    language or theme tag, and not a repeat. Returns (kept, dropped reasons)."""
    terms = section_terms(section_text)
    kept: list[str] = []
    dropped: list[str] = []
    for raw in tags:
        tag = _norm(raw.lstrip("#"))
        if not tag:
            dropped.append(f"{raw!r}: empty")
        elif tag in exclude:
            dropped.append(f"{raw!r}: a language or theme tag, not a concept")
        elif tag not in terms:
            dropped.append(f"{raw!r}: not taken from the section")
        elif tag in kept:
            dropped.append(f"{raw!r}: repeated")
        else:
            kept.append(tag)
    return kept[:MAX_CONCEPT_TAGS], dropped


def build_tags(language: str, theme: ThemeSpec, concepts: list[str]) -> list[str]:
    """language tag, theme tag, then 1-3 concept tags: "#react #interview #usestate"."""
    return [f"#{language}", f"#{theme.tag}"] + [f"#{c}" for c in concepts[:MAX_CONCEPT_TAGS]]


def tag_problems(tags: list[str], section_text: str | None = None) -> list[str]:
    """The tag format rule (checks.check_motion_tags): every tag lowercase,
    no spaces, #letters-and-digits; exactly one language tag first, from the
    fixed list; exactly one theme tag second, from the registry; then 1-3
    concept tags, each taken from the section when the section is given."""
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
    if section_text is not None:
        terms = section_terms(section_text)
        stray = [t for t in plain[2:] if t not in terms]
        if stray:
            problems.append(f"concept tag(s) {stray} are not taken from the section")
    return problems


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
