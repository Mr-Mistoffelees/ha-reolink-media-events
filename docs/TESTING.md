# Testing and release verification

## What has been tested end-to-end

On Home Assistant Container/Core 2026.10.1, the original setup verified:

- Direct snapshot to ntfy, including when video recordings were running.
- Home Assistant snapshot uploaded to an existing Immich album.
- Clear and Fluent RTSP recording via FFmpeg with audio; two Clear recordings and Clear+Fluent in parallel.
- FFmpeg Fluent MP4 delivered and played (with audio) on iPhone via ntfy.
- FFmpeg Clear MP4 uploaded to Immich and played successfully.
- Two branches (Fluent to ntfy, Clear to Immich) started from the same automation.
- Cleanup enabled/disabled, including file retention on incomplete work.
- The final blueprint image/image and video/video modes, parallel branches and independent Clear/Fluent selection.

These tests do not guarantee behavior on every Home Assistant/FFmpeg/Reolink release. The GitHub workflow runs **only offline tests**.

## Offline tests on a checkout

Requirements: Python 3.13 or later, PyYAML and Jinja2 for the tests (the runtime recorder itself needs no third-party Python modules). From the repository root:

```bash
python3 -m pip install -r tests/requirements.txt
python3 -m py_compile scripts/*.py
python3 -m unittest discover -s tests -p 'test_offline.py' -v
```

These tests use temporary paths and no camera/ntfy/Immich credentials. They validate YAML shape, independent stream selection, safe cleanup and RTSP URL construction, but **not** a running Home Assistant instance.

## Optional camera integration test

The test driver `tests/test_record_integration.py` records real RTSP video. It must run **inside** the Home Assistant container and expects the recorder at `/config/camera_media/record_v2.py`. From the **Docker host**, in a directory containing the checkout:

```bash
cd /root/homeassistant
# Change the path on the left to the location of the checkout.
docker compose cp /root/ha-reolink-media-events/tests/test_record_integration.py \
  homeassistant:/tmp/test_record_integration.py

docker compose exec -T homeassistant \
  python3 /tmp/test_record_integration.py \
  --camera REPLACE_WITH_EXISTING_CAMERA_KEY --duration 10
```

Expected ending: `GESAMTERGEBNIS: 3/3 Testblöcke erfolgreich`. The camera must provide audio for this particular test. The driver **keeps** its videos at `/media/kamera_events/modultest/` for inspection. Delete only those specific, reviewed test files when done. If `docker compose cp` is unavailable, place the test script temporarily in `/config/camera_media` instead, and remove it afterward.

## Manual smoke test after installation

1. Create one blueprint event with `ntfy_mode=image`, `immich_mode=none`. Trigger a real `off → on` sensor transition; verify prompt ntfy delivery and a clean trace.
2. Choose `immich_mode=image` and a valid existing album UUID; verify the JPG in that album.
3. Choose `ntfy_mode=video`, `ntfy_video_stream=fluent` and verify the MP4 with audio on the intended device.
4. Choose `immich_mode=video`, `immich_video_stream=clear` and verify the clip in the existing album.
5. On a dual-lens camera, test the alternate camera key and ensure the picture actually shows the desired lens. Verify Fluent/Clear settings independently.
6. With `cleanup_files=false`, verify `/media/kamera_events/<event>/<run_id>/ntfy.mp4` and/or `immich.mp4` are present as applicable. With `true`, verify successful transfers remove only their own local files.
7. Trigger another event while the first is recording; confirm the immediate ntfy snapshot has no artificial wait.

**Note:** Manually clicking “Run actions” skips the original sensor trigger condition and is not a complete test of event detection. Trigger the sensor normally once before calling a configuration production-ready.

## Interpretation of results

A successful upload/service return is not the same as full end-to-end confirmation. Always validate the actual ntfy destination and the specific Immich album. Inspect the media on the intended playback device.
