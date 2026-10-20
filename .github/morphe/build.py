#!/usr/bin/env python3
"""Patch YouTube and YouTube Music with each new Morphe patches release and publish them.

For every stable morphe-patches release newer than the last published build (and not
older than `start_patches_version`), each app is patched from the newest uploaded stock
APK that the patches officially support. The stock version never goes below the one
shipped in the previous release, so every build installs over the last one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

API = "https://api.github.com"
CONFIG = Path(__file__).with_name("config.json")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
# APKMirror naming: <package>_<version>-<versionCode>_<variant>.<ext>
STOCK_NAME = re.compile(
    r"^(?P<package>[A-Za-z][\w.]*?)_(?P<version>\d+(?:\.\d+)+)-.*\.(?P<ext>apkm|apks|xapk|apk)$"
)
# Bundles carry every split, so prefer them over a single-arch .apk of the same version.
EXT_RANK = {"apkm": 0, "apks": 1, "xapk": 2, "apk": 3}
APK_SIG_BLOCK_MAGIC = b"APK Sig Block 42"
SIGNATURE_SCHEMES = (0xF05368C0, 0x7109871A)  # v3, v2
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


class BuildError(Exception):
    pass


def vkey(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


@dataclass
class Stock:
    package: str
    version: str
    ext: str
    name: str
    url: str | None = None
    path: Path | None = None


@dataclass
class Keystore:
    path: Path
    password: str
    alias: str
    entry_password: str


# region GitHub


class _StripAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    # Asset downloads redirect to a storage host that rejects the GitHub token.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            new.remove_header("Authorization")
        return new


_opener = urllib.request.build_opener(_StripAuthOnRedirect)


def _open(url: str, accept: str = "application/vnd.github+json"):
    headers = {"Accept": accept, "User-Agent": "youtube-az-builder"}
    if TOKEN and urllib.parse.urlsplit(url).netloc == "api.github.com":
        headers["Authorization"] = f"Bearer {TOKEN}"
    return _opener.open(urllib.request.Request(url, headers=headers))


def api(path: str):
    with _open(f"{API}/{path}") as response:
        return json.load(response)


def api_all(path: str) -> list:
    items, page = [], 1
    while True:
        batch = api(f"{path}?per_page=100&page={page}")
        items += batch
        if len(batch) < 100:
            return items
        page += 1


def download(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    with _open(url, "application/octet-stream") as response, open(part, "wb") as out:
        shutil.copyfileobj(response, out, 1 << 20)
    part.replace(dest)
    return dest


# endregion

# region Planning


def published_builds(releases: list, apps: list) -> dict[str, dict[str, str]]:
    """Patches version -> {asset prefix: stock version}, read from published asset names."""
    builds: dict[str, dict[str, str]] = {}
    for release in releases:
        if release["draft"]:
            continue
        for asset in release["assets"]:
            for app in apps:
                match = re.match(
                    rf"{re.escape(app['asset_prefix'])}-v?(\d+(?:\.\d+)+)-patches-(\d+\.\d+\.\d+)",
                    asset["name"],
                )
                if match:
                    builds.setdefault(match[2], {})[app["asset_prefix"]] = match[1]
    return builds


def previous_build(builds: dict[str, dict[str, str]], version: str) -> dict[str, str]:
    older = [v for v in builds if vkey(v) < vkey(version)]
    return builds[max(older, key=vkey)] if older else {}


def parse_stock(name: str, **location) -> Stock | None:
    match = STOCK_NAME.match(name)
    if not match:
        return None
    return Stock(match["package"], match["version"], match["ext"], name, **location)


def stock_from_release(releases: list, tag: str) -> list[Stock]:
    release = next((r for r in releases if r["tag_name"] == tag), None)
    if release is None:
        raise BuildError(f"No release tagged '{tag}' found. Create a draft release with that tag and attach the stock APKs.")
    return [s for a in release["assets"] if (s := parse_stock(a["name"], url=a["url"]))]


def stock_from_dir(directory: Path) -> list[Stock]:
    return [s for f in sorted(directory.iterdir()) if f.is_file() and (s := parse_stock(f.name, path=f))]


def supported_versions(jar: Path, mpp: Path, packages: list[str]) -> dict[str, set[str] | None]:
    """Package -> stable versions the patches support (None means any version)."""
    cmd = [*java(jar), "list-versions", f"--patches={mpp}"]
    for package in packages:
        cmd += ["-f", package]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    output = ANSI.sub("", proc.stdout + proc.stderr)
    if proc.returncode:
        raise BuildError(f"list-versions failed for {mpp.name}:\n{output}")

    versions: dict[str, set[str] | None] = {}
    package = None
    for line in output.splitlines():
        if match := re.search(r"Package name: (\S+)", line):
            package = match[1]
            versions[package] = set()
        elif package and line.strip() == "Any":
            versions[package] = None
        elif package and versions[package] is not None and (match := re.match(r"\s+(\d+(?:\.\d+)+)", line)):
            versions[package].add(match[1])
    return versions


def pick_stock(app: dict, stock: list[Stock], supported: dict, floor: str | None) -> Stock:
    if app["package"] not in supported:
        raise BuildError(f"The patches have no {app['name']} patches.")
    allowed = supported[app["package"]]
    candidates = [
        s for s in stock
        if s.package == app["package"]
        and (allowed is None or s.version in allowed)
        and (floor is None or vkey(s.version) >= vkey(floor))
    ]
    if not candidates:
        wanted = sorted((v for v in allowed or () if floor is None or vkey(v) >= vkey(floor)), key=vkey, reverse=True)
        raise BuildError(
            f"No uploaded {app['name']} APK is supported. "
            f"Upload one of: {', '.join(wanted) or 'none available'}"
            + (f" (previous release used {floor})" if floor else "")
        )
    return max(candidates, key=lambda s: (vkey(s.version), -EXT_RANK[s.ext]))


# endregion

# region Patching


def java(jar: Path) -> list[str]:
    return ["java", "-Xmx6g", "-jar", str(jar)]


def fetch_morphe(cfg: dict, tools: Path) -> Path:
    wanted = cfg["morphe_desktop_version"]
    ref = "latest" if wanted == "latest" else f"tags/v{wanted.lstrip('v')}"
    release = api(f"repos/{cfg['morphe_desktop_repo']}/releases/{ref}")
    asset = next(a for a in release["assets"] if re.fullmatch(r"morphe-desktop-.*-all\.jar", a["name"]))
    print(f"Using {asset['name']}")
    return download(asset["browser_download_url"], tools / asset["name"])


def ensure_local(stock: Stock, directory: Path) -> Path:
    if stock.path:
        return stock.path
    print(f"Downloading {stock.name}")
    stock.path = download(stock.url, directory / stock.name)
    return stock.path


def signing_cert(apk: Path) -> str:
    """SHA-256 of the first signer's certificate in the APK Signature Scheme v3/v2 block.

    Morphe no longer adds a v1 (JAR) signature, so keytool -printcert cannot read it.
    """
    with open(apk, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - 65557))
        tail = f.read()
        eocd = tail.rfind(b"PK\x05\x06")
        if eocd < 0:
            raise BuildError(f"{apk.name} is not a valid APK")
        cd_offset = struct.unpack_from("<I", tail, eocd + 16)[0]
        f.seek(cd_offset - 24)
        block_size, magic = struct.unpack("<Q16s", f.read(24))
        if magic != APK_SIG_BLOCK_MAGIC:
            raise BuildError(f"{apk.name} has no APK Signing Block")
        f.seek(cd_offset - block_size)
        pairs = f.read(block_size - 24)

    schemes, pos = {}, 0
    while pos + 12 <= len(pairs):
        length, scheme = struct.unpack_from("<QI", pairs, pos)
        schemes[scheme] = pairs[pos + 12:pos + 8 + length]
        pos += 8 + length
    block = next((schemes[s] for s in SIGNATURE_SCHEMES if s in schemes), None)
    if block is None:
        raise BuildError(f"{apk.name} has no v2/v3 signature")

    def field(buf: bytes, at: int = 0) -> tuple[bytes, int]:
        size = struct.unpack_from("<I", buf, at)[0]
        return buf[at + 4:at + 4 + size], at + 4 + size

    signer = field(field(block)[0])[0]
    signed_data = field(signer)[0]
    _, after_digests = field(signed_data)
    certificate = field(field(signed_data, after_digests)[0])[0]
    return hashlib.sha256(certificate).hexdigest().upper()


def patch_app(jar: Path, mpp: Path, app: dict, stock: Stock, out_apk: Path, work: Path, keystore: Keystore, cert: str):
    result_file = out_apk.with_suffix(".json")
    cmd = [*java(jar), "patch", "-p", str(mpp), "-e", "Custom branding", f"-OcustomName={app['app_name']}"]
    for name in app["disabled_patches"]:
        cmd += ["-d", name]
    cmd += [
        "--keystore", str(keystore.path),
        "--keystore-password", keystore.password,
        "--keystore-entry-alias", keystore.alias,
        "--keystore-entry-password", keystore.entry_password,
        "-t", str(work / "tmp"),
        "-r", str(result_file),
        "-o", str(out_apk),
        str(stock.path),
    ]
    print(f"::group::Patching {stock.name}")
    code = subprocess.run(cmd).returncode
    print("::endgroup::")

    if code or not result_file.exists():
        raise BuildError(f"{app['name']}: Morphe exited with code {code}")
    result = json.loads(result_file.read_text(encoding="utf-8"))
    problems = [f"step {s['step']} failed: {s.get('message')}" for s in result["patchingSteps"] if not s["success"]]
    problems += [f"patch '{p['patch'].get('name')}' failed" for p in result["failedPatches"]]
    if result.get("packageVersion") != stock.version:
        problems.append(f"patched version {result.get('packageVersion')} but expected {stock.version}")
    branding = {
        o["key"]: o["value"]
        for p in result["appliedPatches"] if p.get("name") == "Custom branding"
        for o in p.get("options", [])
    }
    if branding.get("customName") != app["app_name"]:
        problems.append(f"Custom branding was not applied as '{app['app_name']}'")
    if problems:
        raise BuildError(f"{app['name']}: " + "; ".join(problems))

    actual = signing_cert(out_apk)
    if actual != cert.replace(":", "").upper():
        raise BuildError(f"{app['name']}: signed with certificate {actual}, expected {cert}. Check the KEYSTORE secrets.")
    print(f"{out_apk.name}: {len(result['appliedPatches'])} patches applied, signature verified")


def release_notes(version: str, picks: dict[str, Stock], previous: dict[str, str], apps: list) -> str:
    lines = [f"- Update Patches to v{version}"]
    for app in apps:
        stock = picks[app["asset_prefix"]]
        if previous.get(app["asset_prefix"]) != stock.version:
            lines.append(f"- Update {app['name']} to v{stock.version}")
    return "\n".join(lines)


def publish(repo: str, version: str, assets: list[Path], notes: str, latest: bool):
    cmd = [
        "gh", "release", "create", f"v{version}", *map(str, assets),
        "--repo", repo,
        "--title", f"Update v{version}",
        "--notes", notes,
        f"--latest={'true' if latest else 'false'}",
    ]
    if sha := os.environ.get("GITHUB_SHA"):
        cmd += ["--target", sha]
    if subprocess.run(cmd).returncode:
        raise BuildError(f"Creating release v{version} failed")


# endregion


def write_summary(apps: list, rows: list[tuple[str, dict[str, Stock], str]]):
    lines = [
        "| Patches | " + " | ".join(a["name"] for a in apps) + " | Result |",
        "|---" * (len(apps) + 2) + "|",
    ]
    for version, picks, status in rows:
        stock = [picks[a["asset_prefix"]].version if a["asset_prefix"] in picks else "—" for a in apps]
        lines.append(f"| v{version} | " + " | ".join(stock) + f" | {status} |")
    table = "\n".join(lines)
    print(table)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as summary:
            summary.write(f"## YouTube AZ builds\n\n{table}\n")


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"), help="owner/name to publish to")
    parser.add_argument("--patches-version", default=os.environ.get("PATCHES_VERSION") or None,
                        help="build only this patches version, e.g. 1.41.0")
    parser.add_argument("--stock-dir", type=Path, help="use stock APKs from this folder instead of the stock release")
    parser.add_argument("--work-dir", type=Path, default=Path(os.environ.get("RUNNER_TEMP", "build")) / "morphe")
    parser.add_argument("--dry-run", action="store_true", default=os.environ.get("DRY_RUN") == "true",
                        help="build the APKs into <work-dir>/out but do not publish releases")
    parser.add_argument("--plan-only", action="store_true", help="only print which stock APKs would be used")
    args = parser.parse_args()
    if not args.repo:
        parser.error("--repo is required outside GitHub Actions")

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    apps = cfg["apps"]
    work = args.work_dir.resolve()

    releases = api_all(f"repos/{args.repo}/releases")
    builds = published_builds(releases, apps)
    tags = {r["tag_name"] for r in releases if not r["draft"]}

    patch_releases = {
        match[1]: release
        for release in api_all(f"repos/{cfg['patches_repo']}/releases")
        if not release["draft"] and not release["prerelease"]
        and (match := re.fullmatch(r"v(\d+\.\d+\.\d+)", release["tag_name"]))
    }
    if args.patches_version:
        version = args.patches_version.lstrip("v")
        if version not in patch_releases:
            raise SystemExit(f"v{version} is not a stable {cfg['patches_repo']} release")
        targets = [version]
    else:
        newest = max(builds, key=vkey, default=None)
        targets = [
            v for v in patch_releases
            if vkey(v) >= vkey(cfg["start_patches_version"]) and (newest is None or vkey(v) > vkey(newest))
        ]
    targets = sorted((v for v in targets if v not in builds and f"v{v}" not in tags), key=vkey)
    if not targets:
        if args.patches_version:
            print(f"v{args.patches_version.lstrip('v')} already has a published release.")
        else:
            print("Up to date: every patches release already has a published build.")
        return 0
    print("Patches releases to build: " + ", ".join(f"v{v}" for v in targets))

    stock = stock_from_dir(args.stock_dir) if args.stock_dir else stock_from_release(releases, cfg["stock_release_tag"])
    print("Stock APKs: " + ", ".join(f"{s.package} {s.version} ({s.ext})" for s in stock))
    jar = fetch_morphe(cfg, work / "tools")

    # Plan every target first, chaining each one's picks into the next one's minimum version.
    plan = []
    chain = dict(builds)
    for version in targets:
        asset = next(a for a in patch_releases[version]["assets"] if a["name"].endswith(".mpp"))
        mpp = download(asset["browser_download_url"], work / "patches" / asset["name"])
        supported = supported_versions(jar, mpp, [a["package"] for a in apps])
        floor = previous_build(chain, version)
        picks, errors = {}, []
        for app in apps:
            try:
                picks[app["asset_prefix"]] = pick_stock(app, stock, supported, floor.get(app["asset_prefix"]))
            except BuildError as e:
                errors.append(str(e))
        plan.append((version, mpp, picks, errors))
        if not errors:
            chain[version] = {prefix: s.version for prefix, s in picks.items()}

    if args.plan_only:
        write_summary(apps, [(v, picks, "; ".join(errors) or "planned") for v, _, picks, errors in plan])
        return 0

    keystore = Keystore(
        path=Path(os.environ.get("MORPHE_KEYSTORE", "")),
        password=os.environ.get("MORPHE_KEYSTORE_PASSWORD", ""),
        alias=os.environ.get("MORPHE_KEYSTORE_ALIAS") or "Morphe",
        entry_password=os.environ.get("MORPHE_KEYSTORE_ENTRY_PASSWORD") or "Morphe",
    )
    if not keystore.path.is_file() or keystore.path.stat().st_size == 0:
        raise SystemExit("MORPHE_KEYSTORE must point to the signing keystore")

    rows = []
    for version, mpp, picks, errors in plan:
        try:
            if errors:
                raise BuildError("; ".join(errors))
            out_dir = work / "out" / f"v{version}"
            out_dir.mkdir(parents=True, exist_ok=True)
            assets = []
            for app in apps:
                stock_apk = picks[app["asset_prefix"]]
                ensure_local(stock_apk, work / "stock")
                out_apk = out_dir / f"{app['asset_prefix']}-{stock_apk.version}-patches-{version}.apk"
                patch_app(jar, mpp, app, stock_apk, out_apk, work, keystore, cfg["signing_cert_sha256"])
                assets.append(out_apk)

            notes = release_notes(version, picks, previous_build(builds, version), apps)
            if args.dry_run:
                status = "built (dry run)"
            else:
                latest = all(vkey(version) > vkey(v) for v in builds)
                publish(args.repo, version, assets, notes, latest)
                shutil.rmtree(out_dir)
                status = "released"
            builds[version] = {prefix: s.version for prefix, s in picks.items()}
            print(f"v{version} {status}:\n{notes}")
            rows.append((version, picks, status))
        except BuildError as e:
            message = str(e)
            print(f"::error title=Patches v{version}::" + message.replace("\n", "%0A"))
            rows.append((version, picks, f"failed: {message.splitlines()[0]}"))

    write_summary(apps, rows)
    return 1 if any(status.startswith("failed") for _, _, status in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
