# Mobile layout revalidation — 2026-11-08

> The 2026-11-07 shots, page and manifest were removed once London and Paris became transport-only: [`cities-20261111`](../cities-20261111/index.html) is the current sweep. They remain in the history of PR #127 at `c7faf3b`.

Initial reproduction: PR #127, `cab9b3f37e94130e331819d952d8bd15b9775e2d`. Final patch integrates the concurrent zoom-dial/overlay updates through `82cc7c16ce79af2be55aa61a6703a3045fd2e53e` without overwriting them.

## Reproduction and causes

The manifest's eight warnings are **three at 320×640, three at 390×844, and two Shimbashi sheets (390×844 / 1280×800)**. They are not six 390px captures. At narrow widths, the seven controls consume the header's flex row and shrink the board below the intrinsic title/clock widths; `overflow:hidden` clips both. The existing control wrapping at 320px does not reserve space for the board.

The Shimbashi approach walks to the nearest free tile near the bottom of Tokyo. Opening a sheet adds a camera lift, but `clampFocus` immediately clamps that lift back to the unextended map boundary, leaving the player under the sheet.

## Changes

At viewport widths up to 600px, give the board its own full-width flex row. The controls keep their existing wrapping and sizes. With a sheet open, reserve its measured height plus 16px of bottom clearance in the camera clamp and lift (converted to map units by zoom). Closing the sheet reapplies the ordinary boundary. Movement routes, collision data, speed, keyboard/pad handling, language catalogue, and motion preferences are unchanged.

The width test now fails on visual warnings. A dedicated Shimbashi test follows Tokyo's spot order and checks the player with the same browser hit test used by the original evidence.

## Measured results

Local paired execution: **Chromium 141.0.7390.37 / Playwright 1.56.0**, Linux, Noto Sans CJK and Noto Color Emoji. This is a different browser from the original Chromium 153 / Playwright 1.63 capture; both sides of this comparison use the same local environment. The repository dependency configuration is unchanged.

| Check | Before | After |
|---|---:|---:|
| 320px header, three cities | 3 warnings | 0 |
| 390px header, three cities | 3 warnings | 0 |
| Shimbashi player/sheet, phone and desktop | 2 warnings | 0 |
| Total among 20 recaptured checks | 8 | 0 |

The other 12 width checks were clean on both sides. The two focused test methods intentionally report eight failing subtests before the fix (78.956s) and pass after it (78.940s). Screenshots were visually inspected after Japanese/emoji font setup.

Additional browser checks: 11 methods passed (124.174s), covering 11 languages, normal-speed keys/pad and blocked water tiles, reduced motion, signs, city/station tools, categories, favorites/home, no JavaScript, avatars, layers, and river/fire/bridge drawing. The school world also passed four browser checks (8.038s): phone/desktop layout, arrow keys/WASD and walls, phone pad, and header/home/settings/language tools. Both complete city spot sweeps (phone and desktop) passed in 394.282s, including route targets, water collision checks, sheet content, arrows, and real marker presses. In total, all 15 CitiesTests methods and the four selected SchoolTests methods passed.

Initial Python checks: 164 passed, 7 skipped, 1 subtest passed (5.17s): `test_world_classroom.py`, `test_world_places.py`, `test_world_motion.py`, `test_static_contract.py`, `test_visual_regression.py`.

## Evidence scope and provenance

Only the eight previously warned WebP files are replaced. `manifest.json` and the generated gallery now count **574 clean / 0 noted / 574 records**. The concurrent update added four records and refreshed language screenshots. This combines 566 preserved records from the integrated head with eight new captures; it does not claim that all 574 were newly photographed. Original top-level capture metadata remains intact; `revalidation` records the new browser, source hash, exact files, and comparison. Updated records carry `revalidated: true`.

On the initial head, all 562 clean records and their 560 distinct images were verified unchanged. On the integrated head, all 566 clean records and their 564 distinct images are preserved byte-for-byte by this patch (two existing pairs of records share filenames; those were preserved). GIFs are unchanged. Other files changed are `web_ui.py`, the regenerated root `index.html`, the browser test, and this report. No dependency or lockfile changes.

Reproduce the focused after-check:

```sh
WEB_UI_SHOTS=/tmp/cities-recheck python tests/integration/school_browser.py \
  CitiesTests.test_every_width_fits_each_city \
  CitiesTests.test_shimbashi_sheet_keeps_the_player_visible_at_the_map_edge -v
```

Use a separate output directory: a full run against the existing evidence directory would unnecessarily recapture normal records.

After integrating the concurrent changes, Python checks including `test_theme_seed.py`: **172 passed, 10 skipped, 1 subtest passed (4.72s)**.

Final integrated-source browser run: **6 methods passed (129.929s)**: all six widths across all cities, the two Shimbashi approaches, new zoom dial/overlay opacity, all 11 languages, keys/pad/water at normal speed, and reduced motion. Its capture manifest contains no visual warnings. The earlier 15 city / four school results above are the complete pre-integration regression run; the final six checks cover the camera/header integration and newly added controls.
