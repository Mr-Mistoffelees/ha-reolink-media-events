#!/usr/bin/env python3
"""Löscht genau eine erfolgreich zugestellte Kamera-Mediendatei.

Nur Dateien, die record_v2.py unter /media/kamera_events abgelegt hat.
Kein globbing, keine rekursive Löschung und keine Pfade als Eingabe.
"""
from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path

ROOT = Path('/media/kamera_events')
SAFE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')


class CleanupError(Exception):
    """Erwartbarer Fehler bei der lokalen Bereinigung."""


def safe_id(value: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise argparse.ArgumentTypeError(
            'Nur Buchstaben, Zahlen, _ und - erlaubt (max. 80 Zeichen).'
        )
    return value


def ensure_directory(path: Path, label: str) -> None:
    """Keinen symbolischen Link als Verzeichnis akzeptieren."""
    if path.is_symlink() or not path.is_dir():
        raise CleanupError(f'{label} fehlt oder ist kein echtes Verzeichnis: {path}')


def cleanup(event: str, run_id: str, purpose: str) -> dict:
    ensure_directory(ROOT, 'Medien-Wurzel')
    event_dir = ROOT / event
    run_dir = event_dir / run_id
    ensure_directory(event_dir, 'Ereignisverzeichnis')
    ensure_directory(run_dir, 'Durchlaufverzeichnis')

    path = run_dir / f'{purpose}.mp4'
    lock = run_dir / f'{purpose}.lock'
    if lock.exists() or lock.is_symlink():
        raise CleanupError('Aufnahme noch aktiv; Löschung verweigert')

    # lstat folgt Symlinks nicht; ausschließlich echte reguläre Dateien löschen.
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise CleanupError(f'Datei fehlt (nicht gelöscht): {path}') from None
    if not stat.S_ISREG(info.st_mode):
        raise CleanupError(f'Keine reguläre MP4-Datei (nicht gelöscht): {path}')

    path.unlink()
    # Nur leere Durchlaufordner entfernen. Dateien des anderen Zweigs,
    # .part-Dateien und Diagnosematerial bleiben erhalten.
    directory_removed = False
    try:
        run_dir.rmdir()
        directory_removed = True
    except OSError:
        pass

    return {
        'success': True,
        'deleted': True,
        'event_id': event,
        'run_id': run_id,
        'purpose': purpose,
        'file': str(path),
        'bytes_freed': info.st_size,
        'run_directory_removed': directory_removed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Kamera-Mediendatei sicher löschen')
    parser.add_argument('--event', required=True, type=safe_id)
    parser.add_argument('--run-id', required=True, type=safe_id)
    parser.add_argument('--purpose', required=True, choices=('ntfy', 'immich'))
    args = parser.parse_args()
    try:
        result = cleanup(args.event, args.run_id, args.purpose)
    except (CleanupError, OSError) as exc:
        print(f'BEREINIGUNGSFEHLER: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
