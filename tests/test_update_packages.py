"""Official update downloads use synthetic packages and mocked HTTPS only."""

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request
import zipfile

import update_packages as updates


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def checksum(value):
    return hashlib.sha256(value).hexdigest()


def executable():
    value = bytearray(512)
    value[:2] = b'MZ'
    struct.pack_into('<I', value, 0x3C, 64)
    value[64:68] = b'PE\0\0'
    struct.pack_into('<H', value, 68, 0x8664)
    struct.pack_into('<H', value, 88, 0x20B)
    struct.pack_into('<H', value, 156, 2)
    return bytes(value)


class Response(io.BytesIO):
    def __init__(self, body, url, headers=None):
        super().__init__(body)
        self.url = url
        self.status = 200
        self.headers = {'Content-Length': str(len(body))} if headers is None else headers

    def geturl(self):
        return self.url


class UpdatePackageChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root / 'updates'
        self.version = '2.6.0'
        self.make_package()
        self.requests = []
        self.responses = {}
        self.network = patch.object(updates, 'build_opener', return_value=Mock(open=self.respond)).start()
        self.addCleanup(patch.stopall)
        self.use_package()

    def make_package(self, files=None, extra_entries=None, modify_manifest=None, modify_external=None):
        self.payload = files if files is not None else {
            'DawnAtelier.exe': executable(),
            '_internal/version.json': encoded({'version': self.version, 'name': 'Dawn Atelier'}),
            '_internal/desktop/index.html': b'<p>Fixture</p>',
            'licenses/LICENSE.txt': b'Fixture license\n',
        }
        manifest = {'format': updates.PACKAGE_FORMAT, 'version': self.version,
                    'platform': 'windows-x64', 'architecture': 'AMD64',
                    'entryPoint': 'DawnAtelier.exe', 'signed': False,
                    'source': {'fingerprint': 'fixture'},
                    'files': [{'path': name, 'bytes': len(data), 'sha256': checksum(data)}
                              for name, data in sorted(self.payload.items())]}
        if modify_manifest:
            modify_manifest(manifest)
        self.embedded = deepcopy(manifest)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as zipped:
            for name, data in self.payload.items():
                zipped.writestr('DawnAtelier/' + name, data)
            zipped.writestr('DawnAtelier/package-manifest.json', encoded(manifest))
            for name, data in extra_entries or []:
                zipped.writestr(name, data)
        self.archive = stream.getvalue()
        archive_name = f'DawnAtelier-{self.version}-windows-x64.zip'
        manifest['archive'] = {'name': archive_name, 'bytes': len(self.archive), 'sha256': checksum(self.archive)}
        if modify_external:
            modify_external(manifest)
        self.manifest = encoded(manifest)
        self.release = {'version': self.version, 'tag': 'v' + self.version}
        for kind, extension, data in (('archive', 'zip', self.archive), ('manifest', 'manifest.json', self.manifest)):
            name = f'DawnAtelier-{self.version}-windows-x64.{extension}'
            self.release[kind] = {'name': name, 'url': f'{updates.RELEASES_URL}/download/v{self.version}/{name}',
                                  'bytes': len(data), 'sha256': checksum(data)}
        self.api = {'tag_name': 'v' + self.version, 'draft': False, 'prerelease': False,
                    'body': '测试更新', 'assets': [
                        {'name': asset['name'], 'state': 'uploaded', 'size': asset['bytes'],
                         'digest': 'sha256:' + asset['sha256'], 'browser_download_url': asset['url']}
                        for asset in (self.release['archive'], self.release['manifest'])]}

    def use_package(self):
        self.responses[updates.LATEST_URL] = encoded(self.api)
        self.responses[self.release['archive']['url']] = self.archive
        self.responses[self.release['manifest']['url']] = self.manifest

    def replace_archive(self, contents):
        self.archive = contents
        self.release['archive'].update(bytes=len(contents), sha256=checksum(contents))
        manifest = json.loads(self.manifest)
        manifest['archive'].update(bytes=len(contents), sha256=checksum(contents))
        self.manifest = encoded(manifest)
        self.release['manifest'].update(bytes=len(self.manifest), sha256=checksum(self.manifest))
        self.use_package()

    def respond(self, request, timeout):
        self.assertEqual(timeout, updates.TIMEOUT)
        self.assertEqual(request.get_header('User-agent'), 'DawnAtelier-updater')
        self.assertEqual(request.get_header('Accept-encoding'), 'identity')
        self.requests.append(request.full_url)
        value = self.responses[request.full_url]
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, Response) else Response(value, request.full_url)

    def stage(self):
        return updates.stage_release(self.release, self.cache)

    def test_numeric_versions_and_invalid_tags(self):
        self.assertGreater(updates.parse_version('2.10.0'), updates.parse_version('2.9.12'))
        for version in ('v2.6.0', '2.6.0-beta', '2.6.0+abc', '02.6.0', '2.6', '2.6.0\n',
                        '2.6.0 ', '65536.0.0', '', None, True, '２.６.０'):
            with self.subTest(version=version), self.assertRaises(updates.UpdateError):
                updates.parse_version(version)

    def test_latest_release_uses_fixed_api_and_digests(self):
        result = updates.latest_release('2.5.0')
        self.assertEqual(result['version'], self.version)
        self.assertEqual(result['archive'], self.release['archive'])
        self.assertEqual(result['manifest'], self.release['manifest'])
        self.assertEqual(self.requests, [updates.LATEST_URL])
        self.assertIsNone(updates.latest_release('2.6.0'))
        self.assertIsNone(updates.latest_release('2.7.0'))

    def test_drafts_prereleases_and_missing_flags_are_ignored(self):
        for field, value in (('draft', True), ('prerelease', True), ('draft', None), ('prerelease', 'false')):
            with self.subTest(field=field, value=value):
                api = deepcopy(self.api)
                api[field] = value
                self.responses[updates.LATEST_URL] = encoded(api)
                self.assertIsNone(updates.latest_release('2.5.0'))

    def test_invalid_release_tag_is_rejected(self):
        for tag in ('2.6.0', 'v2.6.0-rc1', 'v02.6.0', 'v2.6.0/path', 260):
            with self.subTest(tag=tag):
                api = deepcopy(self.api)
                api['tag_name'] = tag
                self.responses[updates.LATEST_URL] = encoded(api)
                with self.assertRaises(updates.UpdateError):
                    updates.latest_release('2.5.0')

    def test_asset_identity_and_required_api_digest(self):
        for key, value in (('digest', None), ('digest', 'md5:' + 'a' * 32), ('digest', 'sha256:' + 'A' * 64),
                           ('browser_download_url', 'https://evil.example/update.zip'),
                           ('size', 0), ('size', True), ('size', updates.ARCHIVE_LIMIT + 1), ('state', 'new')):
            with self.subTest(key=key, value=value):
                api = deepcopy(self.api)
                api['assets'][0][key] = value
                self.responses[updates.LATEST_URL] = encoded(api)
                with self.assertRaises(updates.UpdateError):
                    updates.latest_release('2.5.0')

    def test_missing_or_duplicate_assets_are_rejected(self):
        for assets in ([], self.api['assets'][:1], self.api['assets'] + [self.api['assets'][0]]):
            api = deepcopy(self.api)
            api['assets'] = assets
            self.responses[updates.LATEST_URL] = encoded(api)
            with self.assertRaises(updates.UpdateError):
                updates.latest_release('2.5.0')

    def test_not_found_has_no_update_and_other_http_errors_fail(self):
        for code in (404, 403, 500):
            self.responses[updates.LATEST_URL] = HTTPError(updates.LATEST_URL, code, 'fixture', {}, None)
            if code == 404:
                self.assertIsNone(updates.latest_release('2.5.0'))
            else:
                with self.assertRaises(updates.UpdateError):
                    updates.latest_release('2.5.0')

    def test_only_allowed_https_redirects(self):
        initial = self.release['archive']['url']
        handler = updates._OfficialRedirects(initial)
        request = Request(initial)
        for url in ('https://release-assets.githubusercontent.com/a?token=fixture',
                    'https://objects.githubusercontent.com/a', initial):
            self.assertEqual(handler.redirect_request(request, None, 302, '', {}, url).full_url, url)
        for url in ('http://release-assets.githubusercontent.com/a', 'file:///tmp/a',
                    'https://evil.example/a', 'https://github.com/other/repo/releases/a',
                    'https://release-assets.githubusercontent.com.evil.example/a',
                    'https://user@release-assets.githubusercontent.com/a',
                    'https://release-assets.githubusercontent.com:444/a',
                    'https://release-assets.githubusercontent.com/a#fragment'):
            with self.subTest(url=url), self.assertRaises(updates.UpdateError):
                handler.redirect_request(request, None, 302, '', {}, url)
        with self.assertRaises(updates.UpdateError):
            updates._OfficialRedirects(updates.LATEST_URL).redirect_request(
                Request(updates.LATEST_URL), None, 302, '', {}, 'https://api.github.com/other')

    def test_response_final_url_is_checked(self):
        self.responses[updates.LATEST_URL] = Response(encoded(self.api), 'https://evil.example/a')
        with self.assertRaises(updates.UpdateError):
            updates.latest_release('2.5.0')

    def test_download_rejects_nonofficial_initial_url(self):
        with self.assertRaises(updates.UpdateError):
            updates._transfer('https://evil.example/a', updates.JSON_LIMIT)
        self.assertEqual(self.requests, [])

    def test_json_bounds_and_invalid_json(self):
        for body in (b'[]', b'not JSON', b'{"tag_name":"v2.6.0","tag_name":"v2.7.0"}', b'{"x":NaN}'):
            self.responses[updates.LATEST_URL] = body
            with self.assertRaises(updates.UpdateError):
                updates.latest_release('2.5.0')
        self.responses[updates.LATEST_URL] = b' ' * 257
        with patch.object(updates, 'JSON_LIMIT', 256), self.assertRaises(updates.UpdateError):
            updates.latest_release('2.5.0')

    def test_download_checks_length_content_encoding_and_hash(self):
        url = self.release['manifest']['url']
        for response in (Response(self.manifest, url, {'Content-Length': str(len(self.manifest) + 1)}),
                         Response(self.manifest, url, {'Content-Length': 'bad'}),
                         Response(self.manifest, url, {'Content-Encoding': 'gzip'}),
                         Response(self.manifest + b'x', url, {}),
                         Response(self.manifest[:-1], url, {}),
                         Response(b'x' * len(self.manifest), url, {})):
            self.responses[url] = response
            with self.assertRaises(updates.UpdateError):
                self.stage()
            self.assertFalse(list((self.cache / 'versions').iterdir()))

    def test_successful_stage_is_exact_verified_and_reusable(self):
        events = []
        result = updates.stage_release(self.release, self.cache, progress=lambda *args: events.append(args))
        directory = Path(result['directory'])
        self.assertEqual(result['version'], self.version)
        self.assertEqual(result['sha256'], checksum(self.archive))
        self.assertEqual(directory.name, 'DawnAtelier')
        self.assertEqual(directory.parent.parent, self.cache / 'versions')
        self.assertTrue(directory.is_absolute())
        self.assertEqual(updates.verify_installation(directory, self.version), self.embedded)
        self.assertEqual(events[0][0], 0)
        self.assertEqual(events[-1][0], 100)
        self.assertEqual([event[0] for event in events], sorted(event[0] for event in events))
        self.assertEqual({path.name for path in directory.parent.iterdir()},
                         {'DawnAtelier', 'release-manifest.json', updates.MARKER_NAME})
        self.requests.clear()
        self.assertEqual(self.stage(), result)
        self.assertEqual(self.requests, [])

    def test_cached_stage_tampering_is_never_overwritten(self):
        result = self.stage()
        directory = Path(result['directory'])
        executable_path = directory / 'DawnAtelier.exe'
        executable_path.write_bytes(b'bad data')
        self.requests.clear()
        with self.assertRaises(updates.UpdateError):
            self.stage()
        self.assertEqual(executable_path.read_bytes(), b'bad data')
        self.assertEqual(self.requests, [])

    def test_cached_release_metadata_is_revalidated(self):
        result = self.stage()
        release_manifest = Path(result['directory']).parent / 'release-manifest.json'
        release_manifest.write_bytes(self.manifest + b' ')
        with self.assertRaises(updates.UpdateError):
            self.stage()

    def test_existing_incomplete_directory_is_not_overwritten(self):
        target = self.cache / 'versions' / f"{self.version}-{checksum(self.archive)[:16]}"
        target.mkdir(parents=True)
        (target / 'sentinel.txt').write_text('keep', encoding='utf-8')
        with self.assertRaises(updates.UpdateError):
            self.stage()
        self.assertEqual((target / 'sentinel.txt').read_text(), 'keep')
        self.assertEqual(self.requests, [])

    def test_local_extra_missing_and_tampered_files_are_rejected(self):
        result = self.stage()
        directory = Path(result['directory'])
        extra = directory / 'extra.txt'
        extra.write_bytes(b'extra')
        with self.assertRaises(updates.UpdateError):
            updates.verify_installation(directory)
        extra.unlink()
        extra.mkdir()
        with self.assertRaises(updates.UpdateError):
            updates.verify_installation(directory)
        extra.rmdir()
        payload = directory / 'licenses/LICENSE.txt'
        payload.unlink()
        with self.assertRaises(updates.UpdateError):
            updates.verify_installation(directory)

    def test_original_installation_can_ignore_unrelated_user_files(self):
        result = self.stage()
        directory = Path(result['directory'])
        saves = directory / 'saves'
        saves.mkdir()
        (saves / 'save1').write_bytes(b'User data never belongs in rollback copies.')
        (directory / 'notes.txt').write_bytes(b'keep')
        self.assertEqual(updates.verify_installation(directory, self.version, allow_extra=True), self.embedded)
        with self.assertRaises(updates.UpdateError):
            updates.verify_installation(directory, self.version)
        (directory / 'licenses/LICENSE.txt').write_bytes(b'tampered')
        with self.assertRaises(updates.UpdateError):
            updates.verify_installation(directory, self.version, allow_extra=True)

    def test_wrong_external_manifest_or_archive_identity_fails(self):
        for change in (lambda value: value.update(source={'fingerprint': 'different'}),
                       lambda value: value['archive'].update(sha256='a' * 64),
                       lambda value: value.update(version='2.7.0')):
            self.make_package(modify_external=change)
            self.use_package()
            with self.assertRaises(updates.UpdateError):
                self.stage()

    def test_version_inside_executable_bundle_must_match(self):
        files = dict(self.payload)
        files['_internal/version.json'] = encoded({'version': '2.5.0'})
        self.make_package(files=files)
        self.use_package()
        with self.assertRaises(updates.UpdateError):
            self.stage()

    def test_executable_must_be_windows_x64_gui(self):
        for contents in (b'not PE', executable().replace(b'MZ', b'XX', 1), bytes(512)):
            files = dict(self.payload)
            files['DawnAtelier.exe'] = contents
            self.make_package(files=files)
            self.use_package()
            with self.assertRaises(updates.UpdateError):
                self.stage()
        for offset, value in ((68, 0x14C), (88, 0x10B), (156, 3)):
            contents = bytearray(executable())
            struct.pack_into('<H', contents, offset, value)
            files = dict(self.payload)
            files['DawnAtelier.exe'] = bytes(contents)
            self.make_package(files=files)
            self.use_package()
            with self.assertRaises(updates.UpdateError):
                self.stage()

    def test_unsafe_archive_paths_are_rejected(self):
        names = ('../escaped.txt', '/absolute.txt', 'Other/app.exe', 'DawnAtelier/../escaped.txt',
                 'DawnAtelier/./dot.txt', 'DawnAtelier//empty.txt', 'DawnAtelier/dir\\file.txt',
                 'DawnAtelier/C:/drive.txt', 'DawnAtelier/file:stream', 'DawnAtelier/CON.txt',
                 'DawnAtelier/com1', 'DawnAtelier/LPT¹.txt', 'DawnAtelier/trailing.',
                 'DawnAtelier/trailing /file', 'DawnAtelier/what?.txt', 'DawnAtelier/line\n.txt',
                 'DawnAtelier/DAWNATELIER.EXE', 'DawnAtelier/_INTERNAL/extra.txt')
        for name in names:
            with self.subTest(name=name):
                self.make_package(extra_entries=[(name, b'unsafe')])
                self.use_package()
                with self.assertRaises(updates.UpdateError):
                    self.stage()
                self.assertFalse(list((self.cache / 'versions').iterdir()))
        self.assertFalse((self.root / 'escaped.txt').exists())

    def test_archive_links_and_special_files_are_rejected(self):
        for mode in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK):
            item = zipfile.ZipInfo('DawnAtelier/link')
            item.create_system = 3
            item.external_attr = (mode | 0o777) << 16
            self.make_package(extra_entries=[(item, b'/elsewhere')])
            self.use_package()
            with self.assertRaises(updates.UpdateError):
                self.stage()
        item = zipfile.ZipInfo('DawnAtelier/reparse')
        item.external_attr = (stat.S_IFREG | 0o600) << 16 | 0x400
        self.make_package(extra_entries=[(item, b'fixture')])
        self.use_package()
        with self.assertRaises(updates.UpdateError):
            self.stage()

    def test_archive_file_directory_collision_is_rejected(self):
        self.make_package(extra_entries=[('DawnAtelier/_internal', b'not a directory')])
        self.use_package()
        with self.assertRaises(updates.UpdateError):
            self.stage()

    def test_encrypted_and_oversized_zip_headers_are_rejected(self):
        original = self.archive
        encrypted = bytearray(original)
        for signature, offset in ((b'PK\x03\x04', 6), (b'PK\x01\x02', 8)):
            index = encrypted.index(signature)
            flags = struct.unpack_from('<H', encrypted, index + offset)[0]
            struct.pack_into('<H', encrypted, index + offset, flags | 1)
        self.replace_archive(bytes(encrypted))
        with self.assertRaises(updates.UpdateError):
            self.stage()
        oversized = bytearray(original)
        central = oversized.index(b'PK\x01\x02')
        struct.pack_into('<I', oversized, central + 24, updates.PAYLOAD_LIMIT + 1)
        self.replace_archive(bytes(oversized))
        with self.assertRaises(updates.UpdateError):
            self.stage()

    def test_zip_null_byte_paths_are_rejected(self):
        marker = b'DawnAtelier/licenses/LICENSE.txt'
        self.replace_archive(self.archive.replace(marker, marker[:-1] + b'\0'))
        with self.assertRaises(updates.UpdateError):
            self.stage()

    def test_unlisted_archive_payload_is_rejected(self):
        self.make_package(extra_entries=[('DawnAtelier/unlisted.dll', b'unlisted')])
        self.use_package()
        with self.assertRaises(updates.UpdateError):
            self.stage()

    def test_payload_entry_and_size_limits(self):
        with patch.object(updates, 'ENTRY_LIMIT', 3), self.assertRaises(updates.UpdateError):
            self.stage()
        with patch.object(updates, 'PAYLOAD_LIMIT', 256), self.assertRaises(updates.UpdateError):
            self.stage()

    def test_manifest_paths_and_file_records_are_validated(self):
        for mutation in (lambda value: value['files'].append(dict(value['files'][0])),
                         lambda value: value['files'][0].update(path='../escape'),
                         lambda value: value['files'][0].update(path='package-manifest.json'),
                         lambda value: value['files'][0].update(bytes=True),
                         lambda value: value['files'][0].update(sha256='bad'),
                         lambda value: value.update(architecture='x86'),
                         lambda value: value.update(entryPoint='different.exe')):
            self.make_package(modify_manifest=mutation)
            self.use_package()
            with self.assertRaises(updates.UpdateError):
                self.stage()

    def test_cancelled_download_never_produces_ready_package(self):
        cancel = Event()
        cancel.set()
        with self.assertRaises(updates.UpdateCancelled):
            updates.stage_release(self.release, self.cache, cancel=cancel)
        self.assertFalse(self.cache.exists())
        cancel.clear()

        def stop(percent, message):
            if percent >= 5:
                cancel.set()

        with self.assertRaises(updates.UpdateCancelled):
            updates.stage_release(self.release, self.cache, cancel=cancel, progress=stop)
        self.assertFalse(list((self.cache / 'versions').iterdir()))

    def test_cancelled_callback_keyword_is_supported(self):
        with self.assertRaises(updates.UpdateCancelled):
            updates.stage_release(self.release, self.cache, cancelled=lambda: True)
        self.assertFalse(self.cache.exists())

    def test_file_system_links_are_rejected_when_available(self):
        external = self.root / 'elsewhere'
        external.mkdir()
        link = self.root / 'linked'
        try:
            link.symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest('Symbolic link creation is unavailable in this Windows session.')
        with self.assertRaises(updates.UpdateError):
            updates.stage_release(self.release, link)
        self.assertEqual(list(external.iterdir()), [])

    def test_windows_alias_spelling_is_accepted_only_for_same_directory(self):
        with patch.object(Path, 'resolve', return_value=self.root / 'long-name'), patch.object(Path, 'samefile', return_value=True):
            self.assertEqual(updates._directory(self.root), self.root)
        with patch.object(Path, 'resolve', return_value=self.root / 'other-directory'), patch.object(Path, 'samefile', return_value=False):
            with self.assertRaises(updates.UpdateError):
                updates._directory(self.root)


if __name__ == '__main__':
    unittest.main()
