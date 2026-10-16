# Motion reels v5: simple steps, real voice, visuals that act it out (2026-10-13)

Your requests, in order:
- one step at a time;
- scenes hidden;
- a voice on new reels;
- visuals that explain by action, not text, and match the material;
- fewer, simpler steps;
- working side icons.

Everything ran in stub mode, with no paid calls and nothing committed. The
new reels were made in a scratch copy of `output/`.

## What to open

| URL | Server | What to check |
|---|---|---|
| http://localhost:5175/ | stub demo (scratch copy) | **Make a reel.** Upload a `.md` file, then one screen per step: Topic → Teaching approach → Language → Theme → Script → Your reel. It's free here, and the reel gets a **real recorded voice** (about 4 minutes on this computer). |
| http://localhost:5175/#reels | stub demo | **The feed:** the newest reel is on top and plays with its voice. Its side icons work: **unclear**, **mp4** (records an MP4), **redraw** (write a note and the visuals are redrawn), **replay**, and sound. |
| http://localhost:5173/#reels | real (`output/`) | Your reels; the same icons work here too. |
| http://localhost:5173/#motion-reel?src=/motion-audit/actions_preview.json | either | The five new action pieces, one per shot |
| http://localhost:5173/#motion-reel?src=/motion-audit/golden_usestate.json | either | A whole reel drawn in free mode with the new pieces (also `golden_tlb`, `golden_tokenization`, `golden_usestate_interview`) |

**Two things in your real `output/` came from your own use of 5173 today,
not from me:**
- **A test reel:** `stub_what_is_a_dynamic_web_application__motion`, from
  your upload at 10:18. It was made in stub mode, so it is silent.
- **An MP4 of your real reel:** `reel.mp4`, saved at 11:12.

Delete the test reel if you don't want it in the feed.

## 1. The steps, one at a time (screens 01–08)

**Upload → Topic → Teaching approach → Language → Theme → Script → Your reel**
- **One thing per screen.** Each step asks one thing, gives a one-line
  reason, and has one big **Continue**. A progress row at the top shows
  where you are.
- **Decided for you, with the recommended choice:** the setup (section and
  characters on), the template (the theme you pick decides it) and the
  scenes. The scenes are drawn and checked automatically and never shown.
- **The last screen** shows a checklist while it works: "Drawing the
  visuals", "Recording the voice — line 5 of 17", "Timing every word".
- **Costs before they're spent.** A paid step shows its cost on its button,
  for example "Write the script — up to $0.45" or "Looks good — make the
  reel (visuals up to $0.53, voice free)". In stub mode they all say free.
- **Language before Theme.** You listed Language after Theme. I put it
  first, because the theme step picks the characters and tags, and both
  depend on the language.

## 2. Voice on new reels

- **Why it was silent:** stub mode recorded silence on purpose.
- **Now:** every new reel is recorded with **Chatterbox**, the free voice
  that runs on this computer. That includes test reels. It takes about 9
  seconds a line, about 4 minutes a reel, and every word is then timed to
  the audio.
- **Silent reels:** only the automated tests stay silent, for speed. A reel
  that really is silent says **"Test reel: no voice"** in the feed.

## 3. Visuals that act the idea out (screens 10–14)

**The old way:** there was effectively one template, mostly text on cards.
Free mode always drew a code window (even with no code), the
"Rebuild / Unwatched / No re-run" icons, and text chips.

**Five new animated pieces** act the idea out (screen 11):

| Piece | What it acts out | Its actions |
|---|---|---|
| **app screen** | what the user sees: a tiny app | a finger taps the button; the number changes, or turns red and shakes when it shouldn't |
| **memory box** | what the computer keeps | a new value drops in; the box is wiped back to its start |
| **flow** | a process, cause and effect | something travels from step to step, and each step lights up |
| **compare** | wrong vs right (✗ / ✓) | the right side appears on the word that names the fix |
| **cycle** | something that repeats | a dot goes round and round the steps |

**New rules,** checked on every reel, so a reel that breaks them is redrawn:
- **Every shot acts something out:** a tap, a change, something travelling,
  a reset or a reveal. Text just appearing doesn't count.
- **At least half the shots** use one of the five pieces.
- **At most 12 words of text per shot**, as short labels. The captions
  already carry the sentence.
- **Code only where your material has code.**
- **Labels use words the shot says.**

**The AI scene writer** (real runs) now gets these as its first rule: show
it, don't write it, for a beginner watching with the sound off. It gets a
worked example and each piece's purpose.

**Free test mode** uses the pieces too:
- **The hook acts out the problem:** a tap that doesn't change the number
  (when the topic is something you click), or a value that goes wrong.
- **The payoff** shows the same picture working.

**Free mode can't really read your material.** It picks labels from what
the reel names (button names, code names, terms), so some labels are still
plain. See the free-mode reels on screens 12–14. Visuals that truly match
your material come from the AI scene writer in a real run, which needs your
paid test below.

## 4. Side icons (screens 20–23)

- **mp4** now works on motion reels too. It records the reel frame by frame
  with its voice, free, on this computer. The new reel took about 2 minutes
  (1,870 frames). Old reels' downloads work again: the built app they're
  recorded from was out of date, and I rebuilt it.
- **redraw** works on motion reels too. You write what the visuals should
  show; the scenes are redrawn with your note, checked, and re-timed to the
  **same** words and voice. It shows its cost first: free in test mode, up
  to about $0.53 in a real run.
- **unclear, replay and the sound state** work as before.
- **A bug fixed on the way:** a server on any port other than 8000 used to
  record MP4s from port 8000.

## Checks

- **Overlaps: none,** across 1,047 sampled moments. That covers:
  - the new UI-made reel;
  - 8 layout contexts with the new pieces (classic and Midnight Lab; one
    narrator, two speakers, with and without characters);
  - 4 whole free-mode reels;
  - your real reel.

  On the way, the sweep found and fixed a big counter drawn off-centre and
  a speaker tag over the takeaway list.
- **Scene checks:**
  - All 10 golden scripts pass all 9 scene checks with free-mode scenes.
  - **686 / 686** free combinations pass every scene check: every section
    of every material in `content/`, with every theme.
- **Tests:**
  - All **59** test modules pass.
  - Evals: **212 passed, 0 failed, 12 skipped** (the paid judge cases).
  - TypeScript is clean and the motion checks pass.
- **Tests changed** to the new rules:
  - the hook acts its problem out;
  - the language mark is optional on the hook, but still never after it;
  - two evals were rewritten for the new rules (E209, E222).

## Your paid test (one real reel)

This is the one thing I can't judge for you: how good the AI's visuals are
on your own material. Start the real server **without** stub mode, then make
one reel at http://localhost:5173/:

```
python -m shorts.server        # no SHORTS_STUB
cd web && npm run dev
```

- **Typical cost:** about **$0.66** per reel. At most about $1.85; the limit
  is $2.00 per reel.
- **Before spending,** each paid step shows its cost on its button.
- **Voice and timing** are free.

Watch it in the feed with the sound off. If a shot doesn't act its line out,
use **redraw** on it with a note.
