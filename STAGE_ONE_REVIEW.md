# Stage 1 frontend review

Stage 1 only: ready for visual approval. Stage 2 has not started. Changes remain local;
no commit, push, production deploy, backend restart or paid provider requests were made.

## Implemented

- Reference #5 application geometry: 336px sidebar, 80px top bar, white workspace at
  x336/y80, large rounded corners and 30px internal gutters.
- Sidebar contains only available existing destinations; no account, subscription,
  assistant, model-library, recording or other unsupported controls were added.
- Upload work area uses a 1.59:1 two-column split, a warm dashed drop target,
  the existing original waveform icon, consent, selected-file state and Open recording.
  Open recording is visible but disabled until the same existing file/consent conditions pass.
- Onest Variable and Lato are self-hosted from Google Fonts with OFL notices.
- Functional sidebar collapse/drawer, keyboard Escape, and responsive stacking.
- Existing public-usage information and Tweeq name/tagline retained.

## Visual comparison

Captured and manually compared the actual Playwright render at 1918 x 955 with the
supplied reference #5. The final white panel is x336/y80/w1566/h859; the drop area is
x366/y185/w906.109/h724. Adjusted sidebar icon/text alignment, upload instruction weight,
vertical panel sizing, upload-button placement and disabled-action alignment.

Five sampled stable surface pixels match the reference exactly: #FBFAF9 sidebar,
#FFFFFF panel/card surfaces, #FAF7F7 drop surface and #C4B7B4 disabled action.
This is structural/color comparison, not a claim that different product content is pixel-identical.
Fish voice portraits, logos, team/billing controls and artwork are intentionally absent.

Screenshots and measurements are in test-results/stage-one/artifacts/:
- stage-one-upload-1918x955.png (primary review screenshot)
- stage-one-file-selected-1918x955.png
- stage-one-desktop-1280x800.png
- stage-one-mobile-390x844.png
- stage-one-mobile-details-390x844.png
- initial-geometry.json and palette-comparison.json

## Preservation checks

The complete App state/effect/event-handler body before JSX is unchanged, verified against
its pre-change backup. Backend app sources, api.js, editorState.js, deliveryText.js,
EditorWorkspace.jsx, EditorSurfaces.jsx, DeliveryControls.jsx, WaveformEditor.jsx and
original index.css are byte-identical to their pre-change versions. The editor remains
in its existing appearance inside the new shell pending Stage 2 approval.

No API contracts, generation settings, session state, timestamps, preview validation,
ASR caching, replacement behavior, Undo/Redo, comparison or export logic changed.

## Validation

Frontend tests: 5 node helper tests plus 41 Vitest tests.
Playwright: 5 real Chromium tests, with all API requests fulfilled from local fixtures
and all nonlocal/unexpected network traffic blocked. Includes actual waveform decoding
from generated local PCM WAV, upload/consent validation, upload failure recovery,
file/consent retention through sidebar toggles, mobile navigation/scrolling and no
horizontal overflow. No live backend or Fish Audio endpoints were used.
Production Vite build checked. Playwright is a development-only dependency.

## Modified/new frontend files

App.jsx (JSX wiring only), AppHeader.jsx, Icon.jsx, main.jsx, App.ui.test.jsx,
index.html (theme color), package.json and pnpm-lock.yaml; new AppShell.jsx,
UploadScreen.jsx, stage-one.css, playwright.config.js, e2e/stage-one.spec.js and
public/fonts/ with license/source notices. No production runtime dependency added.

Backup: see test-results/stage-one/latest.txt for the source archive and protected hashes.
The unrelated untracked migrations/ folder was not changed.

STOP: obtain user approval of this screenshot before any Stage 2 editor redesign.
