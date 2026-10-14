# Installation — Home Assistant Container

This guide installs the **complete** Reolink Media Events system. It does **not** require SSH into a camera, a systemd watcher, Home Assistant helpers, a separate Python service or HACS.

**Tested:** Home Assistant Container/Core 2026.10.1. The example host uses `/root/homeassistant` and Docker Compose service `homeassistant`. Replace those values for your system. Commands run on your Docker **host**, not inside a shell in the Home Assistant UI.

## 0. Prerequisites

- A working Home Assistant Container with `/config` persisted and `/media` mounted to persistent host storage.
- The Reolink integration configured in Home Assistant for the **event binary sensors** and camera snapshot entities.
- The native [ntfy integration](https://www.home-assistant.io/integrations/ntfy/) configured, with at least one `notify.*` topic entity (if sending notifications).
- The native [Immich integration](https://www.home-assistant.io/integrations/immich/) configured (if uploading to Immich), and an **existing album**.
- Camera RTSP enabled in Reolink, reachable **from inside the container** on port 554; valid camera credentials.
- `python3`, `ffmpeg`, `ffprobe` available **inside the container**.

Check the container and binaries (example):

```bash
cd /root/homeassistant
docker compose ps
docker compose exec -T homeassistant sh -c '
  command -v python3 && command -v ffmpeg && command -v ffprobe
  test -d /config && test -d /media && test -w /media
'
```

If `/media` is missing, use `vi /root/homeassistant/compose.yml` and ensure the Home Assistant service has a bind mount such as:

```yaml
services:
  homeassistant:
    volumes:
      - /root/homeassistant/config:/config
      - /root/homeassistant/media:/media
```

**Do not replace an existing `compose.yml` with this fragment.** Add the missing `/media` volume alongside your existing volumes and recreate the container during a maintenance window. See [Home Assistant's local media documentation](https://www.home-assistant.io/more-info/local-media/setup-media).

## 1. Obtain the repository

After the maintainer publishes it to GitHub:

```bash
cd /root
git clone https://github.com/REPLACE_WITH_GITHUB_USERNAME/ha-reolink-media-events.git
cd /root/ha-reolink-media-events
```

**Before the first GitHub publication:** alternatively transfer and extract the ZIP package onto the Docker host, then `cd` into the extracted `ha-reolink-media-events` directory. No real GitHub URL exists until you publish the repo.

## 2. Back up any existing installation

If you have already used this project, first save the two package files and the blueprint outside `/config/packages`:

```bash
HA_DIR=/root/homeassistant
BACKUP="/root/ha-reolink-media-events-backup-$(date +%Y%m%d_%H%M%S)"
mkdir -m 700 -p "$BACKUP"

for file in \
  "$HA_DIR/config/packages/kamera_medien_runtime.yaml" \
  "$HA_DIR/config/packages/kamera_medien_snapshot.yaml" \
  "$HA_DIR/config/blueprints/automation/kamera_medien/reolink_medien.yaml"; do
  if [ -f "$file" ]; then cp -a "$file" "$BACKUP/"; fi
done
printf 'Backup directory: %s\n' "$BACKUP"
```

Your existing `cameras.json` is **not** overwritten by the instructions below. Keep a private backup of it too.

## 3. Install files

Run from the repository root on the Docker host:

```bash
HA_DIR=/root/homeassistant
mkdir -p \
  "$HA_DIR/config/camera_media" \
  "$HA_DIR/config/packages" \
  "$HA_DIR/config/blueprints/automation/kamera_medien" \
  "$HA_DIR/media/kamera_events"

cp blueprints/automation/kamera_medien/reolink_medien.yaml \
  "$HA_DIR/config/blueprints/automation/kamera_medien/"

cp packages/kamera_medien_runtime.yaml \
   packages/kamera_medien_snapshot.yaml \
  "$HA_DIR/config/packages/"

cp scripts/record_v2.py scripts/cleanup_media.py scripts/snapshot_media.py \
  "$HA_DIR/config/camera_media/"

chmod 700 "$HA_DIR/config/camera_media/"*.py

# Copy the example ONLY if the real camera file does not exist yet.
if [ ! -e "$HA_DIR/config/camera_media/cameras.json" ]; then
  install -m 600 examples/cameras.example.json \
    "$HA_DIR/config/camera_media/cameras.json"
fi
chmod 600 "$HA_DIR/config/camera_media/cameras.json"
```

**Do not copy test files or `examples/*.yaml` into `/config/packages/`**. They are examples, not packages to be loaded.

## 4. Configure cameras

Edit the local, untracked credential file using `vi`:

```bash
vi /root/homeassistant/config/camera_media/cameras.json
```

Give each desired physical camera or lens a logical key, such as `front_door`, `garden_wide`, or `garden_tele`. Each entry must contain `host`, `username`, `password`, and optionally `channel` (default 1) and `port` (default 554).

For dual-lens devices, two keys may use the **same IP** and different verified RTSP channels. **Do not assume channel 2 is the tele lens** on every model; test the stream shown. `clear` selects `Preview_NN_main`, `fluent` selects `Preview_NN_sub`.

The keys are used in the blueprint's **Video camera ID** fields. Snapshot camera selection is a **separate Home Assistant `camera.*` entity**.

Check JSON syntax without printing secrets:

```bash
cd /root/homeassistant
docker compose exec -T homeassistant python3 -c '
import json
from pathlib import Path
p = Path("/config/camera_media/cameras.json")
cameras = json.loads(p.read_text())
print("Camera aliases:", ", ".join(sorted(cameras)))
'
```

For troubleshooting camera connectivity, see [Troubleshooting](TROUBLESHOOTING.md).

## 5. Enable Home Assistant packages and local media

Edit:

```bash
vi /root/homeassistant/config/configuration.yaml
```

If a `homeassistant:` block **already exists**, add **only** its missing `packages:` entry. Never create a second `homeassistant:` key:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

If you already have packages configured with the same directive, do nothing.

Home Assistant commonly enables `media_source` through `default_config:`. If your installation has neither `default_config:` nor `media_source:`, add `media_source:` at the **top level** of `configuration.yaml`.

The default `/media` folder is a valid camera.snapshot output location and is normally available as local media. Do not publish sensitive footage by moving it into `/config/www`.

## 6. Validate and restart

Run on the Docker host:

```bash
cd /root/homeassistant

docker exec homeassistant \
  python -m homeassistant --script check_config --config /config \
  && echo "Configuration OK"
```

If validation fails, correct the reported error first; do not restart with an invalid configuration.

On a **first installation**, a Home Assistant restart is recommended so the new packages are loaded:

```bash
docker compose restart homeassistant
```

This interrupts ongoing automations, so choose an appropriate time. If simply upgrading files in an existing installation, Home Assistant's **Developer Tools → YAML** can reload Shell Commands, Scripts and Automations after a successful config check.

## 7. Confirm runtime services and record a short test

From **Home Assistant → Developer Tools → Actions**, use YAML mode (replace `front_door` with a real key from your camera JSON):

```yaml
action: shell_command.kamera_medien_record_v2
data:
  camera_id: front_door
  stream: fluent
  duration: 10
  event_id: installation_test
  purpose: ntfy
  run_id: install_check_001
```

A successful result includes `returncode: 0` and JSON `stdout` with `success: true`, `file` and `media_content_id`. It saves a local MP4 but **does not send a notification** or upload to Immich. If run ID `install_check_001` is reused, change it to another identifier; this module intentionally prevents overwriting files.

Alternatively run the optional [automated recording integration test](TESTING.md). The test files can be removed after review.

## 8. Create the first blueprint automation

In Home Assistant, go to **Settings → Automations & scenes → Blueprints**, locate **Reolink | Kameraereignis → ntfy / Immich** and select **Create automation**. (If the UI lists it under another language, search for **Reolink**.)

For a first smoke test, use an event sensor that you can trigger safely, select the matching source entities and choose **ntfy image** with a configured notify topic. Set **Immich output** to **None** to isolate the first test. The `snapshot_camera` input is **required for image modes**, even though the video camera ID is optional for image-only events.

Save, trigger the event and review the automation trace and ntfy message. For subsequent tests, enable Immich with a valid **album UUID** from the last part of the album's Immich web URL and select the integration from the config-entry selector.

Finally test one Fluent video to ntfy, one Clear video to Immich and, if applicable, parallel events on your camera model. Enable `debug` when troubleshooting and select `cleanup_files: false` while inspecting files.

See [Configuration](CONFIGURATION.md) for every blueprint input and more examples.

## 9. Updates / rollback

Back up the two packages and blueprint, then overwrite them and the scripts with updated repo files. **Do not overwrite the real `cameras.json`.** Run the config check again. For the stream-selector update, older automations keep ntfy=Fluent and Immich=Clear by default.

To roll back, restore the saved files to their original locations, run the config check and reload/restart. Retained media files do not need to be deleted as part of rollback.

## Official references

- [HA packages](https://www.home-assistant.io/docs/configuration/packages/)
- [HA Shell Command](https://www.home-assistant.io/integrations/shell_command/)
- [HA local media](https://www.home-assistant.io/more-info/local-media/setup-media)
- [HA blueprints](https://www.home-assistant.io/docs/automation/using_blueprints/)
- [Immich upload](https://www.home-assistant.io/actions/immich.upload_file/)
- [ntfy notification](https://www.home-assistant.io/actions/ntfy.publish/)
