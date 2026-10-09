# Motion voices: a proposal for review

Nothing here has been recorded or downloaded. This page is for you to decide which voices to use; you then supply the clips.

## The smallest set that works: 4 voices

| Voice slot | Who uses it | Why it is separate |
|---|---|---|
| `motion_narrator` | every one-narrator reel (classic_explainer, narrative, bug_hunt, myth_vs_fact, common_mistakes, predict_the_output, under_the_hood, step_by_step_walkthrough, real_world_scenario, before_vs_after) | the series' own voice |
| `motion_host` | the grey **host** identity, the asking role in every two-speaker reel (INTERVIEWER, PEER_A, STUDENT) | must differ from every character, so two speakers always sound like two people |
| `motion_char_1` | 8 of the 15 language identities (below) | first character voice |
| `motion_char_2` | the other 7 language identities | second character voice, clearly different from voice 1 |

- **Fewer still: 3 voices.** The host also narrates (`motion_narrator` = `motion_host`). This works because a narrator and the host never speak in the same reel. The cost: the solo reels and the interviews sound like the same person.
- **The registry rule:** the four slots must all differ (`shorts/motion_identities.py` refuses a repeat), so any two-speaker reel always has two distinct voices.

### Slots belong to identities (phase 3 badges, approved 4-slot plan)

There are no drawn characters any more. The speaker of a two-speaker reel is the reel's **language identity**, and the identity carries the voice. `shorts/motion_identities.yaml` sets this:

```yaml
voices:
  narrator: motion_narrator
  host: motion_host
  character_1: motion_char_1
  character_2: motion_char_2
```

Each language picks `voice: character_1` or `voice: character_2`:

| `character_1` → `motion_char_1` | `character_2` → `motion_char_2` |
|---|---|
| Python, TypeScript, React, Django, CSS, SQL, C++, CS | JavaScript, Node, HTML, Java, C, Docker, OS |

**To change it:**
1. Edit a language's `voice:` in `shorts/motion_identities.yaml`.
2. Put the clips at `voices/motion/<slot>.wav`.
3. Run `python -m shorts.motion_identities export`.

Until a slot's clip exists, the reel falls back to the project's current clips: `voices/interviewer.wav` for the narrator and the host, and `voices/student.wav` for the two character slots. Every fallback is logged.

## What each Chatterbox reference clip needs

Chatterbox ([resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox), MIT licence) clones from one short reference clip. Its README uses a ~10 s clip in its example and gives no hard minimum. These are working requirements:

- **Length:** 10–15 s of continuous speech. Under ~6 s the voice drifts; over ~20 s adds little.
- **One speaker only.** No music, no background noise or hum, and no room echo; record in a quiet, soft-furnished room.
- **Clean level:** no clipping, speech peaking around -6 dBFS, and less than 0.3 s of silence at the start and end.
- **Format:** WAV, mono, 24 kHz or higher, 16-bit. The pipeline resamples to 24 kHz.
- **Delivery = output.** Chatterbox copies pace and energy. Read in the tone you want the reels to have: clear, friendly, mid-paced. For a fast speaker, the README suggests `cfg_weight ≈ 0.3` (`CHATTERBOX_CFG_WEIGHT`).
- **Language:** English, matching the reels.
- **Content:** any natural sentences. Suggested script, about 12 s:
  > "Let's look at what really happens when this code runs. First the function is called, then the value is stored, and finally the screen updates. It's simpler than it looks."
- **Watermark:** every Chatterbox output carries Resemble AI's inaudible Perth watermark (README).

## Free sources with a clear licence for commercial educational use

Best first. This is not legal advice: confirm each licence on its official page before use. Even with a permissive dataset licence, cloning an identifiable real person's voice for a commercial product can raise consent and personality-rights issues.

1. **Record your own voices** (a teammate, with a signed voice release that covers commercial use and AI voice cloning). This is free, the rights are clearest, and you get the exact tone you want. Recommended.
2. **Synthetic seed voices from Kokoro**, which this project already installs. Kokoro-82M is Apache-2.0 per third-party listings such as [featherless.ai](https://featherless.ai/models/hexgrad/Kokoro-82M) and [tts.ai](https://tts.ai/voices/kokoro/?lang=ar). Generate 12 s reference clips with different Kokoro voices, then Chatterbox clones those.
   - No real person's identity is involved.
   - Check the official Hugging Face card for the voicepacks' own terms.
   - Expect slightly less natural results than human clips.
3. **LJSpeech**: public domain, one reader, from LibriVox ([keithito.com/LJ-Speech-Dataset](https://keithito.com/LJ-Speech-Dataset/)). No attribution is needed, but there is only one voice, and it is a real, identifiable reader.
4. **VCTK**: 109 speakers, CC BY 4.0 according to secondary sources ([datashare.ed.ac.uk](https://datashare.ed.ac.uk/handle/10283/2119?show=full)). Attribution is required, and the controlling terms should be checked on Edinburgh DataShare.
5. **LibriTTS-R**: CC BY 4.0 on [OpenSLR 141](https://www.openslr.org/141/). Some mirrors list CC BY-NC-ND in their metadata, so confirm on OpenSLR first.

Mozilla Common Voice (CC0) is legally simple, but its clips are short and often noisy. It is a poor fit for reference voices.
