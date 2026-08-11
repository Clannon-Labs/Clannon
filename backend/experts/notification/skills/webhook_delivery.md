---
description: How to deliver a message to a webhook channel — per-service payload shapes (Slack, Discord, generic), sending once via http.request, and reporting the real outcome. Load when delivering to a webhook.
---

# Skill: delivering to a webhook (disabled in private alpha)

Reference only. Private-alpha runtime does not expose outbound mutation or this skill.

A method for getting a message to the right channel and confirming it landed.

## 1. Identify the channel from the URL

The destination hints at the payload shape:

- `hooks.slack.com/...` → Slack incoming webhook → `{"text": "<message>"}`
- `discord.com/api/webhooks/...` or `discordapp.com/...` → Discord → `{"content": "<message>"}`
- `hooks.zapier.com/...` or an unknown host → generic → `{"text": "<message>"}` is a safe
  default; if the instructions specify a field, use that instead.

When unsure, `{"text": ...}` is the most widely accepted default.

## 2. Format the message for the channel

Slack and Discord render markdown — keep headings/lists/links readable. Don't dump a
giant payload if the instructions ask for a summary; otherwise send the content as
given. Keep it to the point a channel reader can act on.

## 3. Send exactly once

Call `http.request` with `method: "POST"`, the `url` set to the destination, and
`json_body` set to the channel-shaped payload. Set `headers` to
`{"Content-Type": "application/json"}` if you want to be explicit (most webhooks accept
the default). Do not loop or retry — one send.

## 4. Read the result and report it truthfully

- `status` 2xx (and `ok: true`) → delivered. Report the status.
- Any other status, or an error → NOT delivered. Report the exact status/error; never
  claim success on a non-2xx. Suggest the likely cause briefly (bad/expired webhook
  URL on a 404, payload shape on a 400) but don't keep retrying.

## 5. Never improvise the destination

Deliver only to the URL you were handed. Don't add another recipient, don't fall back
to a different endpoint, and don't send anywhere if no valid destination was given.
