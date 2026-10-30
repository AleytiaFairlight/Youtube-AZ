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
