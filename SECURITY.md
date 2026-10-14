# Security and privacy

This project records private camera footage and accesses local cameras. Treat its configuration, media and diagnostic logs as sensitive.

- **Never commit** `/config/camera_media/cameras.json`: it contains camera passwords. Only commit `examples/cameras.example.json`. `.gitignore` excludes the real file, but check `git status` and `git diff --cached` before pushing.
- Use a dedicated Reolink account with minimal needed permissions if supported. Do not expose RTSP (typically port 554) to the public internet.
- A local user/process with sufficient OS privileges may inspect FFmpeg process arguments, including RTSP credentials, during recording. Protect the container host and avoid untrusted co-tenants.
- Store the camera configuration at `/config/camera_media/cameras.json` with restricted permissions (e.g. `chmod 600`). Backups must be protected as well.
- Protect Home Assistant, ntfy and Immich credentials through their native security mechanisms. Do not paste tokens, alarm locations or camera URLs into public GitHub issues.
- `/media/kamera_events/` contains footage when cleanup is disabled, a delivery fails or a run is interrupted. Plan appropriate filesystem permissions and disk space monitoring.
- Error messages and HA traces may reveal filenames, camera aliases, event IDs and event timing. Sanitize before sharing.
- The project uses local `media-source://` references instead of public `/local/` media URLs for uploads. Do not move files into a publicly accessible `www` directory to work around permission issues.

**Private vulnerability reports:** If you discover a security issue, avoid publishing exploit details or private data in a public issue. Use GitHub's private vulnerability reporting feature if enabled, or contact the maintainer through a private method they explicitly publish. Private support is not guaranteed.
