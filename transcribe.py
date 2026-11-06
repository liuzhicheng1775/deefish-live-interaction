"""Transcribe Chinese audio and translate to English with faster-whisper."""
import sys
import time

from faster_whisper import WhisperModel

MODEL = sys.argv[1] if len(sys.argv) > 1 else "small"
AUDIO = "audio.m4a"


def fmt(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def main() -> None:
    t0 = time.time()
    model = WhisperModel(MODEL, device="cpu", compute_type="int8")
    print(f"model={MODEL} loaded in {time.time() - t0:.1f}s", flush=True)

    segments, info = model.transcribe(
        AUDIO,
        task="translate",  # Chinese speech -> English text, timestamps preserved
        language="zh",
        vad_filter=True,
        beam_size=5,
    )
    print(
        f"detected language={info.language} prob={info.language_probability:.2f} "
        f"duration={info.duration:.1f}s",
        flush=True,
    )

    rows = []
    for i, seg in enumerate(segments, 1):
        text = seg.text.strip()
        print(f"[{fmt(seg.start)} -> {fmt(seg.end)}] {text}", flush=True)
        rows.append((i, seg.start, seg.end, text))

    with open("output.srt", "w", encoding="utf-8") as f:
        for i, start, end, text in rows:
            f.write(f"{i}\n{fmt(start)} --> {fmt(end)}\n{text}\n\n")

    with open("output.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(text for _, _, _, text in rows))

    print(f"DONE segments={len(rows)} elapsed={time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
