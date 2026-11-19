#!/usr/bin/env python3
"""Snapshots offline com verificação SHA-256 e criptografia opcional de arquivos."""

from __future__ import annotations

import argparse
import datetime as dt
import errno
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import stat
import sys
import tempfile
import unicodedata
from itertools import chain
from pathlib import Path, PurePosixPath

VERSION = '0.2.0'
FORMAT = 'backup-guardian-snapshot-v1'
MAGIC = b'BGUARD1\n'
BLOCK = 1024 * 1024
WINDOWS_DEVICE = re.compile(r'CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[0-9¹²³]', re.I)
# O bit Name Surrogate identifica redirecionamentos, como junções. Arquivos
# comuns do OneDrive também podem ser reparse points, com outra tag.
REPARSE_NAME_SURROGATE = 0x20000000


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as handle:
        while chunk := handle.read(BLOCK):
            checksum.update(chunk)
    return checksum.hexdigest()


def safe_rel(raw, *, portable=False):
    if not isinstance(raw, str) or not raw or '\\' in raw:
        raise ValueError('Caminho relativo inválido')
    segments = raw.split('/')
    if any(ord(char) < 32 or char in '<>:"|?*' for char in raw) or any(
        segment in ('', '.', '..') or segment.rstrip(' .') != segment for segment in segments
    ):
        raise ValueError(f'Caminho do manifesto inválido: {raw!r}')
    if (portable or os.name == 'nt') and any(
        WINDOWS_DEVICE.fullmatch(segment.partition('.')[0].rstrip(' ')) for segment in segments
    ):
        raise ValueError(f'Caminho usa nome reservado no Windows: {raw!r}')
    return PurePosixPath(raw)


def _check_type(path, info, *, directory):
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_reparse_tag', 0) & REPARSE_NAME_SURROGATE:
        raise ValueError(f'Link simbólico ou junção não suportado: {path}')
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise ValueError(f'Esperava uma pasta: {path}' if directory else f'Esperava um arquivo comum: {path}')


def _raise_walk_error(error):
    raise error


def _inventory(root):
    _check_type(root, root.lstat(), directory=True)
    directories = set()
    files = {}
    for base, dirnames, filenames in os.walk(root, onerror=_raise_walk_error, followlinks=False):
        for name in dirnames:
            path = Path(base) / name
            _check_type(path, path.lstat(), directory=True)
            directories.add(path.relative_to(root).as_posix())
        for name in filenames:
            path = Path(base) / name
            info = path.lstat()
            _check_type(path, info, directory=False)
            files[path.relative_to(root).as_posix()] = info
    return directories, files


def _fingerprint(info):
    common = (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns)
    # No Windows, lstat e fstat podem expor timestamps diferentes em st_ctime.
    return common if os.name == 'nt' else (*common, info.st_ctime_ns)


def _check_distinct_paths(paths):
    seen = {}
    for path in paths:
        key = unicodedata.normalize('NFC', path.casefold())
        if key in seen:
            raise ValueError(f'Caminhos equivalentes no manifesto: {seen[key]!r} e {path!r}')
        seen[key] = path


def _parent_directories(paths):
    return {
        parent.as_posix()
        for path in paths
        for parent in PurePosixPath(path).parents
        if parent.parts
    }


def _publish(stage, target):
    if os.name == 'nt':
        # os.rename no Windows falha se o destino já existe.
        os.rename(stage, target)
        return

    if sys.platform.startswith('linux'):
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, 'renameat2', None)
        if rename is not None:
            rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
            rename.restype = ctypes.c_int
            at_fdcwd = -100
            rename_noreplace = 1
            if rename(at_fdcwd, os.fsencode(stage), at_fdcwd, os.fsencode(target), rename_noreplace) == 0:
                return
            code = ctypes.get_errno()
            if code not in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
                raise OSError(code, os.strerror(code), str(target))

    if stage.is_file():
        os.link(stage, target)
        stage.unlink()
        return
    raise OSError(errno.ENOTSUP, 'O volume não permite publicar pastas sem risco de sobrescrever', str(target))


def _new_target(path):
    path = Path(path).expanduser()
    try:
        path.lstat()
    except FileNotFoundError:
        return path.parent.resolve() / path.name
    raise ValueError(f'O destino já existe: {path}')


def _copy_into_snapshot(source, target, name, original):
    checksum = hashlib.sha256()
    size = 0
    with source.open('rb') as inp, target.open('xb') as out:
        if _fingerprint(os.fstat(inp.fileno())) != _fingerprint(original):
            raise ValueError(f'A origem mudou durante o backup: {name}')
        while chunk := inp.read(BLOCK):
            out.write(chunk)
            checksum.update(chunk)
            size += len(chunk)
        if size != original.st_size or _fingerprint(os.fstat(inp.fileno())) != _fingerprint(original):
            raise ValueError(f'A origem mudou durante o backup: {name}')
        out.flush()
        os.fsync(out.fileno())
    return {'path': name, 'bytes': size, 'sha256': checksum.hexdigest()}


def create(source, vault):
    source = Path(source).expanduser()
    _check_type(source, source.lstat(), directory=True)
    source = source.resolve(strict=True)
    vault = Path(vault).expanduser()
    try:
        vault_info = vault.lstat()
    except FileNotFoundError:
        pass
    else:
        _check_type(vault, vault_info, directory=True)
    vault = vault.resolve()
    if source == vault or source in vault.parents or vault in source.parents:
        raise ValueError('Origem e destino não podem conter um ao outro')

    directories, files = _inventory(source)
    for name in chain(directories, files):
        safe_rel(name, portable=True)
    _check_distinct_paths(chain(directories, files))

    snapshots = vault / 'snapshots'
    snapshots.mkdir(parents=True, exist_ok=True)
    _check_type(snapshots, snapshots.lstat(), directory=True)
    name = dt.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + secrets.token_hex(3)
    stage = Path(tempfile.mkdtemp(prefix='.temp_', dir=snapshots))
    target = snapshots / name
    try:
        data = stage / 'arquivos'
        data.mkdir()
        for directory in sorted(directories):
            (data / directory).mkdir()
        entries = [
            _copy_into_snapshot(source / name, data / name, name, files[name])
            for name in sorted(files)
        ]
        manifest = {
            'format': FORMAT,
            'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'source_name': source.name,
            'directories': sorted(directories),
            'entries': entries,
        }
        with (stage / 'manifest.json').open('x', encoding='utf-8') as out:
            json.dump(manifest, out, ensure_ascii=False, indent=2)
            out.flush()
            os.fsync(out.fileno())

        report = verify(stage)
        _require_verified(report)
        current_dirs, current_files = _inventory(source)
        if directories != current_dirs or files.keys() != current_files.keys() or any(
            _fingerprint(files[name]) != _fingerprint(current_files[name]) for name in files
        ):
            raise ValueError('A origem mudou durante o backup')

        _publish(stage, target)
        return target, len(entries)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def load_manifest(snapshot):
    snapshot = Path(snapshot)
    _check_type(snapshot, snapshot.lstat(), directory=True)
    manifest_path = snapshot / 'manifest.json'
    _check_type(manifest_path, manifest_path.lstat(), directory=False)
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('format') != FORMAT or not isinstance(payload.get('entries'), list):
        raise ValueError('Formato de snapshot não reconhecido')

    portable = 'directories' in payload
    files = set()
    for item in payload['entries']:
        if (
            not isinstance(item, dict)
            or type(item.get('bytes')) is not int
            or item['bytes'] < 0
            or not isinstance(item.get('sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', item['sha256'])
        ):
            raise ValueError('Entrada inválida no manifesto')
        name = str(safe_rel(item.get('path'), portable=portable))
        if name in files:
            raise ValueError(f'Arquivo repetido no manifesto: {name}')
        files.add(name)

    directories = set()
    if portable:
        if not isinstance(payload['directories'], list):
            raise ValueError('Lista de pastas inválida no manifesto')
        for raw in payload['directories']:
            name = str(safe_rel(raw, portable=True))
            if name in directories:
                raise ValueError(f'Pasta repetida no manifesto: {name}')
            directories.add(name)
        for name in files | directories:
            parent = PurePosixPath(name).parent.as_posix()
            if parent != '.' and parent not in directories:
                raise ValueError(f'Pasta superior ausente no manifesto: {parent}')
    else:
        # Os snapshots 0.1 registravam somente arquivos e suas pastas implícitas.
        directories = _parent_directories(files)

    if files & directories:
        raise ValueError('O manifesto usa o mesmo caminho para arquivo e pasta')
    if portable:
        _check_distinct_paths(chain(files, directories))
    return payload


def _verify(snapshot, manifest):
    data = snapshot / 'arquivos'
    entries = {item['path']: item for item in manifest['entries']}
    problems = []
    report = {'ok': False, 'files': len(entries), 'problems': problems}
    try:
        data.lstat()
    except FileNotFoundError:
        if not entries and 'directories' not in manifest:
            report['ok'] = True
        else:
            problems.append('Pasta de arquivos ausente')
        return report
    except OSError as error:
        problems.append(str(error))
        return report
    try:
        directories, files = _inventory(data)
    except (OSError, ValueError) as error:
        problems.append(str(error))
        return report

    for name in sorted(files.keys() - entries.keys()):
        problems.append(f'Arquivo extra: {name}')
    if 'directories' in manifest:
        expected = set(manifest['directories'])
        problems.extend(f'Pasta ausente: {name}' for name in sorted(expected - directories))
        problems.extend(f'Pasta extra: {name}' for name in sorted(directories - expected))
    for name, item in entries.items():
        info = files.get(name)
        if info is None:
            problems.append(f'Arquivo ausente: {name}')
        elif info.st_size != item['bytes']:
            problems.append(f'Tamanho incorreto: {name}')
        else:
            try:
                if not hmac.compare_digest(digest(data / name), item['sha256']):
                    problems.append(f'SHA-256 divergente: {name}')
            except OSError as error:
                problems.append(f'Falha ao ler {name}: {error}')
    report['ok'] = not problems
    return report


def verify(snapshot):
    snapshot = Path(snapshot).expanduser()
    return _verify(snapshot, load_manifest(snapshot))


def _require_verified(report):
    if not report['ok']:
        summary = '\n'.join(report['problems'][:3])
        raise ValueError(f'Snapshot com falhas:\n{summary}')


def restore(snapshot, target):
    snapshot = Path(snapshot).expanduser()
    manifest = load_manifest(snapshot)
    snapshot = snapshot.resolve(strict=True)
    target = _new_target(target)
    if target == snapshot or snapshot in target.parents or target in snapshot.parents:
        raise ValueError('O destino e o snapshot não podem conter um ao outro')
    report = _verify(snapshot, manifest)
    _require_verified(report)

    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.restaurando_', dir=target.parent))
    try:
        directories = manifest.get('directories')
        if directories is None:
            directories = _parent_directories(item['path'] for item in manifest['entries'])
        for name in sorted(directories):
            (stage / name).mkdir()
        for entry in manifest['entries']:
            name = entry['path']
            source = snapshot / 'arquivos' / name
            out = stage / name
            with source.open('rb') as inp, out.open('xb') as output:
                shutil.copyfileobj(inp, output, BLOCK)
                output.flush()
                os.fsync(output.fileno())
            if out.stat().st_size != entry['bytes'] or not hmac.compare_digest(digest(out), entry['sha256']):
                raise ValueError(f'Cópia restaurada corrompida: {name}')
        _publish(stage, target)
        return target, report['files']
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def list_snapshots(vault):
    base = Path(vault).expanduser() / 'snapshots'
    try:
        info = base.lstat()
    except FileNotFoundError:
        return []
    _check_type(base, info, directory=True)
    snapshots = []
    for path in base.iterdir():
        if path.name.startswith('.'):
            continue
        try:
            load_manifest(path)
        except (OSError, ValueError):
            continue
        snapshots.append(path)
    return sorted(snapshots, reverse=True)


def _crypto():
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError as error:
        raise RuntimeError(
            'A criptografia requer o pacote cryptography. Instale com '
            'python -m pip install -r requirements-crypto.txt'
        ) from error
    return Cipher, algorithms, modes, Scrypt, InvalidTag


def _key(scrypt, password, salt):
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError('Use senha de pelo menos 12 caracteres')
    return scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode('utf-8'))


def _temp_file(target):
    target.parent.mkdir(parents=True, exist_ok=True)
    return tempfile.NamedTemporaryFile(mode='wb', prefix='.guardian-', dir=target.parent, delete=False)


def seal_file(source, target, password):
    Cipher, algorithms, modes, Scrypt, _ = _crypto()
    source = Path(source).expanduser()
    _check_type(source, source.lstat(), directory=False)
    target = _new_target(target)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    header = MAGIC + salt + nonce
    cipher = Cipher(algorithms.AES(_key(Scrypt, password, salt)), modes.GCM(nonce)).encryptor()
    cipher.authenticate_additional_data(header)

    out = _temp_file(target)
    temp = Path(out.name)
    try:
        with out, source.open('rb') as inp:
            initial = os.fstat(inp.fileno())
            out.write(header)
            while chunk := inp.read(BLOCK):
                out.write(cipher.update(chunk))
            if _fingerprint(os.fstat(inp.fileno())) != _fingerprint(initial):
                raise ValueError('O arquivo de origem mudou durante a criptografia')
            out.write(cipher.finalize())
            out.write(cipher.tag)
            out.flush()
            os.fsync(out.fileno())
        _publish(temp, target)
        return target
    finally:
        temp.unlink(missing_ok=True)


def unseal_file(source, target, password):
    Cipher, algorithms, modes, Scrypt, InvalidTag = _crypto()
    source = Path(source).expanduser()
    _check_type(source, source.lstat(), directory=False)
    target = _new_target(target)
    header_size = len(MAGIC) + 16 + 12
    tag_size = 16
    with source.open('rb') as inp:
        initial = os.fstat(inp.fileno())
        size = initial.st_size
        header = inp.read(header_size)
        if len(header) != header_size or size < header_size + tag_size:
            raise ValueError('Arquivo criptografado incompleto')
        if not header.startswith(MAGIC):
            raise ValueError('Formato criptografado inválido')
        salt = header[len(MAGIC):len(MAGIC) + 16]
        nonce = header[-12:]
        inp.seek(size - tag_size)
        tag = inp.read(tag_size)
        if len(tag) != tag_size:
            raise ValueError('Arquivo criptografado incompleto')
        cipher = Cipher(algorithms.AES(_key(Scrypt, password, salt)), modes.GCM(nonce, tag)).decryptor()
        cipher.authenticate_additional_data(header)

        out = _temp_file(target)
        temp = Path(out.name)
        try:
            with out:
                inp.seek(header_size)
                remaining = size - header_size - tag_size
                while remaining:
                    chunk = inp.read(min(BLOCK, remaining))
                    if not chunk:
                        raise ValueError('Arquivo criptografado incompleto')
                    out.write(cipher.update(chunk))
                    remaining -= len(chunk)
                try:
                    out.write(cipher.finalize())
                except InvalidTag as error:
                    raise ValueError('Senha incorreta ou arquivo adulterado') from error
                if _fingerprint(os.fstat(inp.fileno())) != _fingerprint(initial):
                    raise ValueError('O arquivo criptografado mudou durante a leitura')
                out.flush()
                os.fsync(out.fileno())
            _publish(temp, target)
            return target
        finally:
            temp.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=f'Backup Guardian v{VERSION} | backup offline com SHA-256')
    commands = parser.add_subparsers(dest='command', required=True)
    create_parser = commands.add_parser('create', help='Criar snapshot de uma pasta')
    create_parser.add_argument('source')
    create_parser.add_argument('vault')
    verify_parser = commands.add_parser('verify', help='Auditar snapshot inteiro')
    verify_parser.add_argument('snapshot')
    list_parser = commands.add_parser('list', help='Listar snapshots')
    list_parser.add_argument('vault')
    restore_parser = commands.add_parser('restore', help='Restaurar para pasta nova')
    restore_parser.add_argument('snapshot')
    restore_parser.add_argument('target')
    seal_parser = commands.add_parser('seal', help='Criptografar arquivo com AES-256-GCM')
    seal_parser.add_argument('source')
    seal_parser.add_argument('target')
    unseal_parser = commands.add_parser('unseal', help='Descriptografar arquivo BGUARD1')
    unseal_parser.add_argument('source')
    unseal_parser.add_argument('target')
    args = parser.parse_args(argv)

    try:
        if args.command == 'create':
            print('Criado:', *create(args.source, args.vault))
        elif args.command == 'verify':
            report = verify(args.snapshot)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['ok'] else 2
        elif args.command == 'list':
            for snapshot in list_snapshots(args.vault):
                print(snapshot)
        elif args.command == 'restore':
            print('Restaurado:', *restore(args.snapshot, args.target))
        else:
            password = getpass.getpass('Senha de criptografia: ')
            if args.command == 'seal':
                if password != getpass.getpass('Repita a senha: '):
                    raise ValueError('Senhas diferentes')
                print('Criptografado:', seal_file(args.source, args.target, password))
            else:
                print('Descriptografado:', unseal_file(args.source, args.target, password))
    except (OSError, ValueError, RuntimeError) as error:
        print('ERRO:', error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
