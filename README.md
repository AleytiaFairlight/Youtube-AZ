# YouTube AZ

Patched builds of **YouTube** and **YouTube Music**, made with the [Morphe patches](https://github.com/MorpheApp/morphe-patches).
New builds are published automatically when a new Morphe patches release comes out.

**[Download the latest release](https://github.com/AleytiaFairlight/Youtube-AZ/releases/latest)**

## What's in a release

Every release from v1.23.0 on has three files:

| File | What it is |
|---|---|
| `MicroG-RE-<version>.apk` | [MicroG RE](https://github.com/MorpheApp/MicroG-RE), needed to sign in with your Google account. **Install this first.** |
| `YouTube-AZ-<version>-patches-<version>.apk` | YouTube AZ |
| `YouTube-Music-AZ-<version>-patches-<version>.apk` | YouTube Music AZ |

Each release includes the MicroG RE version that was current when its Morphe patches came out.

## Installation

1. **Remove old builds if you have them.** If you used a ReVanced-based build (v4.x or v5.x) or an old
   GmsCore / Vanced microG, uninstall it first. Those are signed with different keys, so the new apps
   won't install over them.
2. **Install MicroG RE.** Download `MicroG-RE-<version>.apk` from the release and install it. If Android
   asks, allow your browser or file manager to install unknown apps.
3. **Set up MicroG RE.** Open MicroG RE once and allow what it asks for (notifications, and running in
   the background / no battery optimization), so sign-in and notifications work.
4. **Install the apps.** Download and install `YouTube-AZ-…apk` and/or `YouTube-Music-AZ-…apk` from the
   same release.
5. **Sign in.** Open YouTube AZ or YouTube Music AZ and sign in; MicroG RE handles the Google account.

YouTube AZ and YouTube Music AZ install next to the official YouTube apps, so you don't have to remove those.

## Updating

- Install the new `YouTube-AZ` / `YouTube-Music-AZ` APK over the one you have. Your settings and sign-in stay.
- When a release lists a newer MicroG RE, install that over your current MicroG RE too.

## Requirements

- YouTube AZ: Android 10 or newer for the current releases.
- YouTube Music AZ: Android 8 or newer, on a 64-bit (arm64) phone.

## Troubleshooting

- **"App not installed"**: an older build signed with a different key is still installed. Uninstall it
  (see step 1) and install again.
- **Can't sign in, or "no Google services"**: check that MicroG RE is installed and was opened once, and
  that it is the version from the release (or newer).
- **No notifications**: allow notifications for MicroG RE and turn off battery optimization for it.

## Older files

The `GMS ( Please Install before using any of the versions )` folder holds the MicroG builds that went with
the older ReVanced-based releases. For releases from v1.23.0 on, use the MicroG RE APK attached to the release.

## How the builds are made

See [.github/morphe/README.md](.github/morphe/README.md).
