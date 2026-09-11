"""
SKILL 4 supplement — real photographs, for the handful of icons that name an
actual physical object rather than a mechanism.

THE COMPLAINT THIS ANSWERS: a reviewer watched the "why can't the CPU talk to
RAM directly" short and said the hand-drawn chip/memory pictograms read as
cartoonish — fine for a children's explainer, wrong for engineering-graduate
exam prep. A CPU is a real, photographable thing; drawing it as a rounded
rectangle with pins was never necessary the way it is for a page table or a
call stack, which do not have a "real photo" because they are not physical.

This is NOT the image-model path visuals.py's docstring warns against ("Image
models produce confident nonsense for page tables and flow diagrams"). Nothing
here is generated. Every file this module can return is a real photograph that
a person took of a real object, fetched from Wikimedia Commons, which needs no
API key and costs nothing to query or download.

CURATED, NOT SEARCHED AT RUNTIME. Letting the pipeline free-text-search Commons
per render would trade one failure mode (a cartoon chip) for a worse one (a
photo of the wrong thing, or of a diagram someone uploaded under a plausible
filename) with nobody reviewing what came back. So the only subjects this can
ever return a photo for are the five below, and each file title was chosen by
hand: searched, downloaded, and looked at before being hard-coded here. See
_COMMONS_FILES for the title, and the credit line (author + licence) that
close reading turned up.

FREE AND LOCAL AFTER THE FIRST FETCH, on purpose — the same bias layout.py's
own docstring records for drawing itself. A short gets rebuilt and re-rendered
many times as prompts change; re-downloading the same JPEG from Commons on
every one of those would be paying a real (if small) cost for something that
never changes, so the bytes are cached to disk keyed by filename and never
re-fetched once they exist.

MUST NEVER BLOCK OR CRASH A RENDER. layout.py has to keep producing a complete,
correct SVG with zero network access — someone re-rendering an already-built
unit offline is a normal, supported case, not an edge case — so every failure
here (no network, a timeout, Commons returning something odd) is swallowed and
answered with None, exactly like a missing pictogram name already falls back to
_pict_box rather than failing the whole frame.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from .. import config


@dataclass(frozen=True)
class PhotoAsset:
    path: Path
    attribution: str


#: subject -> (exact Commons file title, credit line).
#:
#: Every title here was verified three ways, not guessed: found through
#: https://commons.wikimedia.org/w/api.php?action=query&list=search&srnamespace=6,
#: downloaded with
#: `curl -sSL -o /tmp/x -w "%{http_code} %{size_download}\n" \
#:  "https://commons.wikimedia.org/wiki/Special:FilePath/<title>?width=800"`
#: (expecting 200 and a real byte count, not an HTML error page), and then looked
#: at — the downloaded image was read back and checked to actually be a plain,
#: uncluttered photo of the named thing, not a diagram, a chart, or a photo of
#: something else that happened to match the search term. Several first hits
#: failed that last check and were rejected before landing here: a blurry chip
#: shot on a wood table, a cluttered desk with a server buried under a keyboard,
#: an IBM 1403 line printer nobody would recognise as "a printer" any more.
_COMMONS_FILES: dict[str, tuple[str, str]] = {
    "chip":    ("2023 Intel Core i7 12700KF (5).jpg",
                "Intel Core i7-12700KF by Jacek Halicki, Wikimedia Commons, CC BY-SA 4.0"),
    "memory":  ("RAM Module (SDRAM-DDR4).jpg",
                "DDR4 RAM module by ElooKoN, Wikimedia Commons, CC BY-SA 4.0"),
    "disk":    ("35-Desktop-Hard-Drive.jpg",
                "Desktop hard disk drive by Evan-Amos, Wikimedia Commons, CC BY-SA 3.0"),
    "server":  ("Rack of Cisco Hyperflex HXAF 240c M5 nodes.jpg",
                "Server rack (Cisco HyperFlex nodes) by Btrs, Wikimedia Commons, CC BY-SA 4.0"),
    "printer": ("Epson-inkjet-printer.jpg",
                "Inkjet printer (Epson Stylus C45), Wikimedia Commons, CC BY-SA 3.0"),
}

#: subject -> (exact Commons file title, credit line), for the `analogy` template's
#: LEFT panel — see schema.Frame.analogy_subject.
#:
#: A DIFFERENT KIND OF SUBJECT THAN _COMMONS_FILES ABOVE, and worth keeping
#: separate rather than merged into one dict for that reason. Those five are the
#: THING BEING TAUGHT, photographed. These are never the thing being taught —
#: nothing in a real reading material is a stack of plates — they are a
#: physical object a learner already recognises, borrowed to stand in for one
#: that is not photographable (a call stack has no photo; a queue in a scheduler
#: has no photo). schema.Frame.analogy_caption is what keeps that borrowing
#: honest ("like a stack of plates", never "a stack IS a stack of plates").
#:
#: Verified the same three ways as _COMMONS_FILES and by the same discipline:
#: searched via commons.wikimedia.org's search API, downloaded and checked with
#: curl for a real 200 and a real byte count, then looked at. Rejected before
#: landing here: a close-up of a colourful plate stack cropped so tight it no
#: longer reads as a stack of anything (the ceramic dinner-plate stack below
#: reads as one from across a phone screen, the closeup does not), a rolodex
#: shot from directly behind that reads as a fan of paper rather than a rotary
#: card file, and a matryoshka SHOP DISPLAY — three shelves, dozens of dolls,
#: reflections in glass — where "five dolls nested inside each other" is not
#: the thing a viewer's eye would find in two seconds.
#:
#: FOUR MORE ADDED IN A LATER PASS (linked_list, tree, hash_table, graph), same
#: discipline, same rejections when a first hit failed the look-at-it check: a
#: bank-vault gate photo that read as "a vault door", not "labelled boxes each
#: mapped by a number" (the safe-deposit WALL below, shot flat-on with every
#: label legible, replaced it); an engraving of an oak tree, which is an
#: illustration and not a photograph, however tree-shaped; a second oak tree
#: photo so mossy and backlit the branching itself was hard to find in it; a
#: subway map defaced with a station worker's marker scrawl across the middle,
#: and a second one cropped so tight ("Manhattan" filling half the frame) that
#: it read as a logo rather than a network. `sorting` and `pointer` were
#: considered and dropped — no Commons photo of "books by height" or "a single
#: chain link" turned up that was not a cluttered antiquarian scan or a stock
#: photo of something else that happened to match the search words, and a
#: forced choice would have been exactly the "photo of the wrong thing" this
#: module's docstring warns a runtime search invites.
_ANALOGY_FILES: dict[str, tuple[str, str]] = {
    "stack":     ("Stack of dinner plates.jpg",
                  "Stack of dinner plates by Santeri Viinamäki, Wikimedia Commons, "
                  "CC BY-SA 4.0"),
    "queue":     ("Queue of people.jpg",
                  "Queue of people by mycurrency.com, Wikimedia Commons, CC BY-SA 4.0"),
    "cache":     ("Rolodex.agr.jpg",
                  "Rolodex by ArnoldReinhold, Wikimedia Commons, CC BY 2.5"),
    "recursion": ("DGJ 4705 - Russian Matryoshka (4312413546).jpg",
                  "Russian Matryoshka by Dennis G. Jarvis, Wikimedia Commons, "
                  "CC BY-SA 2.0"),
    "linked_list": ("Broad chain closeup.jpg",
                     "Broad chain by Toni Lozano, Wikimedia Commons, CC BY 2.0"),
    "tree":        ("Branches of an oak tree - geograph.org.uk - 2684599.jpg",
                     "Branches of an oak tree by Kim Traynor, Wikimedia Commons, "
                     "CC BY-SA 2.0"),
    "hash_table":  ("Zürich Switzerland-Safe-deposit-boxes-01.jpg",
                     "Safe deposit boxes, Zürich, by CEphoto/Uwe Aranas, "
                     "Wikimedia Commons, CC BY-SA 3.0"),
    "graph":       ("Official New York City Subway Map 2013 vc.jpg",
                     "Official New York City Subway Map by the Metropolitan "
                     "Transportation Authority of the State of New York, "
                     "Wikimedia Commons, CC BY 2.0"),
}

#: Short enough that a stalled Commons request cannot noticeably delay a build,
#: matching the timeout style already used in providers.py's TTS calls (a
#: `timeout=` kwarg on every requests call, never left to hang indefinitely).
_TIMEOUT = 5

_CACHE_DIR = config.OUTPUT_DIR / "photos"

_HEADERS = {"User-Agent": "learning-shorts/1.0 (educational video pipeline)"}


def _safe_filename(title: str) -> str:
    """Commons titles carry spaces and parentheses; a cache path should not."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", title)


def _fetch(entry: tuple[str, str] | None) -> Optional[PhotoAsset]:
    """
    The shared cache-then-fetch body BOTH curated dicts use, pulled out so
    adding the second dict (_ANALOGY_FILES) could not risk the first.

    None covers every failure the same way: subject not in the caller's
    curated dict (entry is None), already-cached read failing, no network, a
    timeout, a non-200, or a body that is not actually image bytes (Commons
    serves an HTML page instead of a redirect when a filename is wrong, and
    that page still comes back with status 200). The caller's job is to fall
    back to a drawn shape in every one of those cases, not to tell them apart.
    """
    if not entry:
        return None
    title, attribution = entry

    dest = _CACHE_DIR / _safe_filename(title)
    if dest.exists():
        try:
            if dest.stat().st_size > 0:
                return PhotoAsset(dest, attribution)
        except OSError:
            return None

    try:
        url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{requests.utils.quote(title)}?width=800"
        r = requests.get(url, timeout=_TIMEOUT, headers=_HEADERS)
        content_type = r.headers.get("content-type", "")
        if r.status_code != 200 or not content_type.startswith("image/") or not r.content:
            return None
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
    except Exception:
        return None

    return PhotoAsset(dest, attribution)


def photo_for(subject: str) -> Optional[PhotoAsset]:
    """A cached real photograph for one of the five curated HARDWARE subjects,
    or None — see _fetch for what None covers."""
    return _fetch(_COMMONS_FILES.get(subject))


def analogy_photo_for(subject: str) -> Optional[PhotoAsset]:
    """
    A cached real photograph for one of the curated ANALOGY subjects (stack,
    queue, cache, recursion, linked_list, tree, hash_table, graph), or None —
    see _fetch for what None covers, and _ANALOGY_FILES for why this is a
    second dict rather than an entry added to _COMMONS_FILES.

    Same cache directory as photo_for on purpose: the two dicts' keys never
    collide (they name different kinds of subject — "chip" is hardware,
    "stack" is an analogy, and nothing here has ever needed both a hardware
    photo and an analogy photo for the same word), and the filenames they map
    to are already namespaced by their own Commons titles, so a shared
    directory costs nothing and avoids a second cache root to keep warm.
    """
    return _fetch(_ANALOGY_FILES.get(subject))
