# Automated YouTube AZ builds

[`build.yml`](../workflows/build.yml) runs every 6 hours (and on demand from the Actions tab). For every
stable [Morphe patches](https://github.com/MorpheApp/morphe-patches/releases) release newer than the last
published build (starting at `start_patches_version`), it:

1. Downloads the latest [Morphe Desktop](https://github.com/MorpheApp/morphe-desktop/releases) CLI and the patches `.mpp`.
2. Picks, for each app, the **newest uploaded stock APK the patches support** (never lower than the version in
   the previous release, so updates install over the old build).
3. Patches with the selections in [`config.json`](config.json), renaming the apps to **YouTube AZ** and
   **YouTube Music AZ**, and signs with the same keystore as the Morphe Desktop builds.
4. Checks that no patch failed, that the app carries the new name and that the APK is signed with the
   expected certificate, then publishes release `vX.Y.Z` ("Update vX.Y.Z") with
   `YouTube-AZ-<ver>-patches-X.Y.Z.apk`, `YouTube-Music-AZ-<ver>-patches-X.Y.Z.apk` and
   `MicroG-RE-<ver>.apk`: the universal APK of the newest stable [MicroG RE](https://github.com/MorpheApp/MicroG-RE/releases)
   release published by the time the patches release came out (pre-releases are skipped).

A release is only published when both apps build. If no uploaded APK is supported, the run fails and the
error lists the versions to upload; the next run picks the release up again.

## One-time setup

**Secret `KEYSTORE_BASE64`** (Settings → Secrets and variables → Actions → New repository secret): the
base64 of `YouTube-Morphe-20.45.36-patches-1.23.0.keystore`. In PowerShell:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("H:\ReVanced-CLI-GU\YouTubeAZ\Morphe\APKs\YouTube\YouTube-Morphe-20.45.36-patches-1.23.0.keystore")) | Set-Clipboard
```

The keystore uses Morphe's defaults (empty store password, alias `Morphe`, key password `Morphe`). Only add
`KEYSTORE_PASSWORD`, `KEYSTORE_ALIAS` or `KEYSTORE_ENTRY_PASSWORD` secrets if you switch to a keystore with
different values.

**Draft release `stock-apks`** (Releases → Draft a new release → tag `stock-apks` → attach files → Save
draft). Attach the stock APKs from APKMirror with their original file names
(`com.google.android.youtube_21.20.405-…apkm`): the package and version are read from the name. Keep it a
draft so the stock APKs are not public.

## Adding a new stock version

When a patches release adds support for a newer YouTube or YouTube Music, upload that APK to the
`stock-apks` draft. The next run uses it automatically. Old stock files can be deleted once no future build
needs them.

## Morphe versions

`morphe_desktop_version` in [`config.json`](config.json) is `latest` by default. Morphe Desktop 1.19 and newer
patch both the 1.x patches and the 2.x patches (Morphe Patcher 2); Desktop 1.18 and older can't load patches
1.48.0 or newer. The build reads both result-file formats (Desktop ≤ 1.18 and ≥ 1.19), so an older Desktop can
still be pinned there, e.g. `"1.18.1"` to rebuild patches up to 1.47.0.

## Manual runs

Actions → Build YouTube AZ → Run workflow:

- **patches_version**: build one specific version (skipped if it already has a release).
- **dry_run**: build without publishing; the APKs are attached to the run as an artifact.

Locally, `python .github/morphe/build.py --repo AleytiaFairlight/Youtube-AZ --stock-dir <folder> --plan-only`
shows which stock APK each pending release would use.
