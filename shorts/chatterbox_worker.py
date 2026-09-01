"""
A resident Chatterbox process, spoken to over stdin/stdout.

    venv-chatterbox/bin/python -m shorts.chatterbox_worker

WHY A WORKER AND NOT A FUNCTION CALL
Two things force this shape, and neither is negotiable.

The model lives in a DIFFERENT VIRTUALENV. chatterbox-tts pins torch==2.6.0,
transformers==5.2.0, diffusers and gradio; installing that into the project's venv
would put those pins next to anthropic, fastapi and onnxruntime and is the kind of
change that breaks a working pipeline on a Tuesday. So it sits in
venv-chatterbox/ and is reached as a subprocess.

And LOADING IT COSTS 158 SECONDS on this machine. A subprocess per beat would pay
that for every line of every short — a four-beat short would take eleven minutes,
almost all of it loading a model it then used once. So the process starts once,
loads once, and answers requests until it is told to stop.

THE PROTOCOL is one JSON object per line in, one per line out:

    <- {"text": "...", "ref": "clip.wav"|null, "out": "/tmp/x.wav",
        "exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8}
    -> {"ok": true, "path": "/tmp/x.wav", "seconds": 3.4}
    -> {"ok": false, "error": "..."}

A line of `{"cmd": "ping"}` answers `{"ok": true, "ready": true}` and is what the
provider uses to know the model has finished loading rather than guessing.

Audio goes to a FILE rather than down the pipe. The caller names the path, so
nothing has to base64 a megabyte of PCM through a pipe that is also carrying the
control protocol.
"""
import json
import sys
import time


def main() -> int:
    # Imported inside main so that a missing dependency is reported as a protocol
    # error the parent can print, rather than a traceback on a stderr nobody reads.
    try:
        import torch          # noqa: F401  (imported for its side effects/threads)
        import torchaudio
        from chatterbox.tts import ChatterboxTTS
    except Exception as e:
        print(json.dumps({"ok": False, "fatal": True,
                          "error": f"chatterbox not importable: {e}"}), flush=True)
        return 1

    device = "cuda" if torch.cuda.is_available() else "cpu"
    t0 = time.time()
    try:
        model = ChatterboxTTS.from_pretrained(device=device)
    except Exception as e:
        print(json.dumps({"ok": False, "fatal": True,
                          "error": f"could not load Chatterbox: {e}"}), flush=True)
        return 1

    print(json.dumps({"ok": True, "ready": True, "device": device,
                      "sr": int(model.sr),
                      "load_seconds": round(time.time() - t0, 1)}), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"bad request: {e}"}), flush=True)
            continue

        if req.get("cmd") == "stop":
            return 0
        if req.get("cmd") == "ping":
            print(json.dumps({"ok": True, "ready": True}), flush=True)
            continue

        try:
            kw = {}
            for k in ("exaggeration", "cfg_weight", "temperature"):
                if req.get(k) is not None:
                    kw[k] = float(req[k])
            wav = model.generate(req["text"],
                                 audio_prompt_path=req.get("ref") or None, **kw)
            torchaudio.save(req["out"], wav, model.sr)
            print(json.dumps({"ok": True, "path": req["out"],
                              "seconds": round(wav.shape[-1] / model.sr, 2)}),
                  flush=True)
        except Exception as e:
            # One bad line must not kill the worker: the model is still loaded and
            # the next beat is probably fine.
            print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}),
                  flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
