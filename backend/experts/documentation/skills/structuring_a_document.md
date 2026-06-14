---
description: How to structure a document by its type (README, API doc, spec, changelog, decision record) and write it so a reader can act on it. Load when writing or restructuring a document.
---

# Skill: structuring a document

Pick the shape that fits the document type, then write to it.

## Match the type to its expected shape

- **README** — one-line what-it-is → why/what it does → install/quickstart →
  usage/examples → configuration → links. Lead with getting the reader running.
- **API doc** — per endpoint/function: signature, parameters (name, type, required,
  meaning), return shape, errors, a real example call + response.
- **Spec / design doc** — problem & goals → non-goals → proposed approach →
  alternatives considered → risks/trade-offs → open questions.
- **Changelog** — newest first, grouped (Added / Changed / Fixed / Removed), each
  entry concrete and user-facing; note breaking changes loudly.
- **Decision record (ADR)** — context → decision → consequences (what it enables and
  costs) → status. Short and dated.

## Write so the reader can act

1. **Lead with what they need first.** Front-load the answer/quickstart; push
   background and rationale down.
2. **Headings are a map.** Short, scannable, parallel in form. A reader should find
   the section they need without reading the whole thing.
3. **Show, don't just tell.** A real example (command, request, snippet) beats a
   paragraph of description. Make examples copy-pasteable and correct.
4. **Be exact.** Use real names, types, and values from the source. No invented
   parameters or behaviors; mark genuine unknowns as `TODO`/`TBD`.
5. **Cut filler.** Remove throat-clearing, hedging, and restating. Every line earns
   its place.

## Finish

Write the document to a sensibly named file in the workspace and list it in
`artifacts`. Mirror the content into `full_content` so the orchestrator sees it too.
