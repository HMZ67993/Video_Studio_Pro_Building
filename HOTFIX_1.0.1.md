# HMZ Video Studio Pro v1.0.1 — Hotfix

## Fixed
- Fixed a Windows crash (`PermissionError: [WinError 32]`) during timeline/audio-preview updates.
- The editor no longer deletes a rendered WAV synchronously while `QMediaPlayer` may still have it open.
- Retired preview WAV files are now detached, queued for cleanup, and retried with backoff if Windows temporarily locks them.
- Shutdown now stops the media player and clears its source before best-effort temporary-file cleanup.

## Validation
- Added a regression test that simulates a locked WAV file.
- 111 tests passed in the main suite (excluding the sticker test module); 5 sticker tests passed separately.
- The GUI/audio backend could not be exercised on a real Windows device in this environment. Please test playback, pause, timeline edits, and repeated preview regeneration on Windows.
