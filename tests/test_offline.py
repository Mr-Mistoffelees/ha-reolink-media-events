"""Non-network regression tests for the release package.

Runs without cameras, Home Assistant, ntfy or Immich. Uses temporary files only.
PyYAML and Jinja2 are test dependencies, not recorder dependencies.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cleanup_media as cm  # noqa: E402
import record_v2 as rec  # noqa: E402
import snapshot_media as sm  # noqa: E402


class BlueprintLoader(yaml.SafeLoader):
    pass


BlueprintLoader.add_constructor('!input', lambda loader, node: ('INPUT', loader.construct_scalar(node)))


def all_input_references(obj):
    if isinstance(obj, tuple) and obj[0] == 'INPUT':
        yield obj[1]
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from all_input_references(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from all_input_references(value)


class ReleaseShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = yaml.load(
            (ROOT / 'blueprints/automation/kamera_medien/reolink_medien.yaml').read_text(),
            Loader=BlueprintLoader,
        )
        cls.runtime = yaml.safe_load((ROOT / 'packages/kamera_medien_runtime.yaml').read_text())
        cls.snapshot = yaml.safe_load((ROOT / 'packages/kamera_medien_snapshot.yaml').read_text())

    def test_yaml_integrity_and_cross_references(self):
        bp = self.blueprint
        self.assertEqual(bp['blueprint']['domain'], 'automation')
        self.assertEqual(bp['mode'], 'parallel')
        self.assertEqual(len(bp['actions'][-1]['parallel']), 2)
        all_inputs = {
            key: v
            for section in bp['blueprint']['input'].values()
            for key, v in section.get('input', {}).items()
        }
        self.assertTrue(set(all_input_references(bp)) <= set(all_inputs))
        self.assertTrue({'event_id', 'detection_sensor', 'snapshot_camera',
                         'ntfy_mode', 'immich_mode', 'cleanup_files', 'debug'} <= set(all_inputs))
        self.assertIn('kamera_medien_video', self.runtime['script'])
        self.assertIn('kamera_medien_immich_bild', self.snapshot['script'])
        self.assertIn('kamera_medien_record_v2', self.runtime['shell_command'])
        self.assertIn('kamera_medien_cleanup', self.runtime['shell_command'])
        self.assertIn('kamera_medien_snapshot_file', self.snapshot['shell_command'])

    def test_independent_stream_choices_and_defaults(self):
        sections = self.blueprint['blueprint']['input']
        for section, field, default in [
            ('ntfy', 'ntfy_video_stream', 'fluent'),
            ('immich', 'immich_video_stream', 'clear'),
        ]:
            item = sections[section]['input'][field]
            self.assertEqual(item['default'], default)
            self.assertEqual({x['value'] for x in item['selector']['select']['options']},
                             {'fluent', 'clear'})
            self.assertEqual(self.blueprint['variables'][f'bp_{field}'], ('INPUT', field))
        branches = self.blueprint['actions'][-1]['parallel']
        scripts = []
        for branch in branches:
            for choice in branch['sequence'][0]['choose']:
                scripts.extend(step for step in choice['sequence']
                               if step.get('action') == 'script.kamera_medien_video')
        self.assertEqual(len(scripts), 2)
        by_purpose = {s['data']['purpose']: s['data'] for s in scripts}
        self.assertEqual(by_purpose['ntfy']['stream'], '{{ bp_ntfy_video_stream }}')
        self.assertEqual(by_purpose['immich']['stream'], '{{ bp_immich_video_stream }}')

    def test_runtime_defaults_without_stream_input(self):
        template = self.runtime['script']['kamera_medien_video']['sequence'][0]['variables']['_stream']
        env = Environment(undefined=StrictUndefined)
        for kwargs, value in [
            ({'purpose': 'ntfy'}, 'fluent'),
            ({'purpose': 'immich'}, 'clear'),
            ({'purpose': 'ntfy', 'stream': 'clear'}, 'clear'),
            ({'purpose': 'immich', 'stream': 'fluent'}, 'fluent'),
        ]:
            self.assertEqual(env.from_string(template).render(**kwargs).strip(), value)

    def test_config_example_is_valid_json_with_placeholders(self):
        config = json.loads((ROOT / 'examples/cameras.example.json').read_text())
        self.assertIn('garden_wide', config)
        self.assertIn('garden_tele', config)
        self.assertEqual(config['garden_wide']['host'], config['garden_tele']['host'])
        self.assertNotEqual(config['garden_wide']['channel'], config['garden_tele']['channel'])
        self.assertTrue(all('REPLACE_WITH' in cam['password'] for cam in config.values()))


class FilesystemSafetyTests(unittest.TestCase):
    def test_safe_identifiers(self):
        for module in (rec, cm, sm):
            self.assertEqual(module.safe_id('garden_pet-10'), 'garden_pet-10')
            for invalid in ('../tmp', 'a/b', '', 'evil;echo'):
                with self.assertRaises(argparse.ArgumentTypeError):
                    module.safe_id(invalid)

    def test_cleanup_deletes_only_selected_file(self):
        with tempfile.TemporaryDirectory() as td, patch.object(cm, 'ROOT', Path(td)):
            run = Path(td) / 'garden_pet' / 'run123'
            run.mkdir(parents=True)
            (run / 'ntfy.mp4').write_bytes(b'ntfy-video')
            (run / 'immich.mp4').write_bytes(b'immich-video')
            data = cm.cleanup('garden_pet', 'run123', 'ntfy')
            self.assertTrue(data['deleted'])
            self.assertFalse((run / 'ntfy.mp4').exists())
            self.assertTrue((run / 'immich.mp4').exists())

    def test_cleanup_respects_lock(self):
        with tempfile.TemporaryDirectory() as td, patch.object(cm, 'ROOT', Path(td)):
            run = Path(td) / 'garden_pet' / 'run123'
            run.mkdir(parents=True)
            (run / 'ntfy.mp4').write_bytes(b'file')
            (run / 'ntfy.lock').touch()
            with self.assertRaises(cm.CleanupError):
                cm.cleanup('garden_pet', 'run123', 'ntfy')
            self.assertTrue((run / 'ntfy.mp4').exists())

    def test_cleanup_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td, patch.object(cm, 'ROOT', Path(td)):
            run = Path(td) / 'garden_pet' / 'run123'
            run.mkdir(parents=True)
            victim = Path(td) / 'outside.mp4'
            victim.write_bytes(b'preserve')
            (run / 'ntfy.mp4').symlink_to(victim)
            with self.assertRaises(cm.CleanupError):
                cm.cleanup('garden_pet', 'run123', 'ntfy')
            self.assertEqual(victim.read_bytes(), b'preserve')

    def test_snapshot_safety(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'events'
            root.mkdir()
            with patch.object(sm, 'ROOT', root), patch.object(sm, 'SNAPSHOT_DIR', root / 'snapshots'):
                path = Path(sm.execute('prepare', 'garden_pet', 'run123')['file'])
                path.write_bytes(b'jpeg')
                self.assertTrue(sm.execute('cleanup', 'garden_pet', 'run123')['deleted'])
                self.assertFalse(path.exists())
                victim = Path(td) / 'outside.jpg'
                victim.write_bytes(b'private')
                path.symlink_to(victim)
                with self.assertRaises(sm.SnapshotFileError):
                    sm.execute('cleanup', 'garden_pet', 'run123')
                self.assertEqual(victim.read_bytes(), b'private')

    def test_rtsp_url_escaping_and_stream_selection(self):
        c = {'username': 'user@home', 'password': 'a/b?c',
             'host': '192.0.2.10', 'channel': 2, 'port': 554}
        main = rec.build_url(c, 'clear')
        sub = rec.build_url(c, 'fluent')
        self.assertIn('user%40home:a%2Fb%3Fc@', main)
        self.assertTrue(main.endswith('/Preview_02_main'))
        self.assertTrue(sub.endswith('/Preview_02_sub'))


if __name__ == '__main__':
    unittest.main()
