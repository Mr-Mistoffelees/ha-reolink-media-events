# Reolink Media Events for Home Assistant

**Home Assistant Blueprint for Reolink Cameras. Delivers event-based snapshots and RTSP videos to ntfy and Immich.**

**Warning:** I’m more of a casual pedestrian than a seasoned software engineer. This project was largely vibe-coded over many evenings with the help of ChatGPT (GPT-6), with me providing the ideas, requirements, and occasional reality checks. It’s running happily in my own Home Assistant setup and has been working great so far—so I figured I’d share it with the community. 

**Background:** Home Assistant is great! But sometimes its native camera recording occasionally struggles with Reolink cameras, leading to a few frustrating issues:

- **Clear stream recording failures**, including FFmpeg timestamp (DTS) errors.
- **Simultaneous recordings from the same camera** being rejected or causing unexpected failures.
- **Unreliable parallel Clear and Fluent recordings**, making independent camera events difficult to handle.

Rather than waiting for everything to magically fix itself, I decided to take matters into my own hands and build a flexible, event-driven solution using FFmpeg.

> **Important:** This is a **blueprint plus runtime scripts**, not a standalone importable blueprint. Installing the blueprint file alone will **not** work. Follow the [complete installation guide](docs/INSTALLATION.md).

## Features

- **Independent events:** create separate blueprint automations for doorbell, people, pets or other Reolink binary sensors.
- **ntfy:** no notification, immediate camera snapshot, or MP4 video with audio; select topic, title, message and priority.
- **Immich:** nothing, JPG snapshot or MP4 video uploaded to an **existing album UUID**. Missing albums are not created.
- **Independent streams:** for each video destination, choose **Clear** or **Fluent**. Defaults are **ntfy = Fluent**, **Immich = Clear**. No transcoding by default.
- **Multiple lenses:** define separate logical camera IDs in `cameras.json` for different tested RTSP channels, even if they share a physical IP address.
- **Parallel processing:** ntfy and Immich branches can run concurrently. Each event execution has a distinct run ID and separate media files.
- **Optional cleanup:** delete an individual local file only after the corresponding delivery action returns successfully; otherwise keep it for diagnostics.
- **Diagnostics:** Home Assistant traces, persistent notifications for validation/recording/cleanup errors and optional logbook debug entries.
- **No extra helpers or database** required; no automatic retries.

## Tested environment

This release has been tested on **Home Assistant Container, Core 2026.10.1**, using Reolink RTSP cameras, the official Home Assistant **ntfy** and **Immich** integrations, and `ffmpeg`/`ffprobe` available **inside** the Home Assistant container. The documented setup assumes the container has a persistent `/config` and `/media` mount.

Other Home Assistant installations and Reolink models may work, but have not been verified as a general compatibility guarantee. The blueprint declares a lower minimum version for its schema features; that is **not** a promise of full integration compatibility on older Core releases.

## Quick start

1. Read the [installation guide](docs/INSTALLATION.md) **before** importing the blueprint.
2. Configure `cameras.json` from [the safe example](examples/cameras.example.json).
3. Install the **two** Home Assistant package files and the **three** Python scripts.
4. Check Home Assistant configuration, restart/reload, then import or create an automation from the blueprint.
5. Start with one event and review its trace, ntfy message and Immich album before adding more.

> **Language note:** Documentation is in English; some blueprint UI labels and runtime diagnostics retain their original German wording from the tested implementation. The technical input keys remain stable.

**Additional docs:** [Configuration](docs/CONFIGURATION.md) · [Architecture](docs/ARCHITECTURE.md) · [Troubleshooting](docs/TROUBLESHOOTING.md) · [Verification/tests](docs/TESTING.md) · [Publishing](docs/PUBLISHING.md) · [Security](SECURITY.md)

## Example event

An event can watch a pet detector, send a Fluent video to one ntfy topic and send a Clear original to an Immich album:

```yaml
alias: Garden – Pet detected
use_blueprint:
  path: kamera_medien/reolink_medien.yaml
  input:
    event_id: garden_pet
    detection_sensor: binary_sensor.REPLACE_WITH_YOUR_PET_SENSOR
    video_camera_id: garden_wide
    snapshot_camera: camera.REPLACE_WITH_YOUR_SNAPSHOT_CAMERA
    video_duration: 20
    ntfy_video_duration: 10
    ntfy_mode: video
    ntfy_video_stream: fluent
    ntfy_target: notify.REPLACE_WITH_YOUR_TOPIC
    ntfy_title: Pet in the garden
    ntfy_message: An animal has been detected.
    ntfy_priority: 3
    immich_mode: video
    immich_video_stream: clear
    immich_config_entry_id: REPLACE_WITH_IMMICH_CONFIG_ENTRY_ID
    immich_album_id: REPLACE_WITH_EXISTING_ALBUM_UUID
    cleanup_files: true
    debug: false
```

The IDs and entities above are placeholders. The `video_camera_id` is a **key in `cameras.json`**, not a Home Assistant camera entity; `snapshot_camera` **is** a Home Assistant camera entity. [More examples and explanations](docs/CONFIGURATION.md).

## Important limitations

- **Video is not instant.** The MP4 must be recorded before ntfy can attach it. The **ntfy snapshot** path does not wait for the video path.
- Home Assistant's `shell_command` has a **fixed 60-second runtime limit**; recording durations are limited to **1–40 seconds** with additional timeout margins.
- Concurrent RTSP requests need camera/network capacity; performance on one camera does not guarantee it on every model.
- There is **no recording before the trigger**, cooldown, per-event quota, retry queue or automatic repair of partial recordings.
- A completed ntfy action confirms handoff, **not delivery to every phone**. An Immich action error can leave a file uploaded but not assigned to the album.
- If a native `ntfy.publish`, `camera.snapshot`, or `immich.upload_file` action fails, the failing branch is visible in HA traces/logs, but a separate persistent error notification is **not guaranteed**.
- Abrupt Home Assistant/container restarts interrupt running jobs; `.part` files can remain and are not automatically retried.
- Passwords are stored locally in `cameras.json` and may be observable to privileged local processes while FFmpeg is running. Follow [Security](SECURITY.md).

## Maintenance and community

This is a personal project released in the hope that others will find it useful. **My free time is limited**, so although bug reports, feedback and feature ideas are welcome, I may not be able to investigate issues, answer questions or implement requests. Please do not interpret a slow or missing response as a lack of appreciation. Thank you for understanding and for sharing improvements respectfully.

Issues and pull requests may be reviewed when time permits; there is no guaranteed support schedule. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT © 2026 **Mr-Mistoffelees**. See [LICENSE](LICENSE). Not affiliated with or endorsed by Home Assistant, Reolink, Immich or ntfy.
