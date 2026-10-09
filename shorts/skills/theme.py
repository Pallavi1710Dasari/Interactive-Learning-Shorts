"""SKILL — motion theme (RESTYLE_TO_MOTION_REELS.md, phase 2b). REEL_STYLE=motion only.

WHERE THIS SITS. teaching_approach.py decided HOW the idea is explained
(analogy, comparison, code, ...). This step decides the FORMAT of the reel:
who speaks and what it feels like (an interview, two peers, a bug hunt, a
story). The two combine; neither replaces the other. The script is written
after this, to the chosen theme's beat template.

WHAT IS THE LLM'S AND WHAT IS NOT. The LLM judges FIT only: which of the
eligible themes best suits the section, its concept tags and the approved
approach. Everything else is a fixed rule in shorts/motion_themes.py:
requirements (code for predict_the_output), approaches the registry marks
incompatible, a template a human pinned, and VARIETY across earlier reels in
the same language. Those rules shrink the list before the call AND check the
pick after it. A rejected pick gets ONE retry with the reason; after that the
template's fallback (classic_explainer for fix_story) is used and the reason
logged.
"""
from .. import motion_themes as mt
from ..llm import ask_json
from ..schema import (MotionThemeChoice, MotionThemeDraft, Section, TeachingApproach,
                      ThemeFitCheck, ThemeRejection)

#: One retry after the first pick, then the fallback (user decision, phase 2b).
MAX_THEME_ATTEMPTS = 2

SYSTEM_MOTION_THEME = """You choose the THEME of ONE short vertical teaching reel.

The TEACHING APPROACH is already approved. It is HOW the idea is explained: an
analogy, a comparison, real code, a process shown step by step. The THEME is the
FORMAT of the reel: who speaks and what it feels like: an interview, two peers
talking it through, a bug hunt, a story. They combine. Keep the approved approach and
pick the format that carries it best.

Pick ONE theme, from ELIGIBLE THEMES only. Every other theme has already been ruled
out by fixed rules (what the section contains, approaches a theme cannot carry, and
variety across earlier reels), so never pick one that is not listed, and never pick
one just to be different: variety is already handled. Choose the theme that best
suits:
- what the SECTION actually teaches: its concept, whether it shows code, whether it
  corrects a wrong belief, describes a bug, or walks a process;
- the CONCEPT TAGS;
- the APPROVED TEACHING APPROACH (a theme that lists it under "works with" carries it
  most naturally).

Also give 1 to 3 concept tags: SEARCHABLE CONCEPTS someone would look up, such as
"usestate", "rerender", "tokenization", "pagetable". Each is one lowercase word, or
two words joined with no space, taken from the material's HEADINGS or its DEFINED
TERMS (CONCEPT TERMS below lists them). Never a variable or function name the
example happens to use ("setcount", "likes"), never a filler word. Not the language,
not the theme.

Return JSON:
{"theme": "<an id from ELIGIBLE THEMES>",
 "reason": "one or two sentences: why this format fits this section and approach",
 "concept_tags": ["...", "..."]}"""


def _theme_line(spec: mt.ThemeSpec) -> str:
    who = " / ".join(spec.roles) if spec.two_speaker else "one narrator"
    return (f"- {spec.id} [template {spec.template}; {who}; needs code: "
            f"{'yes' if spec.needs_code else 'no'}]\n"
            f"    {spec.description}\n"
            f"    suits: {'; '.join(spec.suits)}\n"
            f"    works with: {', '.join(spec.works_with) or 'any approach'}\n"
            f"    hook: {spec.hook.brief}")


def _user_prompt(section: Section, source_text: str, approach: TeachingApproach | None,
                 language: str, concept_tags: list[str], history: list[str],
                 eligible: list[str], vocabulary: list[str]) -> str:
    reg = mt.registry()
    if approach is not None:
        combined = f" (with {', '.join(approach.combined_with)})" if approach.combined_with else ""
        approach_line = f"{approach.primary}{combined}" + (
            f" — {approach.rationale}" if approach.rationale else "")
    else:
        approach_line = "none approved"
    return "\n".join([
        f"SECTION {section.section_id}: {section.title}",
        f"MATERIAL:\n{source_text}",
        f"\nLANGUAGE: {language}",
        f"APPROVED TEACHING APPROACH: {approach_line}",
        f"CONCEPT TAGS (from the section): {', '.join(concept_tags) or 'none found'}",
        f"CONCEPT TERMS (headings and defined terms): {', '.join(vocabulary) or 'none'}",
        "EARLIER REELS IN THIS LANGUAGE (oldest first): "
        + (", ".join(history) if history else "none"),
        "\nELIGIBLE THEMES:",
        *(_theme_line(reg.themes[t]) for t in eligible),
    ])


def choose_theme(section: Section, *, source_text: str, approach: TeachingApproach | None,
                 language: str, history: list[str], template_pin: str | None = None,
                 override: str | None = None, headings: list[str] | None = None,
                 log=print) -> MotionThemeChoice:
    """Choose this reel's theme.

    `source_text` is the selected section's own evidence (what "the section"
    means for requirements and tags). `history` is the earlier reels' themes
    in the same language, oldest first (motion_themes.reel_history).
    `template_pin` is a template a human chose (--template or the reviewer);
    None lets the theme decide the template. `override` is --theme.
    `headings` (the document title and the reel's section titles; default
    the section's own title) are where concept tags may come from, with the
    section's defined terms.

    Raises ValueError when --theme names a theme that is unknown, needs what
    the section lacks, or does not work with the approved approach — those
    are not judgement calls, and a script written to them would fail its
    graders. Variety alone a human may overrule; that is logged."""
    reg = mt.registry()
    kind = approach.primary if approach is not None else None
    has_code = mt.section_has_code(source_text)
    exclude = set(mt.language_tags()) | set(reg.tags().values())
    headings = headings if headings is not None else [section.title]
    candidates = mt.candidate_concept_tags(headings, source_text, exclude)

    def problems(theme_id: str) -> list[str]:
        return mt.theme_problems(theme_id, approach=kind, has_code=has_code,
                                 template=template_pin, history=history, language=language)

    def done(theme_id: str, reason: str, source: str, fit: ThemeFitCheck,
             concepts: list[str], eligible: list[str]) -> MotionThemeChoice:
        spec = reg.themes[theme_id]
        return MotionThemeChoice(
            theme=theme_id, reason=reason, source=source, fit_check=fit,
            tags=mt.build_tags(language, spec, concepts or candidates),
            template=spec.template, language=language, teaching_approach=kind,
            eligible=eligible)

    eligible = mt.eligible_themes(approach=kind, has_code=has_code, template=template_pin,
                                  history=history, language=language)

    # ------------------------------------------------------------ --theme
    if override:
        found = problems(override)
        hard = [p for p in found if not p.startswith("variety:")]
        if hard:
            raise ValueError(f"--theme {override} cannot be used here: " + "; ".join(hard))
        relaxed = [f"{p} (relaxed by --theme)" for p in found]
        for r in relaxed:
            log(f"  theme: {r}")
        fit = ThemeFitCheck(passed=True, overrides=relaxed)
        return done(override, "chosen by the reviewer (--theme)", "flag", fit, candidates,
                    eligible)

    # ------------------------------------------------- nothing / one left
    fallback = reg.fallback[template_pin or "fix_story"]
    if not eligible:
        why = "no theme passed the fit check (requirements, compatibility, template, variety)"
        log(f"  theme: {why} — falling back to {fallback}")
        fit = ThemeFitCheck(passed=False, fallback=True, fallback_reason=why,
                            overrides=[f"{p} (fallback)" for p in problems(fallback)])
        return done(fallback, f"fallback: {why}", "fallback", fit, candidates, eligible)
    if len(eligible) == 1:
        fit = ThemeFitCheck(passed=True)
        return done(eligible[0], "the only theme that passes the fit check", "only_candidate",
                    fit, candidates, eligible)

    # ------------------------------------------------------- the fit call
    vocabulary = [t for t in mt.concept_vocabulary(headings, source_text) if t not in exclude]
    base = _user_prompt(section, source_text, approach, language, candidates, history,
                        eligible, vocabulary)
    user = base
    rejected: list[ThemeRejection] = []
    for attempt in range(1, MAX_THEME_ATTEMPTS + 1):
        draft = ask_json(SYSTEM_MOTION_THEME, user, MotionThemeDraft, max_tokens=500,
                         label="motion_theme")
        found = problems(draft.theme)
        if not found:
            kept, dropped = mt.clean_concept_tags(draft.concept_tags, headings, source_text,
                                                  exclude)
            for d in dropped:
                log(f"  theme: concept tag dropped — {d}")
            fit = ThemeFitCheck(passed=True, attempts=attempt, rejected=rejected)
            return done(draft.theme, draft.reason.strip() or "(no reason given)", "llm",
                        fit, kept, eligible)
        rejected.append(ThemeRejection(theme=draft.theme, attempt=attempt, problems=found))
        log(f"  theme: pick {attempt} {draft.theme!r} rejected — {'; '.join(found)}")
        user = (base + f"\n\nYOUR PREVIOUS PICK {draft.theme!r} WAS REJECTED: "
                + "; ".join(found) + "\nPick again, from ELIGIBLE THEMES only.")

    why = (f"the fit call's picks failed the fit check twice "
           f"({'; '.join(f'{r.theme}: {r.problems[0]}' for r in rejected)})")
    log(f"  theme: {why} — falling back to {fallback}")
    fit = ThemeFitCheck(passed=False, attempts=MAX_THEME_ATTEMPTS, rejected=rejected,
                        fallback=True, fallback_reason=why,
                        overrides=[f"{p} (fallback)" for p in problems(fallback)])
    return done(fallback, f"fallback: {why}", "fallback", fit, candidates, eligible)
