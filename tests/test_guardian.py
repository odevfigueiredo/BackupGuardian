import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backup_guardian as bg

CRYPTO_AVAILABLE = importlib.util.find_spec('cryptography') is not None


class GuardianTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.p=Path(self.temp.name).resolve()
        self.source=self.p/'source';self.source.mkdir();(self.source/'doc').mkdir()
        (self.source/'doc'/'a.txt').write_text('documentos de emergencia',encoding='utf-8')
        (self.source/'bin.dat').write_bytes(b'\x00\x01'*2200)
    def tearDown(self):self.temp.cleanup()
    def test_snapshot_verify_restore(self):
        snapshot,n=bg.create(self.source,self.p/'vault')
        self.assertEqual(n,2)
        self.assertTrue(bg.verify(snapshot)['ok'])
        target,n=bg.restore(snapshot,self.p/'restore')
        self.assertEqual(n,2);self.assertEqual((target/'doc'/'a.txt').read_text(),'documentos de emergencia')
    def test_detect_modified(self):
        snap,_=bg.create(self.source,self.p/'vault')
        (snap/'arquivos'/'bin.dat').write_bytes(b'Y'*4400)
        self.assertFalse(bg.verify(snap)['ok'])
        with self.assertRaises(ValueError):bg.restore(snap,self.p/'out')
    def test_detect_missing_extra(self):
        snap,_=bg.create(self.source,self.p/'vault')
        (snap/'arquivos'/'bin.dat').unlink()
        (snap/'arquivos'/'extra').write_text('extra')
        self.assertGreaterEqual(len(bg.verify(snap)['problems']),2)
    def test_blocks_nested_destination(self):
        with self.assertRaises(ValueError):bg.create(self.source,self.source/'backup')
    def test_reject_symlinks(self):
        try:(self.source/'link').symlink_to(self.source/'doc'/'a.txt')
        except OSError:self.skipTest('symlink unsupported')
        with self.assertRaises(ValueError):bg.create(self.source,self.p/'vault')
    def test_reject_unsafe_manifest(self):
        snap,_=bg.create(self.source,self.p/'vault')
        m=snap/'manifest.json'
        d=json.loads(m.read_text());d['entries'][0]['path']='../../outside';m.write_text(json.dumps(d))
        with self.assertRaises(ValueError):bg.verify(snap)
    def test_no_overwrite_restore(self):
        snap,_=bg.create(self.source,self.p/'vault')
        self.assertRaises(ValueError,bg.restore,snap,self.source)
    def test_list(self):
        bg.create(self.source,self.p/'vault');self.assertEqual(len(bg.list_snapshots(self.p/'vault')),1)

    def test_preserves_empty_directories(self):
        (self.source / 'documentos' / 'vazia').mkdir(parents=True)
        snapshot, files = bg.create(self.source, self.p / 'vault')

        self.assertEqual(files, 2)
        self.assertTrue(bg.verify(snapshot)['ok'])
        target, restored_files = bg.restore(snapshot, self.p / 'restored')
        self.assertEqual(restored_files, 2)
        self.assertTrue((target / 'documentos' / 'vazia').is_dir())

        (snapshot / 'arquivos' / 'documentos' / 'vazia').rmdir()
        self.assertFalse(bg.verify(snapshot)['ok'])

    def test_restores_legacy_snapshot_without_directories_field(self):
        snapshot, files = bg.create(self.source, self.p / 'vault')
        manifest = snapshot / 'manifest.json'
        contents = json.loads(manifest.read_text(encoding='utf-8'))
        contents.pop('directories', None)
        manifest.write_text(json.dumps(contents), encoding='utf-8')

        self.assertTrue(bg.verify(snapshot)['ok'])
        target, restored_files = bg.restore(snapshot, self.p / 'restored')
        self.assertEqual(restored_files, files)
        self.assertEqual((target / 'bin.dat').read_bytes(), (self.source / 'bin.dat').read_bytes())

    def test_restores_empty_legacy_snapshot_without_files_directory(self):
        snapshot = self.p / 'legacy-empty'
        snapshot.mkdir()
        (snapshot / 'manifest.json').write_text(
            json.dumps({
                'format': bg.FORMAT,
                'created_utc': '2025-11-14T13:00:00+00:00',
                'source_name': 'vazia',
                'entries': [],
            }),
            encoding='utf-8',
        )

        self.assertTrue(bg.verify(snapshot)['ok'])
        target, restored_files = bg.restore(snapshot, self.p / 'restored')
        self.assertEqual(restored_files, 0)
        self.assertEqual(list(target.iterdir()), [])

    def test_directory_traversal_error_aborts_snapshot(self):
        blocked = self.source / 'doc'
        scandir = os.scandir

        def deny_blocked_directory(path):
            if Path(path) == blocked:
                raise PermissionError(f'Pasta indisponível: {path}')
            return scandir(path)

        vault = self.p / 'vault'
        with patch.object(bg.os, 'scandir', side_effect=deny_blocked_directory):
            with self.assertRaises((PermissionError, ValueError)):
                bg.create(self.source, vault)
        self.assertEqual(list(vault.glob('snapshots/*')), [])

    def test_list_ignores_staging_and_invalid_manifests(self):
        vault = self.p / 'vault'
        snapshot, _ = bg.create(self.source, vault)
        base = snapshot.parent
        shutil.copytree(snapshot, base / '.temp_late_stage')
        (base / '20000101_000000_000000').mkdir()
        invalid = base / '20000101_000000_000001'
        invalid.mkdir()
        (invalid / 'manifest.json').write_text('[]', encoding='utf-8')

        self.assertEqual(bg.list_snapshots(vault), [snapshot])

    def test_rejects_malformed_manifest(self):
        snapshot, _ = bg.create(self.source, self.p / 'vault')
        manifest = snapshot / 'manifest.json'
        contents = json.loads(manifest.read_text(encoding='utf-8'))
        contents['entries'][0]['bytes'] = True

        for malformed in [[], contents]:
            with self.subTest(manifest_type=type(malformed).__name__):
                manifest.write_text(json.dumps(malformed), encoding='utf-8')
                with self.assertRaises(ValueError):
                    bg.verify(snapshot)

    def test_restore_preserves_directory_created_during_operation(self):
        snapshot, _ = bg.create(self.source, self.p / 'vault')
        target = self.p / 'restored'
        parent_contents = set(self.p.iterdir())
        mkdtemp = tempfile.mkdtemp

        def create_competing_directory(*args, **kwargs):
            stage = mkdtemp(*args, **kwargs)
            target.mkdir()
            return stage

        with patch.object(bg.tempfile, 'mkdtemp', side_effect=create_competing_directory):
            with self.assertRaises((FileExistsError, ValueError)):
                bg.restore(snapshot, target)
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(set(self.p.iterdir()), parent_contents | {target})

    @unittest.skipUnless(os.name == 'nt', 'junções são específicas do Windows')
    def test_rejects_windows_junction_in_source(self):
        try:
            from _winapi import CreateJunction

            CreateJunction(str(self.source / 'doc'), str(self.source / 'junction'))
        except (ImportError, OSError):
            self.skipTest('criação de junção indisponível')
        with self.assertRaises(ValueError):
            bg.create(self.source, self.p / 'vault')

    @unittest.skipUnless(os.name == 'nt', 'junções são específicas do Windows')
    def test_rejects_snapshot_junction_before_hashing_files(self):
        snapshot, _ = bg.create(self.source, self.p / 'vault')
        data = snapshot / 'arquivos'
        shutil.rmtree(data)
        try:
            from _winapi import CreateJunction

            CreateJunction(str(self.source), str(data))
        except (ImportError, OSError):
            self.skipTest('criação de junção indisponível')
        with patch.object(bg, 'digest', side_effect=AssertionError('leitura através de junção')):
            self.assertFalse(bg.verify(snapshot)['ok'])

    def test_source_change_aborts_publication(self):
        vault = self.p / 'vault'
        verify = bg.verify

        def add_file_after_verification(stage):
            report = verify(stage)
            (self.source / 'novo.txt').write_bytes(b'arquivo criado durante o backup')
            return report

        with patch.object(bg, 'verify', side_effect=add_file_after_verification):
            with self.assertRaisesRegex(ValueError, 'origem mudou'):
                bg.create(self.source, vault)
        self.assertEqual(list(vault.glob('snapshots/*')), [])

    @unittest.skipUnless(CRYPTO_AVAILABLE, 'cryptography opcional ausente')
    def test_encrypt_roundtrip(self):
        enc=self.p/'backup.bgc';back=self.p/'back.bin'
        bg.seal_file(self.source/'bin.dat',enc,'senha-segura-de-teste-123')
        bg.unseal_file(enc,back,'senha-segura-de-teste-123')
        self.assertEqual(back.read_bytes(),(self.source/'bin.dat').read_bytes())

    @unittest.skipUnless(CRYPTO_AVAILABLE, 'cryptography opcional ausente')
    def test_encryption_preserves_file_created_during_operation(self):
        source = self.source / 'bin.dat'
        target = self.p / 'encrypted.bgc'
        parent_contents = set(self.p.iterdir())
        open_temp = tempfile.NamedTemporaryFile

        def create_competing_file(*args, **kwargs):
            stage = open_temp(*args, **kwargs)
            target.write_bytes(b'arquivo existente')
            return stage

        with patch.object(bg.tempfile, 'NamedTemporaryFile', side_effect=create_competing_file):
            with self.assertRaises((FileExistsError, ValueError)):
                bg.seal_file(source, target, 'senha-segura-de-teste-123')
        self.assertEqual(target.read_bytes(), b'arquivo existente')
        self.assertEqual(set(self.p.iterdir()), parent_contents | {target})

    @unittest.skipUnless(CRYPTO_AVAILABLE, 'cryptography opcional ausente')
    def test_wrong_password_no_partial(self):
        enc=self.p/'backup.bgc';back=self.p/'back.bin';bg.seal_file(self.source/'bin.dat',enc,'senha-segura-de-teste-123')
        with self.assertRaises(ValueError):bg.unseal_file(enc,back,'senha-errada-123456')
        self.assertFalse(back.exists())

    @unittest.skipUnless(CRYPTO_AVAILABLE, 'cryptography opcional ausente')
    def test_tamper_detected(self):
        enc=self.p/'backup.bgc';back=self.p/'back.bin';bg.seal_file(self.source/'bin.dat',enc,'senha-segura-de-teste-123')
        with enc.open('r+b') as f:f.seek(40);f.write(b'x')
        with self.assertRaises(ValueError):bg.unseal_file(enc,back,'senha-segura-de-teste-123')

    @unittest.skipUnless(CRYPTO_AVAILABLE, 'cryptography opcional ausente')
    def test_disallow_short_password(self):
        with self.assertRaises(ValueError):bg.seal_file(self.source/'bin.dat',self.p/'new.bgc','123')

if __name__=='__main__':unittest.main(verbosity=2)
