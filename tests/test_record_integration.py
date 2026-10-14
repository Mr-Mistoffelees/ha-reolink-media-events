#!/usr/bin/env python3
"""Integrationstest für record_v2.py – aus dem HA-Container aufrufen.

Testet Eingabevalidierung, Clear, Fluent mit Audio und parallele Aufnahmen.
Benötigt eine existierende Kamerakennung in cameras.json.
Löscht keine Dateien und verändert keine HA-Konfiguration.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPT = Path('/config/camera_media/record_v2.py')


def invoke(camera: str, stream: str, purpose: str, run_id: str, duration: int) -> dict:
    cmd = [sys.executable, str(SCRIPT), '--camera', camera,
           '--stream', stream, '--purpose', purpose,
           '--event', 'modultest', '--run-id', run_id,
           '--duration', str(duration)]
    process = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=duration + 22)
    if process.returncode:
        raise AssertionError(
            f'{stream}/{purpose}: Exit {process.returncode}: {process.stderr.strip()}'
        )
    try:
        data = json.loads(process.stdout)
    except ValueError as exc:
        raise AssertionError(f'Keine gültige JSON-Antwort: {process.stdout}') from exc
    path = Path(data['file'])
    assert data['success'] and path.is_file(), 'Fertige MP4 fehlt'
    assert path.stat().st_size > 1024, 'Fertige MP4 ist zu klein'
    assert data['media_content_id'].startswith(
        'media-source://media_source/local/kamera_events/'
    ), 'Ungültige Media-Source-ID'
    assert data['purpose'] == purpose and data['stream'] == stream
    assert data['run_id'] == run_id
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--camera', default='testkamera')
    parser.add_argument('--duration', type=int, default=10)
    args = parser.parse_args()
    if not 5 <= args.duration <= 30:
        parser.error('Testdauer muss zwischen 5 und 30 Sekunden liegen')

    print('01/03: Ungültige Ereignis-ID wird zurückgewiesen', flush=True)
    invalid = subprocess.run(
        [sys.executable, str(SCRIPT), '--camera', args.camera,
         '--stream', 'clear', '--duration', '5',
         '--event', '../bad', '--purpose', 'immich'],
        capture_output=True, text=True, timeout=8,
    )
    assert invalid.returncode != 0, 'Ungültige Ereignis-ID wurde akzeptiert'
    print('  OK', flush=True)

    print('02/03: Einzelaufnahme Clear und Fluent (inkl. Ton)', flush=True)
    first = invoke(args.camera, 'clear', 'immich', uuid.uuid4().hex, args.duration)
    second = invoke(args.camera, 'fluent', 'ntfy', uuid.uuid4().hex, args.duration)
    for video in (first, second):
        assert video['has_audio'], f"Keine Audiospur: {video['file']}"
        print(f"  OK {video['stream']}: {video['size_bytes']} Bytes, "
              f"Audio={video['has_audio']}", flush=True)

    print('03/03: Clear und Fluent parallel, gemeinsame Run-ID', flush=True)
    shared_id = uuid.uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(invoke, args.camera, 'clear', 'immich', shared_id, args.duration)
        b = pool.submit(invoke, args.camera, 'fluent', 'ntfy', shared_id, args.duration)
        clear, fluent = a.result(), b.result()
    assert clear['has_audio'] and fluent['has_audio'], 'Audio fehlt in paralleler Aufnahme'
    assert clear['file'] != fluent['file'], 'Dateikollision'
    print(f"  OK Clear: {clear['file']}", flush=True)
    print(f"  OK Fluent: {fluent['file']}", flush=True)
    print('\nGESAMTERGEBNIS: 3/3 Testblöcke erfolgreich', flush=True)
    print('Hinweis: Testdateien bleiben unter /media/kamera_events/modultest erhalten.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (AssertionError, subprocess.TimeoutExpired, OSError) as exc:
        print(f'GESAMTERGEBNIS: FEHLER: {exc}', file=sys.stderr)
        sys.exit(1)
