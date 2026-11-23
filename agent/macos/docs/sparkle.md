# Sparkle 2 in rMirror for Mac 2.0

Sparkle 2.10.1 (latest stable 2.x at time of writing; `2.11.0-beta.1` exists and is not used) is linked through SwiftPM
(`from: "2.10.1"`, product `Sparkle`, `RMirrorApp` target only). It stays **inert** unless the bundle's Info.plist has a
non-empty `SUFeedURL` **and** a non-empty `SUPublicEDKey`. Without them (or outside a bundle, e.g. `swift build` /
`--render-screens`) nothing from Sparkle is instantiated and the app uses the `version.json` check through the core.

Legend: **[verified-docs]** read in sparkle-project.org docs; **[verified-disk]** observed after `swift build`;
**[inference]** my reasoning, not stated by Sparkle; **[unverified]** not checked.

## 1. Where Sparkle lands and how to embed it  [verified-disk]

After `swift build -c release`:

- `.build/release` is a symlink to `.build/out/Products/Release`.
- Framework (universal x86_64+arm64, symlinks intact): `.build/release/Sparkle.framework`
  (debug: `.build/debug/Sparkle.framework`). Original copy: `.build/artifacts/sparkle/Sparkle/Sparkle.xcframework/macos-arm64_x86_64/Sparkle.framework`.
- Contents: `Versions/B/{Sparkle,Autoupdate,Updater.app,XPCServices/{Downloader.xpc,Installer.xpc},Resources,...}`.
- Tools: `.build/artifacts/sparkle/Sparkle/bin/{generate_keys,generate_appcast,sign_update,BinaryDelta}`.

Embed (preserve symlinks; `ditto` or `cp -a`, never plain `cp -R` without `-a`):

```sh
mkdir -p rMirror.app/Contents/Frameworks
ditto .build/release/Sparkle.framework rMirror.app/Contents/Frameworks/Sparkle.framework
```

Optionally strip files not needed at runtime (`Headers`, `Modules`, `PrivateHeaders`) - [inference], not required.

### rpath

`otool -l .build/release/RMirrorApp` shows exactly three LC_RPATH entries: `/usr/lib/swift`, `@loader_path`, and the Xcode
toolchain swift dir. (Debug adds `.build/out/Products/Debug/PackageFrameworks`.) The executable links
`@rpath/Sparkle.framework/Versions/B/Sparkle`. `@loader_path` only finds the framework when it sits next to the executable
(`Contents/MacOS/`), which is not where it goes in a bundle, so add:

```sh
install_name_tool -add_rpath @executable_path/../Frameworks rMirror.app/Contents/MacOS/RMirrorApp
```

This invalidates the signature, so do it before any `codesign`. Sparkle's docs suggest `-Wl,-rpath,@loader_path/../Frameworks`
as a linker flag [verified-docs]; the `install_name_tool` route is equivalent for an executable [inference].
Check afterwards: `otool -l .../RMirrorApp | grep -A2 LC_RPATH` and `otool -L` (both must resolve).

## 2. Code signing order (Developer ID, hardened runtime, not sandboxed)

Sparkle docs (Sandboxing > Code Signing) give this inside-out order **[verified-docs]**; they say not to use `--deep`.
The `Installer.xpc`/`Downloader.xpc` services are only needed by *sandboxed* apps; the docs say a non-sandboxed app may remove
them **[verified-docs]**, whether the Downloader signing line is needed then is **[inference]: no**. Safest and simplest: keep
them and sign them (harmless), or delete `XPCServices/` before signing and skip the first two lines. Choose one, consistently.
Do not set `SUEnableInstallerLauncherService` (sandbox only).

```sh
FW=rMirror.app/Contents/Frameworks/Sparkle.framework/Versions/B
# 1. XPC services (skip if you deleted XPCServices/)
codesign -f -s "$CODESIGN_IDENTITY" -o runtime --timestamp "$FW/XPCServices/Installer.xpc"
codesign -f -s "$CODESIGN_IDENTITY" -o runtime --timestamp --preserve-metadata=entitlements "$FW/XPCServices/Downloader.xpc"   # Sparkle >= 2.6
# 2. helpers
codesign -f -s "$CODESIGN_IDENTITY" -o runtime --timestamp "$FW/Autoupdate"
codesign -f -s "$CODESIGN_IDENTITY" -o runtime --timestamp "$FW/Updater.app"
# 3. the framework
codesign -f -s "$CODESIGN_IDENTITY" -o runtime --timestamp rMirror.app/Contents/Frameworks/Sparkle.framework
# 4. then the app's other nested code (Python core etc.), then the app itself with the app's entitlements
codesign -f -s "$CODESIGN_IDENTITY" -o runtime --timestamp --entitlements <app.entitlements> rMirror.app
codesign --verify --strict --verbose=2 rMirror.app
```

**[verified-disk, 2026-11-23]** `scripts/build_app.sh` follows this order with the XPC services kept and signed, no
entitlements anywhere, and a universal `RMirrorApp` (`swift build -c release --arch arm64 --arch x86_64`; products
in `<scratch>/out/Products/Release/`, `Sparkle.framework` included; `install_name_tool -add_rpath` adds the rpath to
both slices). Result: `codesign --verify --deep --strict` passes, the DMG was notarized (Accepted) and stapled, and
`spctl -a` accepts the app copied out of the DMG as "Notarized Developer ID".

`--timestamp` is not in Sparkle's snippet but is required for notarization [inference from Apple's rules]. The app is signed
last. Library validation: signing Sparkle with the same Developer ID team as the app satisfies it; no
`disable-library-validation` entitlement is needed [inference]; the docs mention disabling it only for ad-hoc/Debug runs.

## 3. Info.plist keys

| Key | Value | Notes |
|---|---|---|
| `SUFeedURL` | `https://<downloads-host>/releases/appcast-arm64.xml` (per arch, see section 5) | required; absent/empty = Sparkle off |
| `SUPublicEDKey` | base64 string printed by `generate_keys` | required; absent/empty = Sparkle off |
| `SUEnableAutomaticChecks` | `true` | unset = Sparkle asks the user on the second launch [verified-docs]; `true` = no prompt. Recommended `true` for a menu-bar app, which has no good place for the prompt |
| `SUScheduledCheckInterval` | `86400` | seconds; default 86400, minimum 3600 [verified-docs] |
| `SUAutomaticallyUpdate` | leave unset (`NO`) | `YES` installs silently; the app also hosts a Python core, so keep install user-confirmed |
| `SUVerifyUpdateBeforeExtraction` | optional `true` | Sparkle 2.7.3+, needs EdDSA; only required for Apple Archive [verified-docs] |

Leaving `SUFeedURL`/`SUPublicEDKey` out disables Sparkle and `Updater` falls back to the `version.json` alert.

## 4. Owner steps at release time

1. Create the key once: `.build/artifacts/sparkle/Sparkle/bin/generate_keys`. The private key goes into the **login Keychain**
   (item "https://sparkle-project.org"); the public key is printed for `SUPublicEDKey` [verified-docs]. Back up:
   `generate_keys -x <file>` exports the private key (store offline, never commit); `generate_keys -f <file>` imports it on another Mac [verified-docs].
   Losing the key means installed apps can never be updated by Sparkle again.
2. Build, sign, notarize, staple each DMG, then put the DMGs for one architecture in a folder and run
   `generate_appcast <folder>` (signs entries with the Keychain key and writes `appcast.xml`; also makes delta updates
   [verified-docs]). The page documents no flags; check `generate_appcast --help` [unverified]. Typical extras such as
   `--download-url-prefix` exist in recent versions [unverified - confirm with `--help`].
3. Upload the DMG(s) and appcast to the downloads host (B2 next to `version.json`): e.g.
   `https://<downloads-host>/releases/appcast-arm64.xml`, `appcast-x86_64.xml`, and the DMGs they reference. The host must be
   HTTPS. Keep `version.json` (used by the fallback and the dashboard) in step.
4. Ship the app with `SUFeedURL`/`SUPublicEDKey`/`SUEnableAutomaticChecks` set at build time.

## 5. Two architectures (arm64 DMG and x86_64 DMG)

What the docs say [verified-docs]: from Sparkle 2.9 an appcast item can carry
`<sparkle:hardwareRequirements>arm64</sparkle:hardwareRequirements>` to require Apple silicon. The docs describe no
x86_64 counterpart and no per-architecture enclosure selection.

Options:

- **A. Two feeds, chosen at build time (recommended).** `SUFeedURL` is `.../appcast-arm64.xml` in the arm64 build and
  `.../appcast-x86_64.xml` in the x86_64 build. Each feed lists only DMGs of its own architecture. Pros: needs nothing beyond
  documented behaviour; an Intel Mac can never be offered an arm64 core. Cons: two appcasts to publish; the architecture is fixed
  per installed app (fine, since the bundled core is too); a user who moves from Intel to Apple silicon keeps the Intel build
  until they reinstall (Rosetta runs it).
- **B. One feed, `hardwareRequirements=arm64` on the arm64 item plus a plain item for Intel.** [inference] Intel Macs skip the
  arm64 item, but Apple silicon Macs see both items and, with equal version numbers, selection is not documented, so an arm64
  Mac could be offered the Intel build. Would need different `sparkle:version` ordering, which breaks the version scheme.
  Not recommended without testing [unverified].

Recommendation: A.

## 6. Updating from a DMG

Yes. Sparkle accepts `.dmg`, `.zip`, `.tar.*`, `.aar` (Apple Archive, 2.7+) and installer pkg. DMG recommendation:
APFS-formatted, LZFSE-compressed images (decompression speed) [verified-docs]. The DMG should contain the app at its top
level; a layout with an `/Applications` symlink next to the app is fine [inference]. Symlinks inside the app must be preserved;
for zips use `ditto -c -k --sequesterRsrc --keepParent`.

## 7. App behaviour (for whoever wires AppDelegate)

`Updater` implements `SPUStandardUserDriverDelegate` with `supportsGentleScheduledUpdateReminders = true`. When Sparkle is about to
show an update it sets the activation policy to `.regular`, calls the presenter closure, activates the app, and for scheduled
checks badges the Dock icon (cleared when the user sees the update). It does not switch back to `.accessory`; the window manager
already does that when the last window closes. No user-notification permission flow is implemented (the Sparkle sample adds
one; optional). A scheduled-alert loss is therefore only possible if the window manager flips the policy to `.accessory` while
the Sparkle window is open [inference]; check this when hand-testing against a real feed [unverified].
