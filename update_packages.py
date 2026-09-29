"""Download and verify official Windows updates without running their contents.

The GitHub release API authenticates the asset digests over HTTPS. Every file is
then verified against the downloaded manifest before a staged package is usable.
This module neither starts processes nor touches the current installation.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile


REPOSITORY = 'X-Zero-L/dawn-atelier'
LATEST_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
RELEASES_URL = f'https://github.com/{REPOSITORY}/releases'
JSON_LIMIT = 4 * 1024 * 1024
ARCHIVE_LIMIT = 128 * 1024 * 1024
PAYLOAD_LIMIT = 512 * 1024 * 1024
ENTRY_LIMIT = 10000
TIMEOUT = 30
CHUNK_SIZE = 128 * 1024
PACKAGE_FORMAT = 'dawn-atelier-windows-package-v1'
MARKER_NAME = 'ready.json'
_SHA256 = re.compile(r'[0-9a-f]{64}')
_VERSION = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')
_ASSET_HOSTS = {'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
_DEVICES = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} | {
    prefix + suffix for prefix in ('COM', 'LPT') for suffix in '123456789¹²³'
}


class UpdateError(ValueError):
    """An update was unavailable, unsafe, incomplete, or inconsistent."""


class UpdateCancelled(UpdateError):
    """The caller cancelled an update before it became ready."""


def parse_version(text):
    """Return a comparable numeric release version; reject pre-release labels."""
    if not isinstance(text, str) or len(text) > 23 or not _VERSION.fullmatch(text):
        raise UpdateError('更新版本号无效，应为三段数字。')
    version = tuple(int(part) for part in text.split('.'))
    if any(part > 65535 for part in version):
        raise UpdateError('更新版本号超出 Windows 支持的范围。')
    return version


def _cancelled(cancel):
    if cancel is not None and (cancel() if callable(cancel) else cancel.is_set()):
        raise UpdateCancelled('更新已取消。')


def _progress(callback, percent, message):
    if callback is not None:
        callback(max(0, min(100, int(percent))), message)


def _check_url(url, initial):
    if not isinstance(url, str) or any(ord(character) < 33 for character in url) or '\\' in url:
        raise UpdateError('更新下载地址无效。')
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise UpdateError('更新下载地址无效。') from error
    if (parsed.scheme != 'https' or parsed.username is not None or parsed.password is not None
            or port not in (None, 443) or parsed.fragment):
        raise UpdateError('更新只能通过 GitHub 的 HTTPS 地址下载。')
    if initial == LATEST_URL:
        allowed = url == LATEST_URL
    else:
        allowed = url == initial or parsed.hostname in _ASSET_HOSTS
    if not allowed:
        raise UpdateError('更新下载被重定向到了未授权的地址。')


class _OfficialRedirects(HTTPRedirectHandler):
    max_redirections = 6
    max_repeats = 2

    def __init__(self, initial):
        super().__init__()
        self.initial = initial

    def redirect_request(self, request, response, code, message, headers, newurl):
        _check_url(newurl, self.initial)
        return super().redirect_request(request, response, code, message, headers, newurl)


def _transfer(url, limit, destination=None, expected=None, progress=None, cancel=None):
    """Bound network reads and verify length/digest before returning any data."""
    if url != LATEST_URL and not re.fullmatch(
            re.escape(RELEASES_URL) + r'/download/v([0-9]+\.[0-9]+\.[0-9]+)/DawnAtelier-\1-windows-x64\.(zip|manifest\.json)', url):
        raise UpdateError('更新文件必须来自黎明工坊的正式发布仓库。')
    _check_url(url, url)
    _cancelled(cancel)
    request = Request(url, headers={
        'User-Agent': 'DawnAtelier-updater',
        'Accept': 'application/vnd.github+json' if url == LATEST_URL else 'application/octet-stream',
        'Accept-Encoding': 'identity',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    opener = build_opener(_OfficialRedirects(url))
    data = bytearray() if destination is None else None
    digest, count = hashlib.sha256(), 0
    with opener.open(request, timeout=TIMEOUT) as response:
        _check_url(response.geturl(), url)
        if response.status != 200:
            raise UpdateError(f'更新服务器返回了状态 {response.status}。')
        if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
            raise UpdateError('更新服务器返回了不支持的压缩传输。')
        length_header = response.headers.get('Content-Length')
        declared = None
        if length_header is not None:
            try:
                declared = int(length_header)
            except (ValueError, TypeError) as error:
                raise UpdateError('更新下载大小无效。') from error
            if declared < 0 or declared > limit or (expected and declared != expected['bytes']):
                raise UpdateError('更新下载大小与发布记录不符。')
        while True:
            _cancelled(cancel)
            block = response.read(min(CHUNK_SIZE, limit - count + 1))
            if not block:
                break
            count += len(block)
            if count > limit or (expected and count > expected['bytes']):
                raise UpdateError('更新下载超出允许大小。')
            digest.update(block)
            if destination is None:
                data.extend(block)
            else:
                destination.write(block)
            if progress is not None:
                progress(count)
    _cancelled(cancel)
    if declared is not None and count != declared:
        raise UpdateError('更新下载不完整，请重试。')
    if expected and (count != expected['bytes'] or digest.hexdigest() != expected['sha256']):
        raise UpdateError('更新文件校验失败，请重新下载。')
    return bytes(data) if data is not None else None


def _json(data):
    if len(data) > JSON_LIMIT:
        raise UpdateError('更新清单超出允许大小。')

    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise UpdateError('更新清单包含重复字段。')
            value[key] = item
        return value

    try:
        value = json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite JSON')))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise UpdateError('更新清单格式无效。') from error
    if not isinstance(value, dict):
        raise UpdateError('更新清单必须是一个对象。')
    return value


def _size(value, limit, allow_empty=False):
    if type(value) is not int or value < (0 if allow_empty else 1) or value > limit:
        raise UpdateError('更新文件大小无效或超出允许范围。')
    return value


def _sha(value):
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise UpdateError('更新文件缺少有效的 SHA-256 校验值。')
    return value


def _asset(version, extension, value, api=False):
    name = f'DawnAtelier-{version}-windows-x64.{extension}'
    url = f'{RELEASES_URL}/download/v{version}/{name}'
    if not isinstance(value, dict):
        raise UpdateError('更新发布缺少完整的 Windows 下载文件。')
    digest = value.get('digest') if api else value.get('sha256')
    if api:
        if not isinstance(digest, str) or not digest.startswith('sha256:'):
            raise UpdateError('更新发布缺少 GitHub 提供的 SHA-256 校验值。')
        digest = digest[7:]
    actual_url = value.get('browser_download_url') if api else value.get('url')
    if value.get('name', name) != name or actual_url != url:
        raise UpdateError('更新文件必须来自黎明工坊的正式发布仓库。')
    return {'name': name, 'url': url,
            'bytes': _size(value.get('size') if api else value.get('bytes'),
                           ARCHIVE_LIMIT if extension == 'zip' else JSON_LIMIT),
            'sha256': _sha(digest)}


def latest_release(current_version):
    """Return a newer official stable release, or None when already current."""
    current = parse_version(current_version)
    try:
        release = _json(_transfer(LATEST_URL, JSON_LIMIT))
    except HTTPError as error:
        if error.code == 404:
            return None
        raise UpdateError('暂时无法检查更新，请稍后重试。') from error
    if release.get('draft') is not False or release.get('prerelease') is not False:
        return None
    tag = release.get('tag_name', '')
    if not isinstance(tag, str) or not tag.startswith('v'):
        raise UpdateError('正式发布的版本标签无效。')
    version = tag[1:]
    if parse_version(version) <= current:
        return None
    assets = release.get('assets')
    if not isinstance(assets, list):
        raise UpdateError('更新发布没有可用的 Windows 文件。')
    found = {}
    for key, extension in (('archive', 'zip'), ('manifest', 'manifest.json')):
        name = f'DawnAtelier-{version}-windows-x64.{extension}'
        matching = [asset for asset in assets if isinstance(asset, dict) and asset.get('name') == name]
        if len(matching) != 1 or matching[0].get('state') != 'uploaded':
            raise UpdateError('更新发布的 Windows 文件尚未完整上传。')
        found[key] = _asset(version, extension, matching[0], api=True)
    return {'version': version, 'tag': tag, 'url': f'{RELEASES_URL}/tag/{tag}',
            'notes': str(release.get('body') or '')[:32768], **found}


def _path_parts(name):
    if (not isinstance(name, str) or not name or len(name) > 1024 or '\\' in name
            or name.startswith('/') or name.endswith('/')):
        raise UpdateError('更新包包含无效的文件路径。')
    parts = name.split('/')
    for part in parts:
        if (part in ('', '.', '..') or len(part) > 255 or part.endswith(('.', ' '))
                or any(ord(character) < 32 or character in ':"<>|?*' for character in part)
                or part.split('.')[0].upper() in _DEVICES):
            raise UpdateError('更新包包含不安全的 Windows 文件路径。')
    return parts


def _check_link(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise UpdateError('更新目录不能包含符号链接或目录联接。')
    return info


def _directory(path, create=False):
    directory = Path(os.path.abspath(os.fspath(path)))
    for component in (*reversed(directory.parents), directory):
        try:
            info = _check_link(component)
        except FileNotFoundError:
            if not create:
                raise UpdateError('更新目录不存在。') from None
            component.mkdir()
            info = _check_link(component)
        if not stat.S_ISDIR(info.st_mode):
            raise UpdateError('更新目录路径中包含非目录文件。')
    if directory.resolve() != directory:
        raise UpdateError('更新目录被重定向到了其他位置。')
    return directory


def _file_bytes(path, limit):
    info = _check_link(path)
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit or info.st_nlink != 1:
        raise UpdateError('更新清单文件无效。')
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise UpdateError('更新清单超出允许大小。')
    return value


def _manifest(value, expected_version=None, external=False):
    version = value.get('version')
    parse_version(version)
    if expected_version is not None and version != expected_version:
        raise UpdateError('更新包的版本号与发布记录不符。')
    if (value.get('format') != PACKAGE_FORMAT or value.get('platform') != 'windows-x64'
            or value.get('architecture') != 'AMD64' or value.get('entryPoint') != 'DawnAtelier.exe'):
        raise UpdateError('更新包不是受支持的 Windows x64 黎明工坊。')
    if not external and 'archive' in value:
        raise UpdateError('更新包内的清单格式无效。')
    files = value.get('files')
    if not isinstance(files, list) or not files or len(files) >= ENTRY_LIMIT:
        raise UpdateError('更新包的文件列表无效。')
    paths, prefixes, total = {}, {}, 0
    for item in files:
        if not isinstance(item, dict):
            raise UpdateError('更新包的文件记录无效。')
        name = item.get('path')
        parts = _path_parts(name)
        key = name.casefold()
        if key in paths or key == 'package-manifest.json':
            raise UpdateError('更新包的文件清单包含重复路径。')
        paths[key] = name
        for index in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:index])
            if prefix.casefold() in prefixes and prefixes[prefix.casefold()] != prefix:
                raise UpdateError('更新包包含大小写冲突的路径。')
            prefixes[prefix.casefold()] = prefix
        total += _size(item.get('bytes'), PAYLOAD_LIMIT, allow_empty=True)
        _sha(item.get('sha256'))
    if total > PAYLOAD_LIMIT:
        raise UpdateError('更新包展开后超出允许大小。')
    for name in paths.values():
        if any('/'.join(name.split('/')[:index]).casefold() in paths
               for index in range(1, len(name.split('/')))):
            raise UpdateError('更新包包含文件和目录冲突。')
    if not {'DawnAtelier.exe', '_internal/version.json'}.issubset(set(paths.values())):
        raise UpdateError('更新包缺少程序或版本文件。')
    return value


def _verify_pe(path):
    with path.open('rb') as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise UpdateError('更新程序不是 Windows 可执行文件。')
        offset = struct.unpack_from('<I', header, 0x3C)[0]
        if offset < 64 or offset > 1024 * 1024:
            raise UpdateError('更新程序的 Windows 文件头无效。')
        stream.seek(offset)
        pe = stream.read(94)
    if (len(pe) < 94 or pe[:4] != b'PE\0\0' or struct.unpack_from('<H', pe, 4)[0] != 0x8664
            or struct.unpack_from('<H', pe, 24)[0] != 0x20B
            or struct.unpack_from('<H', pe, 92)[0] != 2):
        raise UpdateError('更新程序必须是 Windows x64 图形程序。')


def verify_installation(directory, expected_version=None, *, allow_extra=False):
    """Verify an exact unpacked payload, including every file and embedded version.

    Extra files are rejected by default. allow_extra validates only declared
    payload files in a current user installation; it never scans unrelated user
    folders. Staged and rollback packages must use the default exact check.
    """
    directory = _directory(directory)
    manifest = _manifest(_json(_file_bytes(directory / 'package-manifest.json', JSON_LIMIT)), expected_version)
    expected = {item['path']: item for item in manifest['files']}
    if allow_extra:
        for relative, record in expected.items():
            path = directory.joinpath(*relative.split('/'))
            _directory(path.parent)
            info = _check_link(path)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != record['bytes']:
                raise UpdateError(f'更新包文件与清单不符：{relative}')
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest != record['sha256']:
                raise UpdateError(f'更新包文件校验失败：{relative}')
        version = _json(_file_bytes(directory / '_internal/version.json', JSON_LIMIT))
        if version.get('version') != manifest['version']:
            raise UpdateError('程序内的版本号与更新清单不符。')
        _verify_pe(directory / 'DawnAtelier.exe')
        return manifest
    actual, directories, total = set(), [directory], 0
    while directories:
        for path in directories.pop().iterdir():
            relative = path.relative_to(directory).as_posix()
            _path_parts(relative)
            info = _check_link(path)
            if stat.S_ISDIR(info.st_mode):
                directories.append(path)
                if not any(name.startswith(relative + '/') for name in expected):
                    raise UpdateError('更新目录包含清单之外的目录。')
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise UpdateError('更新包包含非普通文件。')
            actual.add(relative)
            total += info.st_size
            if len(actual) > ENTRY_LIMIT or total > PAYLOAD_LIMIT:
                raise UpdateError('更新包展开后超出允许大小。')
            if relative == 'package-manifest.json':
                continue
            record = expected.get(relative)
            if record is None or info.st_size != record['bytes']:
                raise UpdateError(f'更新包文件与清单不符：{relative}')
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest != record['sha256']:
                raise UpdateError(f'更新包文件校验失败：{relative}')
    if actual != set(expected) | {'package-manifest.json'}:
        raise UpdateError('更新包缺少清单中声明的文件。')
    version = _json(_file_bytes(directory / '_internal/version.json', JSON_LIMIT))
    if version.get('version') != manifest['version']:
        raise UpdateError('程序内的版本号与更新清单不符。')
    _verify_pe(directory / 'DawnAtelier.exe')
    return manifest


def _extract(archive, target, cancel=None, progress=None):
    with zipfile.ZipFile(archive) as zipped:
        entries = zipped.infolist()
        if not entries or len(entries) > ENTRY_LIMIT:
            raise UpdateError('更新压缩包的文件数量超出允许范围。')
        total, seen, paths, files = 0, set(), {}, set()
        for item in entries:
            _cancelled(cancel)
            if item.orig_filename != item.filename:
                raise UpdateError('更新压缩包包含无效的文件路径。')
            name = item.filename[:-1] if item.is_dir() else item.filename
            parts = _path_parts(name)
            if parts[0] != 'DawnAtelier' or (len(parts) == 1 and not item.is_dir()):
                raise UpdateError('更新压缩包的根目录无效。')
            if name.casefold() in seen:
                raise UpdateError('更新压缩包包含重复路径。')
            seen.add(name.casefold())
            if not item.is_dir():
                files.add(name.casefold())
            for index in range(1, len(parts) + 1):
                prefix = '/'.join(parts[:index])
                if prefix.casefold() in paths and paths[prefix.casefold()] != prefix:
                    raise UpdateError('更新压缩包包含大小写冲突的路径。')
                paths[prefix.casefold()] = prefix
            mode = stat.S_IFMT(item.external_attr >> 16)
            if (mode not in (0, stat.S_IFDIR if item.is_dir() else stat.S_IFREG)
                    or item.external_attr & 0x400 or item.flag_bits & 1
                    or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                raise UpdateError('更新压缩包包含链接、加密文件或不支持的压缩方式。')
            total += item.file_size
            if item.file_size < 0 or total > PAYLOAD_LIMIT or (item.is_dir() and item.file_size):
                raise UpdateError('更新压缩包展开后超出允许大小。')
        for name in seen:
            parts = name.split('/')
            if any('/'.join(parts[:index]) in files for index in range(1, len(parts))):
                raise UpdateError('更新压缩包包含文件和目录冲突。')
        consumed = 0
        for item in entries:
            _cancelled(cancel)
            output = target.joinpath(*item.filename.rstrip('/').split('/'))
            if not output.is_relative_to(target):
                raise UpdateError('更新解压路径超出暂存目录。')
            if item.is_dir():
                _directory(output, create=True)
                continue
            _directory(output.parent, create=True)
            written = 0
            with zipped.open(item) as source, output.open('xb') as destination:
                while True:
                    _cancelled(cancel)
                    block = source.read(min(CHUNK_SIZE, item.file_size - written + 1))
                    if not block:
                        break
                    written += len(block)
                    if written > item.file_size:
                        raise UpdateError('更新压缩包的文件大小与声明不符。')
                    destination.write(block)
            if written != item.file_size:
                raise UpdateError('更新压缩包不完整。')
            consumed += written
            _progress(progress, 75 + 15 * consumed / max(1, total), '正在展开并核对更新文件…')


def _external_manifest(data, release):
    manifest = _manifest(_json(data), release['version'], external=True)
    expected = release['archive']
    if manifest.get('archive') != {key: expected[key] for key in ('name', 'bytes', 'sha256')}:
        raise UpdateError('下载清单与 GitHub 发布的压缩包校验值不符。')
    return manifest


def _verify_stage(stage, release):
    stage = _directory(stage)
    if {item.name for item in stage.iterdir()} != {'DawnAtelier', 'release-manifest.json', MARKER_NAME}:
        raise UpdateError('已下载的更新目录不完整，请清理该暂存版本后重试。')
    marker = _json(_file_bytes(stage / MARKER_NAME, JSON_LIMIT))
    if marker != {'version': release['version'], 'archive_sha256': release['archive']['sha256'],
                  'manifest_sha256': release['manifest']['sha256']}:
        raise UpdateError('已下载的更新与当前发布不一致。')
    data = _file_bytes(stage / 'release-manifest.json', JSON_LIMIT)
    if len(data) != release['manifest']['bytes'] or hashlib.sha256(data).hexdigest() != release['manifest']['sha256']:
        raise UpdateError('已下载的更新清单校验失败。')
    external = _external_manifest(data, release)
    embedded = verify_installation(stage / 'DawnAtelier', release['version'])
    if embedded != {key: value for key, value in external.items() if key != 'archive'}:
        raise UpdateError('更新包内外的文件清单不一致。')


def _remove_temporary(path, parent):
    """Delete only the unique directory created by this download, never a link."""
    try:
        checked = _directory(path)
        if checked.parent != _directory(parent):
            return
        for directory, names, files in os.walk(checked, followlinks=False):
            for name in names + files:
                _check_link(Path(directory) / name)
        shutil.rmtree(checked)
    except (OSError, UpdateError):
        pass


def stage_release(release, cache_root, progress=None, cancel=None, *, cancelled=None):
    """Download, verify, and atomically stage a release under cache_root/versions."""
    if cancelled is not None:
        if cancel is not None:
            raise TypeError('Pass either cancel or cancelled, not both.')
        cancel = cancelled
    if not isinstance(release, dict):
        raise UpdateError('更新发布信息无效。')
    version = release.get('version')
    parse_version(version)
    release = {'version': version,
               'archive': _asset(version, 'zip', release.get('archive')),
               'manifest': _asset(version, 'manifest.json', release.get('manifest'))}
    _cancelled(cancel)
    versions = _directory(_directory(cache_root, create=True) / 'versions', create=True)
    destination = versions / f"{version}-{release['archive']['sha256'][:16]}"
    result = {'version': version, 'directory': str(destination / 'DawnAtelier'),
              'sha256': release['archive']['sha256'], 'archive_sha256': release['archive']['sha256']}
    if destination.exists() or destination.is_symlink():
        _verify_stage(destination, release)
        _cancelled(cancel)
        _progress(progress, 100, '更新已下载并通过校验。')
        return result
    temporary = Path(tempfile.mkdtemp(prefix=f'.{version}-', dir=versions))
    try:
        _progress(progress, 0, '正在下载更新清单…')
        data = _transfer(release['manifest']['url'], JSON_LIMIT, expected=release['manifest'], cancel=cancel)
        external = _external_manifest(data, release)
        (temporary / 'release-manifest.json').write_bytes(data)
        archive = temporary / 'package.zip'
        _progress(progress, 5, '正在下载新版黎明工坊…')
        with archive.open('xb') as stream:
            _transfer(release['archive']['url'], ARCHIVE_LIMIT, destination=stream, expected=release['archive'],
                      cancel=cancel, progress=lambda count: _progress(
                          progress, 5 + 70 * count / release['archive']['bytes'], '正在下载新版黎明工坊…'))
        _extract(archive, temporary, cancel=cancel, progress=progress)
        _cancelled(cancel)
        _progress(progress, 92, '正在校验全部程序文件…')
        embedded = verify_installation(temporary / 'DawnAtelier', version)
        if embedded != {key: value for key, value in external.items() if key != 'archive'}:
            raise UpdateError('更新包内外的文件清单不一致。')
        archive.unlink()
        _cancelled(cancel)
        marker = {'version': version, 'archive_sha256': release['archive']['sha256'],
                  'manifest_sha256': release['manifest']['sha256']}
        marker_path = temporary / (MARKER_NAME + '.tmp')
        marker_path.write_text(json.dumps(marker, sort_keys=True) + '\n', encoding='utf-8')
        marker_path.replace(temporary / MARKER_NAME)
        _directory(versions)
        if destination.exists() or destination.is_symlink():
            _verify_stage(destination, release)
        else:
            temporary.rename(destination)
        _progress(progress, 100, '更新已下载并通过校验。')
        return result
    except (zipfile.BadZipFile, EOFError) as error:
        raise UpdateError('更新压缩包损坏，请重新下载。') from error
    finally:
        if temporary.exists():
            _remove_temporary(temporary, versions)


# Descriptive aliases for callers that only need the package operations.
download_release = stage_release
verify_package = verify_installation
