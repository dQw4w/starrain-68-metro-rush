# Challenge reference images

Drop a challenge's reference image here (JPG/PNG/WebP), then point that
challenge's `image_url` in `backend/seed_challenges.py` at `/challenge-images/<filename>`.

This folder is Vite's `public/` dir, so anything here is copied verbatim into
the build output and served at that exact path — no code changes needed
beyond the `image_url` string. `image_url` is hidden until a team's attempt
is approved to start — it's shown alongside the task description, not on
the map pin/teaser — so **never put a spoiler image here** — a photo of what
you're looking for (a DDR machine, a character) is fine; a photo of the
actual venue/answer is not.

Keep filenames descriptive and kebab-case, e.g. `ddr-machine.png`,
`kousaka-honoka.png`. Any image extension works (jpg/png/webp/gif/svg) —
`image_url` is just a path, served with whatever content-type matches the
file's actual extension — just make sure the extension you use here matches
the file you actually drop in.

Currently expected by seed_challenges.py:

- `ddr-machine.png` — 明曜百貨任務 (what a DDR cabinet looks like) ✅ already here
- `takamatsu-tomori.png` — 西門町任務, `image_url` (高松燈 reference)
- `tennoji-rina.png` — 西門町任務, `image_url_2` (天王寺璃奈 reference —
  this challenge accepts merch of either character, so both photos show)
- `miramar-stairs.png` — 美麗華任務 (the ground-floor stairway entrance)
- `morse-code.png` — 南港區民活動中心任務 (the Morse code reference chart —
  this one is task material, not just a hint: the team decodes against it)
- `matra-train.png` — 木柵機廠任務, `image_url` (馬特拉列車)
- `bombardier-train.png` — 木柵機廠任務, `image_url_2` (龐巴迪列車)
- `lin-garden-inscription.png` — 林本源園邸任務 (the 題字 the team memorises
  at the gate and then hunts for inside — task material, not just a hint)

The 木柵機廠 description says 左圖 = 馬特拉 and 右圖 = 龐巴迪, and the modal
renders `image_url` on the left, `image_url_2` on the right — so those two
can't be swapped without rewriting the description.

Add the missing ones here, matching these exact names, and the next
redeploy picks them up automatically.
