# GUI Compact Update — v1.0.2

## Changes

- Tightened spacing and margins in the right-side Inspector tabs (Video, Color, Speed, Audio, Keyframes, Motion).
- Reduced the height and padding of numeric fields, combo boxes, buttons, and checkboxes only inside the Inspector.
- Made the Text Inspector denser: smaller group-box padding, more compact rows, smaller color swatches and formatting buttons, and a shorter text input area.
- Kept global dialogs and unrelated application controls at their existing sizes.
- No project schema or media-rendering behavior was changed in this GUI update.

## Verification

- Python compile check passed.
- Automated test suite: 116 passed.
- PyQt6 is not available in the build environment, so the visual result still needs confirmation on Windows at the actual panel width and display scaling.
