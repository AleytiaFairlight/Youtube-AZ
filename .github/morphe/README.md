# Automated YouTube AZ builds

[`build.yml`](../workflows/build.yml) runs every 6 hours (and on demand from the Actions tab). For every
stable [Morphe patches](https://github.com/MorpheApp/morphe-patches/releases) release newer than the last
published build (starting at `start_patches_version`), it:

1. Downloads the latest [Morphe Desktop](https://github.com/MorpheApp/morphe-desktop/releases) CLI and the patches `.mpp`.
2. Picks, for each app, the **newest uploaded stock APK the patches support** (never lower than the version in
   the previous release, so updates install over the old build).
3. Patches with the selections in [`config.json`](config.json), renaming the apps to **YouTube AZ** and
   **YouTube Music AZ**, and signs with the same keystore as the Morphe Desktop builds.
4. Checks that no patch failed and that the APK is signed with the expected certificate, then publishes
   release `vX.Y.Z` ("Update vX.Y.Z") with `YouTube-AZ-<ver>-patches-X.Y.Z.apk` and
   `YouTube-Music-AZ-<ver>-patches-X.Y.Z.apk`.

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

## Manual runs

Actions → Build YouTube AZ → Run workflow:

- **patches_version**: build one specific version (skipped if it already has a release).
- **dry_run**: build without publishing; the APKs are attached to the run as an artifact.

Locally, `python .github/morphe/build.py --repo AleytiaFairlight/Youtube-AZ --stock-dir <folder> --plan-only`
shows which stock APK each pending release would use.
