# Troubleshooting

**First step:** Open the automation's **Trace** and identify the exact failing action. Video processing also has a script trace for `script.kamera_medien_video`; snapshots have `script.kamera_medien_immich_bild`.

| Symptom | What to check |
| --- | --- |
| Blueprint says configuration invalid | For **any image mode**, set `snapshot_camera` to a valid `camera.*` entity; also check output target, video camera key and Immich UUID/instance when relevant. Both outputs cannot be `none`. |
| Unknown video camera ID | `video_camera_id`/`ntfy_video_camera_id` must match a key in `/config/camera_media/cameras.json`, **not** a `camera.*` entity. |
| No RTSP output | Enable RTSP in the camera, check routing/firewall/TCP 554, credentials and channel mapping **from inside the container**. |
| Wrong wide/tele lens | Verify `Preview_01_sub`, `Preview_02_sub`, etc. on the actual device. Channel mapping is model-specific. |
| Immich says invalid UUID | Use the **album UUID** copied from the end of the album web URL, not its human-friendly album name. |
| Missing ntfy video | Verify FFmpeg recording succeeded, file size, topic entity, ntfy attachment limits and codec compatibility on the receiver. |
| Snapshot succeeds but no file retained | With `cleanup_files: true`, the JPG is intentionally deleted after successful Immich action. Set `false` while testing. |
| `.part` file remains | Recording or Home Assistant process was interrupted or FFmpeg failed. The project does not auto-retry; inspect traces and disk before removing test debris. |
| Recording timeout | Camera connection may hang, or duration+processing exceeded timeout margins. `shell_command` itself has a 60-second hard limit. |
| Native ntfy/Immich action fails without persistent notification | Inspect the native action in **Trace / Home Assistant Logs**. Persistently notifying on arbitrary native action exceptions is not guaranteed by the current YAML design. |
| Too many concurrent recordings | Lower simultaneous event load; HA script and automation have max-concurrency ceilings. Camera/network/server capacity can also be lower. |
| `media-source://` not accessible | Check container's persistent `/media` mount and that local `media_source` is enabled; do not substitute public `/config/www`. |

## Useful commands (Docker host)

```bash
cd /root/homeassistant

# File presence and access inside the container
docker compose exec -T homeassistant sh -c \
  'ls -ld /config/camera_media /media/kamera_events; command -v ffmpeg; command -v ffprobe'

# Validate camera aliases without leaking secrets
docker compose exec -T homeassistant python3 -c \
  'import json; print(sorted(json.load(open("/config/camera_media/cameras.json"))))'

# Check HA configuration
docker exec homeassistant \
  python -m homeassistant --script check_config --config /config

# Recent HA logs (sanitize before sharing)
docker compose logs --tail=150 homeassistant
```

A successful Home Assistant configuration check confirms only configuration validity, **not** that Reolink, ntfy or Immich is reachable. For end-to-end testing, see [Testing](TESTING.md).

## Privacy reminder

Do not paste RTSP URLs, `cameras.json`, media files, API keys or unredacted traceback paths into public issues. Event names, camera locations and timestamps can be sensitive too.
