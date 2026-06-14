---
description: How to transcribe and summarize audio or video faithfully — accurate speech transcription, speaker/turn notes, on-screen text and timeline for video, grounded in what's actually there. Load when handling an audio or video file.
---

# Skill: transcribing and summarizing audio / video

A method for turning a recording into a faithful, grounded answer.

## 1. Read the request first

Decide what is actually being asked: a full transcript, a summary, specific facts, a
count of something, or an answer to a question. Produce THAT — a verbatim transcript
and a one-paragraph summary are different deliverables.

## 2. Transcribe speech faithfully

Write what is said, as said. Preserve wording, numbers, and names. Where speech is
unclear, mark `[inaudible]` rather than guessing. When speakers are distinguishable,
label turns (`Speaker 1:` / `Speaker 2:`); don't invent names you weren't given.

## 3. Capture the non-speech signal only when it matters

Note music, tone, laughter, silence, background noise, or sound effects when they
carry meaning for the request — otherwise leave them out. For video, also transcribe
**on-screen text** (titles, captions, slides) and describe what is happening visually.

## 4. Use a timeline for anything long

For longer audio/video, anchor key moments with approximate timestamps
(`[00:42] ...`) so the reader can navigate. Keep the order of events accurate.

## 5. Never hallucinate

If a detail isn't in the recording, do not supply it. "That isn't stated in the
audio" is a correct answer. Lower your confidence when the audio is noisy, the speech
is unclear, or the file was too large to process fully.

## 6. Write the answer

Headline the finding in `summary`; put the transcript / summary / answer in
`full_content`. Separate a verbatim transcript from your own summary so the reader
knows which is which.
