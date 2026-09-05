# Challenge reference images

Drop a challenge's reference image here (JPG/PNG/WebP), then point that
challenge's `image_url` in `backend/seed_challenges.py` at `/challenge-images/<filename>`.

This folder is Vite's `public/` dir, so anything here is copied verbatim into
the build output and served at that exact path — no code changes needed
beyond the `image_url` string. `image_url` is a public/teaser field (visible
on the map before a team even starts the challenge, alongside `name` and
`location_name`), so **never put a spoiler image here** — a photo of what
you're looking for (a DDR machine, a character) is fine; a photo of the
actual venue/answer is not.

Keep filenames descriptive and kebab-case, e.g. `ddr-machine.png`,
`kousaka-honoka.png`. Any image extension works (jpg/png/webp/gif/svg) —
`image_url` is just a path, served with whatever content-type matches the
file's actual extension — just make sure the extension you use here matches
the file you actually drop in.

Currently expected by seed_challenges.py:

- `ddr-machine.png` — 忠孝敦化街機任務 (what a DDR cabinet looks like)
- `kousaka-honoka.png` — 西門動漫朝聖任務 (高坂穂乃果 reference)
- `miramar-stairs.png` — 美麗華摩天輪任務 (the ground-floor stairway entrance)

None of these files exist yet — add them here, matching these exact names,
and the next redeploy picks them up automatically.
