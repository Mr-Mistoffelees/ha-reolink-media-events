#!/usr/bin/env python3
"""Sichere Dateivorbereitung und -bereinigung für Immich-Snapshots.

Aufgerufen von Home Assistant im Container. Keine freien Dateipfade, nur
validierte Ereignis-/Run-Kennungen. Die Kameraaufnahme macht HA camera.snapshot.
"""
from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path

ROOT = Path('/media/kamera_events')
SNAPSHOT_DIR = ROOT / 'snapshots'
SAFE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')


class SnapshotFileError(Exception):
    pass


def safe_id(value: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise argparse.ArgumentTypeError('Kennung muss 1-80 sichere Zeichen enthalten')
    return value


def target(event: str, run_id: str) -> Path:
    return SNAPSHOT_DIR / f'{event}__{run_id}.jpg'


def check_dir(directory: Path, label: str) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise SnapshotFileError(f'{label} fehlt oder ist kein echtes Verzeichnis')


def execute(action: str, event: str, run_id: str) -> dict:
    check_dir(ROOT, 'Medienbasis')
    if action == 'prepare':
        if SNAPSHOT_DIR.is_symlink():
            raise SnapshotFileError('Snapshot-Verzeichnis darf kein Symlink sein')
        SNAPSHOT_DIR.mkdir(mode=0o700, exist_ok=True)
    check_dir(SNAPSHOT_DIR, 'Snapshot-Verzeichnis')
    path = target(event, run_id)
    if action == 'prepare':
        # Schutz vor Wiederverwendung des gleichen Dateinamens und Symlinks.
        if path.exists() or path.is_symlink():
            raise SnapshotFileError('Snapshot-Dateiname ist bereits belegt')
        return {'success': True, 'action': action, 'file': str(path)}
    if action == 'cleanup':
        try:
            info = path.lstat()
        except FileNotFoundError:
            raise SnapshotFileError('Snapshot-Datei zum Löschen nicht vorhanden') from None
        if not stat.S_ISREG(info.st_mode):
            raise SnapshotFileError('Snapshot-Datei ist kein regulärer Dateityp')
        path.unlink()
        return {
            'success': True, 'action': action, 'deleted': True,
            'file': str(path), 'bytes_freed': info.st_size,
        }
    raise SnapshotFileError('Unbekannte Aktion')


def main() -> int:
    parser = argparse.ArgumentParser(description='HA Immich-Snapshot-Dateiverwaltung')
    parser.add_argument('--action', required=True, choices=('prepare', 'cleanup'))
    parser.add_argument('--event', required=True, type=safe_id)
    parser.add_argument('--run-id', required=True, type=safe_id)
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args.action, args.event, args.run_id)))
        return 0
    except (SnapshotFileError, OSError) as exc:
        print(f'SNAPSHOT-DATEIFEHLER: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
