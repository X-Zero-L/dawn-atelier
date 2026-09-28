"""Build the Windows x64 desktop ZIP from an isolated, pinned Python environment.

Usage: python scripts/build-windows.py
Outputs: dist/windows/ (ZIP, SHA256SUMS, file manifest, and dependency inventory).
No game installation, game data, or user saves are needed or bundled.
"""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import venv
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / ".build/windows"
ENVIRONMENT = BUILD_ROOT / "venv"
OUTPUT_ROOT = ROOT / "dist/windows"
RUNTIME_PACKAGES = ("pywebview", "pythonnet", "cryptography", "Pillow")
PRIVATE_NAMES = {"config.local.json", "gameassembly.dll", "global-metadata.dat", "thepiper.exe"}
PRIVATE_EXTENSIONS = {".bundle", ".bytes", ".ress", ".save", ".bak"}
WEB_FILES = {
    "index.html", "app.js", "presets-ui.js", "style.css", "presets.css", "progression-ui.js", "progression.css", "save-refresh.js",
    "brand/emblem.svg", "brand/botanical.svg",
}
DESKTOP_FILES = {"index.html", "launcher.css", "launcher.js"}


def run(arguments, **kwargs):
    print("+ " + subprocess.list2cmdline([str(argument) for argument in arguments]), flush=True)
    return subprocess.run([str(argument) for argument in arguments], cwd=ROOT, check=True, **kwargs)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def current_version():
    value = json.loads((ROOT / "version.json").read_text(encoding="utf-8-sig"))["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", value) or any(int(part) > 65535 for part in value.split(".")):
        raise ValueError("version.json must contain a three-part numeric version")
    return value


def ensure_owned_paths():
    # Reject junctions/symlinks before any operation that can replace build output.
    for path in (ROOT / ".build", BUILD_ROOT, ENVIRONMENT, BUILD_ROOT / "dist",
                 BUILD_ROOT / "dist/DawnAtelier", BUILD_ROOT / "pyinstaller",
                 ROOT / "dist", OUTPUT_ROOT):
        if path.exists() and path.resolve() != path.absolute():
            raise ValueError(f"Build output must not be redirected through a link: {path}")
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def source_files():
    files = list(ROOT.glob("*.py"))
    files.extend((ROOT / "research").rglob("*.py"))
    files.extend((ROOT / "schemas").rglob("*.json"))
    for directory in ("build",):
        files.extend(path for path in (ROOT / directory).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    files.extend(ROOT / "web" / relative for relative in sorted(WEB_FILES))
    files.extend(ROOT / "desktop" / relative for relative in sorted(DESKTOP_FILES))
    files.extend(ROOT / name for name in (
        "version.json", "NOTICE.md", "requirements.txt", "requirements-desktop.txt",
        "requirements-build.txt", "scripts/build-windows.py", ".github/workflows/windows-release.yml",
    ))
    return sorted(set(files), key=lambda path: path.relative_to(ROOT).as_posix())


def source_snapshot():
    files = {path.relative_to(ROOT).as_posix(): digest(path) for path in source_files()}
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    commit, dirty = None, None
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT, text=True))
    except (OSError, subprocess.CalledProcessError):
        pass  # A downloaded source ZIP has no Git metadata.
    return {"commit": commit, "workingTreeDirty": dirty, "fingerprint": fingerprint, "files": files}


def build_environment(args):
    interpreter = ENVIRONMENT / "Scripts/python.exe"
    if not interpreter.is_file():
        if args.skip_install:
            raise RuntimeError("No build environment exists. Run once without --skip-install.")
        print("Creating the isolated Windows build environment…", flush=True)
        venv.EnvBuilder(with_pip=True).create(ENVIRONMENT)
    if not args.skip_install:
        run([interpreter, "-m", "pip", "install", "--disable-pip-version-check", "-r", ROOT / "requirements-build.txt"])
    arguments = [interpreter, Path(__file__).resolve(), "--inside-build-env"]
    if args.expected_version:
        arguments.extend(["--expected-version", args.expected_version])
    run(arguments)


def verify_pins():
    from packaging.requirements import Requirement

    for name in ("requirements.txt", "requirements-desktop.txt", "requirements-build.txt"):
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-r ")):
                continue
            requirement = Requirement(line)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            installed = metadata.version(requirement.name)
            if not requirement.specifier.contains(installed):
                raise RuntimeError(f"{requirement.name} {installed} does not satisfy {requirement.specifier}")


def version_resource(version):
    numbers = tuple(int(part) for part in version.split(".")) + (0,)
    path = BUILD_ROOT / "version-info.txt"
    values = {
        "CompanyName": "Dawn Atelier contributors",
        "FileDescription": "黎明工坊 · 黎明门前的吹笛人存档工具",
        "FileVersion": version,
        "InternalName": "DawnAtelier",
        "OriginalFilename": "DawnAtelier.exe",
        "ProductName": "黎明工坊 · Dawn Atelier",
        "ProductVersion": version,
    }
    strings = ",\n".join(f"        StringStruct({key!r}, {value!r})" for key, value in values.items())
    path.write_text(
        "# UTF-8\nVSVersionInfo(\n"
        f"  ffi=FixedFileInfo(filevers={numbers!r}, prodvers={numbers!r}, mask=0x3f, "
        "flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
        "  kids=[StringFileInfo([StringTable('080404B0', [\n"
        + strings + "\n      ])]), VarFileInfo([VarStruct('Translation', [2052, 1200])])]\n)\n",
        encoding="utf-8",
    )
    return path


def runtime_distributions():
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    result = {}
    pending = list(RUNTIME_PACKAGES)
    while pending:
        name = canonicalize_name(pending.pop())
        if name in result:
            continue
        distribution = metadata.distribution(name)
        result[name] = distribution
        for value in distribution.requires or []:
            requirement = Requirement(value)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return dict(sorted(result.items()))


def copy_notices(destination):
    notices = destination / "licenses"
    notices.mkdir(exist_ok=True)
    packages = []
    # The PyInstaller bootloader is shipped even though the build tool itself is not.
    distributions = runtime_distributions()
    distributions["pyinstaller"] = metadata.distribution("pyinstaller")
    for name, distribution in distributions.items():
        package_dir = notices / name
        package_dir.mkdir(exist_ok=True)
        license_paths = []
        for relative in distribution.files or []:
            if not any(word in Path(relative).name.lower() for word in ("license", "copying", "notice")):
                continue
            source = Path(distribution.locate_file(relative))
            if not source.is_file():
                continue
            filename = str(relative).replace("/", "__").replace("\\", "__").replace("..", "_")
            target = package_dir / filename
            shutil.copyfile(source, target)
            license_paths.append(target.relative_to(destination).as_posix())
        package_metadata = distribution.metadata
        if not license_paths and package_metadata.get("License"):
            target = package_dir / "LICENSE-from-package-metadata.txt"
            target.write_text(package_metadata["License"] + "\n", encoding="utf-8")
            license_paths.append(target.relative_to(destination).as_posix())
        packages.append({
            "name": package_metadata["Name"], "version": distribution.version,
            "role": "bootloader" if name == "pyinstaller" else "runtime",
            "licenseExpression": package_metadata.get("License-Expression"),
            "licenseFiles": license_paths,
            "projectUrls": package_metadata.get_all("Project-URL", []),
        })
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("The Python distribution LICENSE.txt was not found")
    shutil.copyfile(python_license, notices / "Python-LICENSE.txt")
    packages.append({"name": "CPython", "version": sys.version.split()[0], "role": "runtime",
                     "licenseFiles": ["licenses/Python-LICENSE.txt"]})
    sdk_dir = notices / "Microsoft.Web.WebView2"
    sdk_dir.mkdir(exist_ok=True)
    for filename in ("LICENSE.txt", "NOTICE.txt", "source.json"):
        shutil.copyfile(ROOT / "build/licenses/webview2" / filename, sdk_dir / filename)
    sdk = json.loads((sdk_dir / "source.json").read_text(encoding="utf-8"))
    packages.append({"name": "Microsoft.Web.WebView2", "version": sdk["version"], "role": "runtime-sdk",
                     "source": sdk["url"], "licenseFiles": ["licenses/Microsoft.Web.WebView2/LICENSE.txt", "licenses/Microsoft.Web.WebView2/NOTICE.txt"]})
    shutil.copyfile(ROOT / "NOTICE.md", destination / "NOTICE.md")
    return packages


def inspect_payload(directory):
    required = [
        "DawnAtelier.exe", "_internal/version.json", "_internal/web/index.html", "_internal/desktop/index.html",
        "_internal/schemas/thepiper-2026-09-25/save_schema.json",
        "_internal/schemas/thepiper-2026-09-28/save_schema.json",
        "_internal/schemas/compatibility/2026-09-28-1042.json",
        "_internal/build/assets/dawn-atelier.ico",
        "_internal/webview/lib/Microsoft.Web.WebView2.Core.dll",
        "_internal/webview/lib/Microsoft.Web.WebView2.WinForms.dll",
        "_internal/webview/lib/runtimes/win-x64/native/WebView2Loader.dll",
    ]
    for relative in required:
        if not (directory / relative).is_file():
            raise RuntimeError(f"Required packaged file is missing: {relative}")
    executable = (directory / "DawnAtelier.exe").read_bytes()
    pe = struct.unpack_from("<I", executable, 0x3C)[0]
    machine = struct.unpack_from("<H", executable, pe + 4)[0]
    subsystem = struct.unpack_from("<H", executable, pe + 24 + 68)[0]
    if executable[:2] != b"MZ" or executable[pe:pe + 4] != b"PE\0\0" or machine != 0x8664 or subsystem != 2:
        raise RuntimeError("The desktop executable must be a Windows x64 GUI program")
    files = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        lowered = relative.lower()
        if path.is_symlink() or path.name.lower() in PRIVATE_NAMES or path.suffix.lower() in PRIVATE_EXTENSIONS:
            raise RuntimeError(f"Private or unexpected payload file: {relative}")
        if any(lowered.startswith(prefix) for prefix in (
            "_internal/data/", "_internal/web/assets/", "_internal/web/logs/", "_internal/web/preview/",
            "_internal/backups/", "_internal/modified-saves/", "_internal/.git/",
        )):
            raise RuntimeError(f"Local data must never be packaged: {relative}")
        if lowered.startswith("_internal/web/") and relative[len("_internal/web/"):] not in WEB_FILES:
            raise RuntimeError(f"Web resource is outside the release allowlist: {relative}")
        if lowered.startswith("_internal/desktop/") and relative[len("_internal/desktop/"):] not in DESKTOP_FILES:
            raise RuntimeError(f"Desktop resource is outside the release allowlist: {relative}")
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": digest(path)})
    return files


def build(args):
    verify_pins()
    version = current_version()
    if args.expected_version and args.expected_version.removeprefix("v") != version:
        raise ValueError(f"Requested release {args.expected_version} does not match version.json ({version})")
    before = source_snapshot()
    environment = os.environ.copy()
    environment["DAWN_VERSION_FILE"] = str(version_resource(version))
    environment["PYTHONUTF8"] = "1"
    log_path = BUILD_ROOT / "pyinstaller.log"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--distpath", str(BUILD_ROOT / "dist"), "--workpath", str(BUILD_ROOT / "pyinstaller"),
               str(ROOT / "build/windows.spec")]
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
        if process.wait():
            raise RuntimeError(f"PyInstaller failed; see {log_path}")
    destination = BUILD_ROOT / "dist/DawnAtelier"
    packages = copy_notices(destination)
    quickstart = (ROOT / "build/windows-quickstart.txt").read_text(encoding="utf-8")
    (destination / "开始使用.txt").write_text(quickstart.replace("{{VERSION}}", version), encoding="utf-8-sig")
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bom = {"format": "dawn-atelier-dependencies-v1", "version": version, "platform": "windows-x64",
           "createdAt": timestamp, "packages": packages}
    write_json(destination / "dependencies.json", bom)
    after = source_snapshot()
    if after["fingerprint"] != before["fingerprint"]:
        raise RuntimeError("Source files changed during the build. Run the command again before publishing.")
    files = inspect_payload(destination)
    manifest = {"format": "dawn-atelier-windows-package-v1", "version": version, "createdAt": timestamp,
                "platform": "windows-x64", "architecture": "AMD64", "entryPoint": "DawnAtelier.exe",
                "signed": False, "source": before, "files": files}
    write_json(destination / "package-manifest.json", manifest)
    base = f"DawnAtelier-{version}-windows-x64"
    archive = OUTPUT_ROOT / f"{base}.zip"
    temporary = OUTPUT_ROOT / f".{base}.zip.tmp"
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
            for path in sorted(destination.rglob("*")):
                if path.is_file():
                    zipped.write(path, "DawnAtelier/" + path.relative_to(destination).as_posix())
        with zipfile.ZipFile(temporary) as zipped:
            corrupt = zipped.testzip()
            if corrupt:
                raise RuntimeError(f"Archive integrity check failed: {corrupt}")
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)
    checksum = digest(archive)
    (OUTPUT_ROOT / f"{base}.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    (OUTPUT_ROOT / "SHA256SUMS-windows.txt").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    manifest["archive"] = {"name": archive.name, "bytes": archive.stat().st_size, "sha256": checksum}
    write_json(OUTPUT_ROOT / f"{base}.manifest.json", manifest)
    write_json(OUTPUT_ROOT / f"{base}.dependencies.json", bom)
    print(f"\nReady: {archive}\nSHA256: {checksum}\nPayload: {len(files)} files", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-install", action="store_true", help="Reuse the existing isolated build dependencies")
    parser.add_argument("--expected-version", help="Fail unless version.json matches this version/tag")
    parser.add_argument("--inside-build-env", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise SystemExit("Build the Windows x64 package with 64-bit Python on Windows.")
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required to build the package.")
    ensure_owned_paths()
    if args.inside_build_env:
        if Path(sys.prefix).resolve() != ENVIRONMENT.resolve():
            raise SystemExit("The internal build stage requires the isolated build environment.")
        build(args)
    else:
        build_environment(args)


if __name__ == "__main__":
    main()
