# Export Performance Diagnosis

The current export path is a CPU-side frame compositor followed by FFmpeg encoding. For every output frame, `VideoStudioProject._frame_for_export()` calls `render_composite_frame()` at the target resolution. That method iterates active clips, decodes or seeks source frames, applies color/effects/masks/chroma, renders text/stickers, performs transforms, and composites layers. The resulting full-resolution BGR24 frame is copied to bytes and written to FFmpeg stdin.

## Main cost centers

1. **Frame composition in Python/OpenCV** occurs for every frame. The NVENC option only accelerates final H.264 encoding; it does not move the compositor to the GPU.
2. **Resolution and FPS multiply work.** 4K has four times the pixels of 1080p; 60 FPS doubles the frame count compared with 30 FPS. 4K60 therefore processes about eight times as many pixels per second as 1080p30.
3. **CPU encoding preset:** the normal x264 path uses `medium` for high/balanced and `faster` for compact. `medium` favors compression efficiency over speed.
4. **Reverse and non-linear speed playback:** the video reader pool optimizes forward sequential reads, but reverse/non-sequential frame indices trigger seeks.
5. **Full-frame effects/transforms and multiple overlays:** color operations, chroma key, LUTs, blur, alpha composition, and affine transforms operate on large arrays.
6. **Raw frame transport:** 4K BGR24 is about 24.9 MB per frame (about 746 MB/s at 30 FPS) before compression.

## Safe user-side speed settings

- Use 1080p / 30 FPS for ordinary delivery; reserve 4K / 60 FPS for projects that truly need it.
- Select the existing Compact preset for faster exports when reduced compression efficiency / larger or lower-quality output is acceptable.
- Enable NVIDIA encoding if the option is visible and the machine has a supported NVIDIA GPU. This can reduce encoder time, but not Python composition time.
- Temporarily disable heavy effects (chroma, LUT, motion blur, sharpness, multiple overlays) to identify which effects dominate.

## Recommended engineering work

- Add separate export timing for frame rendering versus FFmpeg back-pressure/encoding.
- Introduce an explicit Fast x264 preset (e.g. `veryfast`) without silently changing the quality default.
- Improve reverse/non-linear reads, preferably by decoding a clip once into a sequential/reverse frame iterator or using FFmpeg/PyAV decoding.
- Cache invariant masks/LUTs and avoid repeated full-frame allocations where safe.
- Separate preview proxies from final export sources; proxy frames should never silently reduce final export quality.
- Consider a GPU compositor only as a later architectural project, with CPU fallback and output-equivalence tests.

No export-rendering code was changed in v1.0.2. This report records the concrete bottlenecks found in the current implementation and the safest optimization order.
