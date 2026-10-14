# Architecture

```text
Reolink sensor (person/pet/doorbell)
            |
            v
Home Assistant blueprint automation (one per event)
            |
        parallel
         /     \
        /       \
      ntfy     Immich
       |         |
  image: direct  image: HA camera.snapshot -> JPG
  video: RTSP    video: RTSP FFmpeg -> MP4
       |         |
  ntfy.publish  immich.upload_file(existing album UUID)
       |         |
 optional cleanup for that destination's *own* local file
```

## Modules

| Component | File | Responsibility |
| --- | --- | --- |
| Blueprint | `blueprints/automation/kamera_medien/reolink_medien.yaml` | event trigger, parameters, separate destination branches |
| Runtime | `packages/kamera_medien_runtime.yaml` | invokes recorder, handles delivery and optional video cleanup |
| Snapshot package | `packages/kamera_medien_snapshot.yaml` | snapshot preparation, camera.snapshot, Immich and optional JPG cleanup |
| Recorder | `scripts/record_v2.py` | camera JSON → RTSP URL → FFmpeg → ffprobe → atomic `.mp4` |
| Video cleanup | `scripts/cleanup_media.py` | delete **one** completed `.mp4`, with ID, lock and path checks |
| JPG cleanup | `scripts/snapshot_media.py` | prepare and delete an event/run-specific JPG |

## Media layout

```text
/media/kamera_events/
    snapshots/
        garden_pet__20261013T123000_123456_54321.jpg
    garden_pet/
        20261013T123000_123456_54321/
            ntfy.mp4
            immich.mp4
```

Incomplete recordings use temporary `*.mp4.part` files. The recorder verifies duration and the presence of a video stream before atomically publishing the `.mp4`. Files are **not** intentionally reused across different purposes/runs.

## Runtime contract

FFmpeg is invoked through Home Assistant's native `shell_command`; its response supplies `returncode`, `stdout`, `stderr`. On success the recorder prints a single JSON object including `success`, `file`, `media_content_id`, `size_bytes`, `stream`, `has_audio`, `event_id`, `run_id` and `purpose`. Runtime YAML checks this JSON and routes to the native ntfy or Immich action.

There is no custom network server or background queue. This keeps maintenance simple but means HA restarts can interrupt jobs and calls must complete within `shell_command`'s 60-second limit. Duration is capped at 40 seconds.

## Why not `camera.record`?

During development on HA Core 2026.10.1, intermittent `non monotonically increasing dts` failures occurred with Reolink Clear recordings via `camera.record`, and it rejected simultaneous recordings of one entity. Direct FFmpeg via RTSP was successfully tested for Clear/Fluent, with audio and concurrent recording. This is evidence for **this setup**, not a universal claim about all Home Assistant/Reolink versions.

## Design boundaries

The project does not decide when to arm an alarm, switch lights, detect animals using its own AI, create Immich albums, retry failed transfers or manage camera recording limits. Reolink provides detection; Home Assistant provides orchestration and user-facing logging; ntfy and Immich handle destination delivery/storage.
