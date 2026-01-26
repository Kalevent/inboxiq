# 60‑Second Demo Video Plan (FFmpeg)

## Goal
Produce a clean 60‑second product demo video for InboxIQ using screen recordings and FFmpeg.

## Assets You’ll Need
- Screen recordings (1080p, 60fps recommended):
  - Homepage hero + dashboard overview
  - Connections → Connect Gmail/Outlook
  - Decision outcomes + queue
  - Training metrics tab
  - Use cases page (optional)
- Logo (SVG/PNG)
- Optional: music bed + voiceover

## Recommended Flow (60s total)
1. **0–6s** — Brand intro (logo + tagline)
2. **6–18s** — Unified intake (homepage hero + connections)
3. **18–32s** — Decision outcomes + queue
4. **32–44s** — Training metrics (account‑specific tuning)
5. **44–54s** — Use case page (healthcare or claims)
6. **54–60s** — CTA (Start free trial)

## Step 1 — Record Clips
Use your OS screen recorder or OBS.
- Record each section as separate clips.
- Keep the UI steady (no fast scrolling).
- Save clips as `.mp4` or `.mov`.

## Step 2 — Normalize Clips (resolution + fps)
Normalize everything to 1920x1080 @ 60fps:

```bash
ffmpeg -i clip1.mov -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" -r 60 clip1_1080.mp4
```

Repeat for all clips.

## Step 3 — Trim Each Clip
Trim each clip to target length:

```bash
ffmpeg -i clip1_1080.mp4 -ss 00:00:02 -t 00:00:06 -c copy clip1_trim.mp4
```

## Step 4 — Create Intro Slide (optional)
If you want a short intro slide:

```bash
ffmpeg -f lavfi -i color=c=black:s=1920x1080:d=6 -vf "drawtext=text='InboxIQ — AI Decision Engine':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2" intro.mp4
```

## Step 5 — Concatenate Clips
Create `concat_list.txt`:

```
file 'intro.mp4'
file 'clip1_trim.mp4'
file 'clip2_trim.mp4'
file 'clip3_trim.mp4'
file 'clip4_trim.mp4'
file 'clip5_trim.mp4'
```

Then:

```bash
ffmpeg -f concat -safe 0 -i concat_list.txt -c copy demo_raw.mp4
```

## Step 6 — Add Background Music (optional)

```bash
ffmpeg -i demo_raw.mp4 -i music.mp3 -filter_complex "[1:a]volume=0.15[a1];[0:a][a1]amix=inputs=2:duration=shortest" -c:v copy demo_music.mp4
```

## Step 7 — Add Voiceover (optional)

```bash
ffmpeg -i demo_raw.mp4 -i voiceover.wav -filter_complex "[1:a]volume=1.0[a1];[0:a][a1]amix=inputs=2:duration=shortest" -c:v copy demo_voice.mp4
```

## Step 8 — Export Final 60s Video

```bash
ffmpeg -i demo_raw.mp4 -t 60 -c:v libx264 -preset slow -crf 18 -c:a aac -b:a 192k inboxiq_demo_60s.mp4
```

## Optional: Add Captions
If you have `.srt` captions:

```bash
ffmpeg -i inboxiq_demo_60s.mp4 -vf "subtitles=captions.srt" inboxiq_demo_60s_captioned.mp4
```

## QC Checklist
- Audio levels consistent
- Text readable at 100% zoom
- No UI glitches or cursor noise
- 60s total duration

## Deliverables
- `inboxiq_demo_60s.mp4`
- Optional: `inboxiq_demo_60s_captioned.mp4`
