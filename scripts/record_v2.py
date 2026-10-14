#!/usr/bin/env python3
"""Reolink-RTSP-Aufnahme für Home Assistant (Modul 1).

Vertrag:
- Argumente: --camera, --stream, --duration, --event, --purpose, [--run-id]
- Exit 0: genau eine JSON-Zeile auf stdout, danach ist die MP4 fertig.
- Exit != 0: lesbare Meldung auf stderr, niemals Kamerapasswörter.
- Keine Konvertierung: Video/Audio werden unverändert kopiert.
- Keine Dateibereinigung: eigener Verarbeitungsschritt nach ntfy/Immich.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

CAMERA_CONFIG = Path('/config/camera_media/cameras.json')
OUTPUT_ROOT = Path('/media/kamera_events')
MEDIA_PREFIX = 'media-source://media_source/local/kamera_events'
MAX_DURATION = 40  # Home Assistant shell_command wird nach 60 s beendet.
SAFE_ID = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$')


class RecordingError(Exception):
    """Erwartbarer Aufnahme-/Konfigurationsfehler."""


def safe_id(value: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise argparse.ArgumentTypeError(
            'Nur Buchstaben, Ziffern, _ und - erlaubt (max. 80 Zeichen).'
        )
    return value


def read_camera(camera_id: str) -> dict:
    try:
        cameras = json.loads(CAMERA_CONFIG.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RecordingError(f'Kamerakonfiguration nicht lesbar: {type(exc).__name__}') from None

    if camera_id not in cameras:
        raise RecordingError(f'Unbekannte Kamera-ID: {camera_id}')
    camera = cameras[camera_id]
    required = ('host', 'username', 'password')
    if not isinstance(camera, dict) or not all(
        isinstance(camera.get(k), str) and camera[k] for k in required
    ):
        raise RecordingError(f'Unvollständige Konfiguration für Kamera: {camera_id}')
    host = camera['host']
    if any(c in host for c in ' /@?#\n\r\t'):
        raise RecordingError(f'Ungültiger Host bei Kamera: {camera_id}')
    try:
        channel = int(camera.get('channel', 1))
        port = int(camera.get('port', 554))
    except (ValueError, TypeError):
        raise RecordingError(f'Ungültiger Kanal/Port bei Kamera: {camera_id}') from None
    if not 1 <= channel <= 99 or not 1 <= port <= 65535:
        raise RecordingError(f'Kanal/Port außerhalb des gültigen Bereichs: {camera_id}')
    return {**camera, 'channel': channel, 'port': port}


def build_url(camera: dict, stream: str) -> str:
    suffix = 'main' if stream == 'clear' else 'sub'
    user = quote(camera['username'], safe='')
    password = quote(camera['password'], safe='')
    host = camera['host']
    if ':' in host and not host.startswith('['):  # IPv6
        host = f'[{host}]'
    return (
        f"rtsp://{user}:{password}@{host}:{camera['port']}"
        f"/Preview_{camera['channel']:02d}_{suffix}"
    )


def probe_video(path: Path, expected_duration: int) -> dict:
    try:
        probe = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries',
             'stream=codec_type,codec_name:format=duration',
             '-of', 'json', str(path)],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except subprocess.TimeoutExpired:
        raise RecordingError('ffprobe-Timeout') from None
    if probe.returncode != 0:
        raise RecordingError('ffprobe konnte die Ausgabedatei nicht lesen')
    try:
        details = json.loads(probe.stdout)
        streams = details.get('streams', [])
        duration = float(details.get('format', {}).get('duration', 0))
    except (ValueError, TypeError, KeyError):
        raise RecordingError('Ungültige ffprobe-Metadaten') from None
    if not any(s.get('codec_type') == 'video' for s in streams):
        raise RecordingError('MP4 enthält keine Videospur')
    if duration < expected_duration * 0.70:
        raise RecordingError(
            f'Video unvollständig: {duration:.1f} s statt ca. {expected_duration} s'
        )
    return {
        'duration_seconds': round(duration, 2),
        'has_audio': any(s.get('codec_type') == 'audio' for s in streams),
        'video_codec': next(
            (s.get('codec_name', 'unknown') for s in streams
             if s.get('codec_type') == 'video'), 'unknown'
        ),
    }


def record(args: argparse.Namespace) -> dict:
    camera = read_camera(args.camera)
    url = build_url(camera, args.stream)
    run_id = args.run_id or (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        + '_' + uuid.uuid4().hex[:8]
    )

    # Sowohl ntfy- als auch Immich-Zweig können unter derselben Run-ID arbeiten.
    directory = OUTPUT_ROOT / args.event / run_id
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / f'{args.purpose}.mp4'
    lock = directory / f'{args.purpose}.lock'
    partial = directory / f'{args.purpose}.{uuid.uuid4().hex[:8]}.mp4.part'

    # Exklusives Lock verhindert versehentliche Doppelaufträge mit gleicher Run-ID.
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError:
        raise RecordingError('Aufnahme für diese Ereignis-/Run-/Ziel-Kombination läuft bereits') from None

    try:
        if final.exists():
            raise RecordingError(f'Zieldatei bereits vorhanden: {final}')
        command = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-rtsp_transport', 'tcp', '-i', url,
            '-map', '0:v:0', '-map', '0:a:0?',
            '-c:v', 'copy', '-c:a', 'copy',
            '-t', str(args.duration), '-movflags', '+faststart',
            '-f', 'mp4', str(partial),
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True,
                timeout=min(args.duration + 12, 52), check=False,
            )
        except subprocess.TimeoutExpired:
            raise RecordingError('FFmpeg-Timeout (Kamera nicht erreichbar oder Stream hängt)') from None
        if result.returncode:
            # Zugangsdaten in Logs und HA-Traces unter keinen Umständen ausgeben.
            error = result.stderr.replace(url, '[RTSP_URL]')
            for secret in (camera['password'], quote(camera['password'], safe='')):
                if secret:
                    error = error.replace(secret, '[GEHEIM]')
            raise RecordingError(
                f'FFmpeg Exit-Code {result.returncode}: {error.strip()[-1500:]}'
            )
        if not partial.exists() or partial.stat().st_size < 1024:
            raise RecordingError('Keine brauchbare MP4-Datei erstellt')
        metadata = probe_video(partial, args.duration)

        # Atomare Freigabe erst NACH FFmpeg, Größen- und Video-Prüfung.
        partial.rename(final)
        relative = f'{args.event}/{run_id}/{args.purpose}.mp4'
        return {
            'success': True,
            'event_id': args.event,
            'run_id': run_id,
            'camera_id': args.camera,
            'stream': args.stream,
            'purpose': args.purpose,
            'file': str(final),
            'filename': final.name,
            'media_content_id': f'{MEDIA_PREFIX}/{relative}',
            'media_content_type': 'video/mp4',
            'size_bytes': final.stat().st_size,
            **metadata,
        }
    finally:
        lock.unlink(missing_ok=True)
        # Fehlerhafte .part-Dateien werden bewusst nicht gelöscht.


def main() -> int:
    parser = argparse.ArgumentParser(description='Reolink RTSP nach MP4 aufnehmen')
    parser.add_argument('--camera', required=True, type=safe_id)
    parser.add_argument('--stream', required=True, choices=('clear', 'fluent'))
    parser.add_argument('--duration', required=True, type=int)
    parser.add_argument('--event', required=True, type=safe_id)
    parser.add_argument('--purpose', required=True, choices=('ntfy', 'immich'))
    parser.add_argument('--run-id', type=safe_id)
    args = parser.parse_args()
    if not 1 <= args.duration <= MAX_DURATION:
        parser.error(f'--duration muss zwischen 1 und {MAX_DURATION} Sekunden liegen')
    try:
        data = record(args)
        print(json.dumps(data, ensure_ascii=False))
        return 0
    except (RecordingError, OSError, ValueError) as exc:
        print(f'AUFNAHMEFEHLER: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
