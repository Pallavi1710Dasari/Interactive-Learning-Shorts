"""
RESTYLE_TO_STORY_REELS.md Step 7 Part 2/3: unit tests for shorts/story_audio.py
and its story_voices.py voice-resolution layer.

No API key, no network, no real provider calls — every test runs under
SHORTS_STUB=1, where story_voices.synth_raw() returns a silent WAV of the
estimated length instead of calling Kokoro/Chatterbox for real (see that
function's own STUB branch). The one real, local, free thing exercised here
is story_voices.list_kokoro_voices() / validate_cast_voices("kokoro") — that
just enumerates this machine's installed Kokoro voice catalogue, no
synthesis, no network.

    SHORTS_STUB=1 python -m shorts.story_audio_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import contextlib
import io
import json
import shutil
import subprocess
import wave
from pathlib import Path

from shorts import config, story_audio, story_voices
from shorts.schema import Character, ConceptMapping, Shot, StoryScript
from shorts.tts import ffmpeg_exe

SHORT_ID = "stub_audio_test"


def _tiny_story(short_id: str = SHORT_ID) -> StoryScript:
    """
    A deliberately small, self-contained 3-shot story (one scene shot per
    acting character + one cta) — small enough to paste verbatim into a
    reply, but real enough to exercise render_shot_audio's two duration
    branches: a long-enough line where the AUDIO drives final_duration, and
    a cta whose overlay_text is read by the Narrator (Step 7 Part 2's own
    "including text_card/recap/cta Narrator lines" rule).
    """
    mapping = [ConceptMapping(
        concept_rule="state resets on every re-render unless you persist it",
        source_quote="Local variables inside a component function are reset on every render.",
        actor="Rahul",
        metaphor_event="Rahul's counter snaps back to zero every time he blinks",
        visible_proof="the number on screen visibly resets to 0",
        lesson_line="State resets unless you persist it.",
    )]
    shots = [
        Shot(shot_id="s1", kind="scene", characters=["Rahul"], framing="medium",
             action="Rahul stares at the screen, arms crossed, jabbing the button again.",
             line="Five clicks. Still zero? This makes absolutely no sense to me at all!",
             emotion="frustrated", concept_ref=mapping[0].concept_rule,
             story_beat="problem",
             source_quote=mapping[0].source_quote),
        Shot(shot_id="s2", kind="scene", characters=["Riya"], framing="two_shot",
             action="Riya leans over and points calmly at the flickering counter.",
             line="Look closer. The counter resets every single time you call it fresh.",
             emotion="calm", concept_ref=mapping[0].concept_rule,
             story_beat="reaction",
             source_quote=mapping[0].source_quote),
        Shot(shot_id="s3", kind="cta", characters=[],
             action="", overlay_text="Try it yourself — follow along!",
             emotion="friendly"),
    ]
    return StoryScript(
        short_id=short_id, session_id="sess1", source_section_id="sec1",
        question="Why does my counter keep resetting?",
        estimated_seconds=30.0,
        cast=[Character(name="Rahul"), Character(name="Riya")],
        mapping=mapping, system_name="React", setting="a cluttered dev desk",
        props=["laptop"], hook_line="Five clicks. Still zero?",
        card_facts=["State resets unless persisted"],
        shots=shots, lessons=[mapping[0].lesson_line],
    )


def _write_story(short_id: str = SHORT_ID) -> StoryScript:
    story = _tiny_story(short_id)
    shutil.rmtree(config.OUTPUT_DIR / short_id, ignore_errors=True)
    path = config.OUTPUT_DIR / f"{short_id}.story.json"
    path.write_text(story.model_dump_json(indent=2), encoding="utf-8")
    return story


def _run_capture(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*a, **kw)
    return result, buf.getvalue()


# Same disposable-cache reasoning as story_frames_test.py's own top-level
# shutil.rmtree(...) of .image_cache — a PREVIOUS run of this file left a
# real cache on disk, content-addressed by (provider, voice, text, params);
# without clearing it, "was synth_raw actually called" assertions below
# would be false negatives from run 2 onward.
shutil.rmtree(story_audio.AUDIO_CACHE_DIR, ignore_errors=True)


# ============================================================ voice mapping

def test_kokoro_cast_voices_are_all_valid():
    story_voices.validate_cast_voices("kokoro")
    catalogue = set(story_voices.list_kokoro_voices())
    for name in story_voices.CAST_ROLES:
        vid = config.CAST_KOKORO_VOICE.get(name, "")
        assert vid and vid in catalogue, (name, vid)
    print(f"   ok — every CAST_KOKORO_VOICE id (all 4 roles) exists in the "
         f"installed Kokoro catalogue ({len(catalogue)} voices): "
         f"{config.CAST_KOKORO_VOICE}")


def test_invalid_kokoro_voice_fails_clearly_naming_the_character():
    original = dict(config.CAST_KOKORO_VOICE)
    config.CAST_KOKORO_VOICE["Rahul"] = "not_a_real_voice_id"
    try:
        try:
            story_voices.validate_cast_voices("kokoro")
            assert False, "should have raised VoiceError"
        except story_voices.VoiceError as e:
            assert "Rahul" in str(e) and "not_a_real_voice_id" in str(e), str(e)
            print(f"   ok — an invalid Kokoro voice id fails clearly, naming "
                 f"the character and the bad id: {e}")
    finally:
        config.CAST_KOKORO_VOICE.clear()
        config.CAST_KOKORO_VOICE.update(original)


def test_chatterbox_with_no_clips_configured_fails_naming_every_character():
    status = story_voices.list_chatterbox_status()
    if not status["installed"]:
        print(f"   skipped — chatterbox not installed here: {status['reason']}")
        return
    original = dict(config.CAST_CHATTERBOX_VOICE)
    for name in story_voices.CAST_ROLES:
        config.CAST_CHATTERBOX_VOICE[name] = ""
    try:
        try:
            story_voices.validate_cast_voices("chatterbox")
            assert False, "should have raised VoiceError"
        except story_voices.VoiceError as e:
            for name in story_voices.CAST_ROLES:
                assert name in str(e), (name, str(e))
            print(f"   ok — chatterbox with no reference clips configured "
                 f"fails, naming all 4 roles at once: {e}")
    finally:
        config.CAST_CHATTERBOX_VOICE.clear()
        config.CAST_CHATTERBOX_VOICE.update(original)


def test_voice_for_unknown_provider_raises():
    try:
        story_voices.voice_for("Rahul", "not_a_provider")
        assert False, "should have raised VoiceError"
    except story_voices.VoiceError as e:
        print(f"   ok — an unknown TTS_PROVIDER_STORY raises clearly: {e}")


# ======================================================== emotion param lookup

def test_params_for_kokoro_uses_the_emotion_speed_table():
    p = story_audio._params_for("kokoro", "frustrated")
    assert p == {"speed": config.EMOTION_DELIVERY["frustrated"]["kokoro_speed"]}
    print(f"   ok — _params_for('kokoro', 'frustrated') -> {p}")


def test_params_for_chatterbox_uses_exaggeration_and_cfg_weight():
    p = story_audio._params_for("chatterbox", "calm")
    delivery = config.EMOTION_DELIVERY["calm"]
    assert p == {"exaggeration": delivery["chatterbox_exaggeration"],
                "cfg_weight": delivery["chatterbox_cfg_weight"]}
    print(f"   ok — _params_for('chatterbox', 'calm') -> {p}")


def test_params_for_unknown_emotion_falls_back_to_default():
    p = story_audio._params_for("kokoro", "not_a_real_emotion")
    assert p == {"speed": config.EMOTION_DELIVERY_DEFAULT["kokoro_speed"]}
    print(f"   ok — an unrecognized emotion falls back to EMOTION_DELIVERY_DEFAULT: {p}")


# ================================================================= cache hit

def test_synth_cached_hits_cache_on_second_call():
    calls = {"n": 0}
    original = story_voices.synth_raw

    def counting_synth_raw(*a, **kw):
        calls["n"] += 1
        return original(*a, **kw)

    story_voices.synth_raw = counting_synth_raw
    try:
        text = "This exact sentence is unique to the cache hit test."
        raw1 = story_audio.synth_cached("Rahul", text, "neutral", "kokoro")
        raw2 = story_audio.synth_cached("Rahul", text, "neutral", "kokoro")
    finally:
        story_voices.synth_raw = original

    assert calls["n"] == 1, f"expected exactly 1 underlying synth call, got {calls['n']}"
    assert raw1 == raw2
    print(f"   ok — synth_cached calls story_voices.synth_raw exactly once "
         f"for two identical (provider, voice, text, params) requests "
         f"(calls={calls['n']})")


def test_cache_key_changes_with_text_voice_or_params():
    k1 = story_audio._cache_key("kokoro", "am_puck", "hello", {"speed": 1.0})
    k2 = story_audio._cache_key("kokoro", "am_puck", "goodbye", {"speed": 1.0})
    k3 = story_audio._cache_key("kokoro", "af_heart", "hello", {"speed": 1.0})
    k4 = story_audio._cache_key("kokoro", "am_puck", "hello", {"speed": 1.1})
    assert len({k1, k2, k3, k4}) == 4
    print("   ok — the cache key changes with text, voice, and params independently")


# ============================================================ final_duration

def test_ordinary_short_shot_uses_the_planned_floor():
    shot = Shot(shot_id="s_short", kind="scene", characters=["Rahul"],
               action="a blink", line="Wait.", emotion="confused")
    record = story_audio.render_shot_audio(SHORT_ID, shot, "kokoro")
    assert record["final_duration"] == shot.duration_seconds, record
    print(f"   ok — a short line's final_duration ({record['final_duration']}s) "
         f"is the planned floor (shot.duration_seconds={shot.duration_seconds}s), "
         f"not the (shorter) raw audio length")


def test_ordinary_long_shot_is_driven_by_audio_length_plus_buffer():
    shot = Shot(shot_id="s_long", kind="scene", characters=["Riya"],
               action="a long explanation",
               line=("This is a deliberately long sentence with plenty of words "
                    "so that the stub-synthesized audio length plus a quarter "
                    "second buffer ends up longer than the planned estimate."),
               emotion="calm")
    record = story_audio.render_shot_audio(SHORT_ID, shot, "kokoro")
    from shorts.schema import WORDS_PER_SECOND
    words = len(shot.line.split())
    audio_len = max(0.6, words / WORDS_PER_SECOND + 0.3)
    expected = max(shot.duration_seconds, round(audio_len + 0.25, 3))
    assert abs(record["final_duration"] - expected) < 0.01, (record, expected)
    assert record["final_duration"] > shot.duration_seconds, (
        "this test is only meaningful if the audio-driven value actually wins")
    print(f"   ok — a long line's final_duration ({record['final_duration']}s) is "
         f"audio_len+0.25s ({round(audio_len + 0.25, 3)}s), which exceeds the "
         f"planned estimate ({shot.duration_seconds}s) — the max() picks it")


def test_cta_keeps_planned_minimum_without_the_buffer_but_never_truncates():
    short_cta = Shot(shot_id="s_cta_short", kind="cta", characters=[],
                     action="", overlay_text="Go!", emotion="friendly")
    record = story_audio.render_shot_audio(SHORT_ID, short_cta, "kokoro")
    assert record["final_duration"] == short_cta.duration_seconds, record
    print(f"   ok — a short cta's final_duration ({record['final_duration']}s) is "
         f"exactly its planned floor, no +0.25s buffer applied")

    long_cta = Shot(shot_id="s_cta_long", kind="cta", characters=[],
                    action="",
                    overlay_text=("Try it yourself, follow along, and see the "
                                  "exact same reset happen on your own screen too!"),
                    emotion="friendly")
    record2 = story_audio.render_shot_audio(SHORT_ID, long_cta, "kokoro")
    from shorts.schema import WORDS_PER_SECOND
    words = len(long_cta.overlay_text.split())
    audio_len = max(0.6, words / WORDS_PER_SECOND + 0.3)
    assert record2["final_duration"] >= round(audio_len, 3) - 0.01, record2
    assert record2["final_duration"] > long_cta.duration_seconds, (
        "this test is only meaningful if the real audio outran the planned floor")
    print(f"   ok — a cta whose overlay_text outruns its planned floor "
         f"({long_cta.duration_seconds}s) stretches to cover the real audio "
         f"({record2['final_duration']}s) rather than truncating it")


# ================================== timings.json / final_duration / mix
#
# These three checks are naturally sequential (run() must happen once
# before any of them can be checked) so they live in ONE test rather than
# three separately-ordered ones — main()'s test loop runs tests in
# ALPHABETICAL order, not definition order, so splitting them across
# separately-named functions would make correctness depend on their names
# sorting the right way, which is exactly the kind of fragile coupling
# worth avoiding here.

def test_run_produces_timings_final_durations_and_a_normalized_mix():
    _write_story()
    code, out = _run_capture(story_audio.run, SHORT_ID, "kokoro")
    assert code == 0, out

    timings_path = config.OUTPUT_DIR / SHORT_ID / "timings.json"
    timings = json.loads(timings_path.read_text(encoding="utf-8"))
    assert set(timings.keys()) == {"s1", "s2", "s3"}, timings.keys()
    for shot_id, rec in timings.items():
        assert set(rec.keys()) == {"start", "end", "final_duration", "words"}, rec
        assert isinstance(rec["start"], (int, float))
        assert isinstance(rec["end"], (int, float))
        assert rec["end"] > rec["start"]
        assert abs((rec["end"] - rec["start"]) - rec["final_duration"]) < 0.01
        for w in rec["words"]:
            assert set(w.keys()) == {"word", "start", "end"}, w
            assert w["end"] >= w["start"]
    # shots are laid out back to back with STORY_SHOT_AUDIO_GAP between them
    assert abs(timings["s2"]["start"] - timings["s1"]["end"] - config.STORY_SHOT_AUDIO_GAP) < 0.01
    print(f"   ok — timings.json has exactly the 3 shot ids, each with "
         f"{{start, end, final_duration, words[]}}, shots spaced by the "
         f"{config.STORY_SHOT_AUDIO_GAP}s gap:\n{json.dumps(timings, indent=2)}")

    story_path = config.OUTPUT_DIR / f"{SHORT_ID}.story.json"
    story = StoryScript.model_validate_json(story_path.read_text(encoding="utf-8"))
    for shot in story.shots:
        assert shot.final_duration_seconds is not None, shot.shot_id
        assert shot.final_duration_seconds > 0
    print(f"   ok — story.json's own shots now carry final_duration_seconds: "
         f"{[(s.shot_id, s.final_duration_seconds) for s in story.shots]}")

    mix_path = config.OUTPUT_DIR / SHORT_ID / "audio" / "mix.wav"
    with wave.open(str(mix_path), "rb") as w:
        assert w.getframerate() == story_audio.MIX_SAMPLE_RATE, (
            "loudnorm must not silently upsample the mix — see story_audio._mix's "
            "own explicit -ar note")
        assert w.getnchannels() == 1
        mix_duration = w.getnframes() / w.getframerate()
    expected = max(t["end"] for t in timings.values())
    assert abs(mix_duration - expected) < 0.2, (mix_duration, expected)
    print(f"   ok — mix.wav is mono at the pinned {story_audio.MIX_SAMPLE_RATE}Hz "
         f"(loudnorm did not upsample it), duration {mix_duration:.2f}s matches "
         f"the last shot's end ({expected:.2f}s)")


def test_music_ducking_produces_a_mixed_track_of_matching_duration():
    exe = ffmpeg_exe()
    if exe is None:
        print("   skipped — no ffmpeg available")
        return
    _write_story()
    code, out = _run_capture(story_audio.run, SHORT_ID, "kokoro")
    assert code == 0, out
    mix_path = config.OUTPUT_DIR / SHORT_ID / "audio" / "mix.wav"

    music_path = config.OUTPUT_DIR / SHORT_ID / "_test_music.wav"
    subprocess.run([exe, "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=8",
                   "-ar", str(story_audio.MIX_SAMPLE_RATE), "-ac", "1", str(music_path)],
                  capture_output=True, check=True)

    original_music_path = config.MUSIC_PATH
    config.MUSIC_PATH = str(music_path)
    try:
        with wave.open(str(mix_path), "rb") as w:
            speech_duration = w.getnframes() / w.getframerate()
        out_path = story_audio._duck_music(mix_path, mix_path.parent, exe)
    finally:
        config.MUSIC_PATH = original_music_path

    assert out_path.exists()
    with wave.open(str(out_path), "rb") as w:
        duration = w.getnframes() / w.getframerate()
    assert abs(duration - speech_duration) < 0.3, (duration, speech_duration)
    print(f"   ok — mix_with_music.wav is produced (music ducked to "
         f"{config.MUSIC_DUCK_DB}dB) with duration ({duration:.2f}s) matching "
         f"the speech track ({speech_duration:.2f}s), not the (longer) music bed")
    music_path.unlink(missing_ok=True)
    out_path.unlink(missing_ok=True)


# ==================================================== >80s -> NEEDS_REVIEW

def test_over_budget_reel_is_marked_needs_review_without_rewriting_the_script():
    short_id = "stub_audio_needs_review"
    story = _write_story(short_id)
    original_max = config.STORY_MAX_TOTAL_SECONDS
    config.STORY_MAX_TOTAL_SECONDS = 5.0   # this 3-shot story easily runs longer
    try:
        code, out = _run_capture(story_audio.run, short_id, "kokoro")
    finally:
        config.STORY_MAX_TOTAL_SECONDS = original_max

    assert code == 0, out   # never a hard failure — see the PART 2 spec
    assert "NEEDS_REVIEW" in out
    assert "not auto-rewriting the script" in out
    status_path = config.OUTPUT_DIR / short_id / "audio" / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "NEEDS_REVIEW"
    assert status["total_seconds"] > status["max_seconds"] == 5.0
    print(f"   ok — a reel over STORY_MAX_TOTAL_SECONDS finishes with exit "
         f"code 0 (never crashes) and is marked NEEDS_REVIEW without "
         f"rewriting the script: {status}")


def test_under_budget_reel_is_marked_ok():
    short_id = "stub_audio_ok"
    _write_story(short_id)
    code, out = _run_capture(story_audio.run, short_id, "kokoro")
    assert code == 0, out
    status_path = config.OUTPUT_DIR / short_id / "audio" / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "OK"
    assert "status: OK" in out
    print(f"   ok — a reel within STORY_MAX_TOTAL_SECONDS "
         f"({config.STORY_MAX_TOTAL_SECONDS}s) is marked OK: {status}")


# =================================== STEP 8 Part 1 — real word timings

class _FakeWord:
    def __init__(self, start, end):
        self.start, self.end = start, end


class _FakeSegment:
    def __init__(self, words):
        self.words = words


def _fake_transcribe(detected_starts_ends):
    """A drop-in for faster_whisper.WhisperModel.transcribe: one segment
    holding one _FakeWord per (start, end) pair, matching the real API's
    (segments, info) return shape closely enough for _whisper_words."""
    def transcribe(path, word_timestamps=True, initial_prompt=None,
                   language="en", beam_size=1):
        words = [_FakeWord(s, e) for s, e in detected_starts_ends]
        return [_FakeSegment(words)], None
    return transcribe


def test_whisper_words_pairs_real_boundaries_with_our_own_known_words():
    text = "Five clicks still zero"
    fake_model = type("M", (), {"transcribe": staticmethod(
        _fake_transcribe([(0.0, 0.4), (0.401, 0.812), (0.9123, 1.2), (1.3, 1.777)]))})()

    original = story_audio._load_whisper_model
    story_audio._load_whisper_model = lambda: fake_model
    try:
        words = story_audio._whisper_words(Path("/dev/null"), text)
    finally:
        story_audio._load_whisper_model = original

    assert words is not None
    assert [w.word for w in words] == text.split()
    # ROUNDED TO 3 DECIMALS — Step 8 Part 1's own rule, and proof these are
    # REAL detected boundaries (0.9123 -> 0.912), not an even split.
    assert words[2].start == 0.912, words[2].start
    assert words[1].end == 0.812, words[1].end
    print(f"   ok — _whisper_words pairs whisper's own real detected "
         f"boundaries with OUR known words positionally, rounded to 3 "
         f"decimals: {[(w.word, w.start, w.end) for w in words]}")


def test_whisper_words_falls_back_to_none_on_word_count_mismatch():
    text = "Five clicks still zero"
    fake_model = type("M", (), {"transcribe": staticmethod(
        _fake_transcribe([(0.0, 0.4), (0.4, 0.8)]))})()   # only 2, text has 4

    original = story_audio._load_whisper_model
    story_audio._load_whisper_model = lambda: fake_model
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            words = story_audio._whisper_words(Path("/dev/null"), text)
    finally:
        story_audio._load_whisper_model = original

    assert words is None
    assert "don't line up" in buf.getvalue()
    print("   ok — a whisper/known-text word-count mismatch returns None "
         "(never guesses a pairing) and prints why")


def test_whisper_words_falls_back_to_none_on_an_exception():
    def raising(*a, **kw):
        raise RuntimeError("model exploded")

    original = story_audio._load_whisper_model
    story_audio._load_whisper_model = raising
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            words = story_audio._whisper_words(Path("/dev/null"), "hello there")
    finally:
        story_audio._load_whisper_model = original

    assert words is None
    assert "faster-whisper failed" in buf.getvalue()
    print("   ok — a whisper exception is caught, never raised, and returns "
         "None with a printed reason")


def test_word_timings_falls_back_to_even_split_with_a_warning_when_whisper_fails():
    original_stub = config.STUB
    original_whisper = story_audio._whisper_words
    config.STUB = False
    story_audio._whisper_words = lambda wav_path, text: None
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            words = story_audio._word_timings(Path("/dev/null"), "hi there", 2.0)
    finally:
        config.STUB = original_stub
        story_audio._whisper_words = original_whisper

    expected = story_audio._even_words("hi there", 0.0, 2.0)
    assert words == expected
    print(f"   ok — when whisper fails (outside SHORTS_STUB), _word_timings "
         f"falls back to the even-split approximation: {words}")


def test_word_timings_never_attempts_whisper_under_stub():
    calls = {"n": 0}
    original_whisper = story_audio._whisper_words

    def counting(*a, **kw):
        calls["n"] += 1
        return None

    story_audio._whisper_words = counting
    try:
        assert config.STUB, "this test must run under SHORTS_STUB=1"
        words = story_audio._word_timings(Path("/dev/null"), "hi there", 2.0)
    finally:
        story_audio._whisper_words = original_whisper

    assert calls["n"] == 0
    assert words == story_audio._even_words("hi there", 0.0, 2.0)
    print("   ok — _word_timings never calls whisper under SHORTS_STUB=1 "
         "(the silent stub audio has nothing for it to find) — even split "
         "used directly, 0 whisper calls")


def test_word_timings_caches_the_whisper_result_by_cache_key():
    calls = {"n": 0}
    original_stub = config.STUB
    original_whisper = story_audio._whisper_words
    config.STUB = False
    key = "test_word_timing_cache_key_12345"
    (story_audio.AUDIO_CACHE_DIR / f"{key}.words.json").unlink(missing_ok=True)

    def counting(wav_path, text):
        calls["n"] += 1
        from shorts.schema import WordTiming
        return [WordTiming(word=w, start=float(i), end=float(i) + 0.5)
               for i, w in enumerate(text.split())]

    story_audio._whisper_words = counting
    try:
        w1 = story_audio._word_timings(Path("/dev/null"), "hi there", 2.0, cache_key=key)
        w2 = story_audio._word_timings(Path("/dev/null"), "hi there", 2.0, cache_key=key)
    finally:
        config.STUB = original_stub
        story_audio._whisper_words = original_whisper
        (story_audio.AUDIO_CACHE_DIR / f"{key}.words.json").unlink(missing_ok=True)

    assert calls["n"] == 1, "the second call must be a cache hit, not a re-transcription"
    assert [w.model_dump() for w in w1] == [w.model_dump() for w in w2]
    print("   ok — _word_timings caches a real whisper result by cache_key — "
         "identical audio reused across shots (e.g. recap/cta lines) is "
         "only ever transcribed once")


def test_resolved_cache_key_reflects_the_actually_resolved_provider():
    original = dict(config.CAST_CHATTERBOX_VOICE)
    config.CAST_CHATTERBOX_VOICE["Rahul"] = ""   # force a fallback to kokoro
    try:
        key_requested_chatterbox = story_audio._resolved_cache_key(
            "Rahul", "a test line", "neutral", "chatterbox")
        key_requested_kokoro = story_audio._resolved_cache_key(
            "Rahul", "a test line", "neutral", "kokoro")
    finally:
        config.CAST_CHATTERBOX_VOICE.clear()
        config.CAST_CHATTERBOX_VOICE.update(original)

    assert key_requested_chatterbox == key_requested_kokoro, (
        "a chatterbox request that resolves (falls back) to kokoro must "
        "share kokoro's own cache key, not a separate 'chatterbox' one for "
        "audio that was never actually produced by chatterbox")
    print("   ok — _resolved_cache_key keys by the ACTUALLY RESOLVED "
         "provider: a chatterbox request that falls back to kokoro shares "
         "kokoro's own cache entry rather than mislabeling kokoro audio as "
         "chatterbox's")


# ============================================= STEP 9 FIX 1 — recap join

def test_recap_join_strips_trailing_punctuation_before_joining():
    """Every lesson ending in '.', '!', '?', or nothing at all — the joined
    result must contain no '..', no '. .', and no '!.' anywhere, ending in
    exactly one '.'."""
    shot = Shot(shot_id="s_recap", kind="recap", characters=[], action="",
               card_lines=["Ends in period.", "Ends in bang!",
                          "Ends in question?", "No punctuation at all"])
    text = story_audio.spoken_text(shot)
    assert text is not None
    for bad in ("..", ". .", "!.", "?."):
        assert bad not in text, (bad, text)
    assert text.endswith(".") and not text.endswith("..")
    print(f"   ok — lessons ending in '.', '!', '?', or nothing join with no "
         f"double punctuation and end in exactly one '.': {text!r}")


def test_recap_join_handles_a_single_card_line():
    shot = Shot(shot_id="s_recap", kind="recap", characters=[], action="",
               card_lines=["Only one lesson here."])
    text = story_audio.spoken_text(shot)
    assert text == "Only one lesson here."
    print(f"   ok — a single card_line still ends in exactly one '.': {text!r}")


def test_recap_join_with_no_card_lines_returns_none():
    shot = Shot(shot_id="s_recap", kind="recap", characters=[], action="", card_lines=[])
    assert story_audio.spoken_text(shot) is None
    print("   ok — a recap shot with no card_lines at all returns None, unchanged")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} story_audio tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL STORY_AUDIO TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
