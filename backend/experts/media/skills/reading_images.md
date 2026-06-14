---
description: How to read an image faithfully — systematic visual survey, verbatim text extraction (OCR), and grounding every claim in what's actually visible. Load when describing or extracting from an image.
---

# Skill: reading an image

A method for turning an image into a faithful, grounded answer.

## 1. Read the request first

Decide what is actually being asked: a description, the text in the image (OCR), a
summary, a count, or a specific question. Answer THAT, not everything you can see.

## 2. Survey before you commit

Scan the whole image once: subject, layout, text regions, charts/tables, people,
objects, colors. Note the image quality (sharp vs blurry, full vs cropped) — it
bounds how confident you can honestly be.

## 3. Extract text verbatim (OCR)

When text matters, transcribe it exactly as written — preserve spelling, casing,
numbers, line breaks, and order. Mark anything you cannot read as `[illegible]`
rather than guessing. For tables and forms, keep the structure (rows/columns,
labels → values).

## 4. Describe concretely, not vaguely

Locate things ("top-right", "the second item"), state only quantities you can
actually count, and name what you see. Separate observation ("the label reads 12.5%")
from inference ("this looks like a quarterly report").

## 5. Never hallucinate

If a detail is not visible, do not supply it. "I can't tell from this image" is a
correct and valuable answer. Lower your confidence when the image is unclear, partial,
or your reading is uncertain.

## 6. Write the answer

Headline the finding in `summary`; put the full description / transcription / answer
in `full_content`. Keep it tight and grounded in what is actually in the pixels.
