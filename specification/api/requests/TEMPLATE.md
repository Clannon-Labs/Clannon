# <one line: what the route does>

```
From:     frontend
To:       backend
Date:     YYYY-MM-DD
Status:   OPEN          # OPEN | DONE | BLOCKED | NEEDS DISCUSSION
Blocking: no            # yes = frontend work has actually stopped
```

## What UI this unblocks

What the user sees that they cannot see today. One or two sentences. This is what
lets the backend judge priority and push back on the shape if there is a cheaper one.

## Proposed route

| | |
|---|---|
| Method | `GET` |
| Path | `/example/{id}` |
| Auth | required / none |
| Query params | `?foo=` — what it filters |

## Request

```ts
// body shape, or "none — query params only"
```

## Response

```ts
type ExampleResponse = {
  id: string;
  // field names are the backend's JSON names, not camelCased guesses
};
```

## Failure cases the UI needs to distinguish

| Case | Expected | Why the UI cares |
|---|---|---|
| Not found / not owned | 404 | non-disclosure — must look identical to unknown |
| Empty result | `[]` + 200 | renders "nothing yet", not an error state |

Say explicitly when the UI **cannot** tell two states apart with the proposed shape.
That is usually the real design question, and it is cheaper to answer now than after
it ships.

## How the frontend is coping meanwhile

Which mock in `src/lib/api/mock.ts`, or which UI is stubbed. Confirms work continued.

---

<!-- backend appends below this line; do not edit the section above -->
