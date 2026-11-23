#!/bin/bash
#
# Build rMirror for Mac 2.0: rMirror.app (Swift shell + bundled Python core) and a signed,
# notarized, stapled DMG.
#
# Usage (from anywhere):
#   CODESIGN_IDENTITY="Developer ID Application: Name (TEAMID)" agent/macos/scripts/build_app.sh
#   agent/macos/scripts/build_app.sh --unsigned           # local test build: ad-hoc signed, no DMG checks
#   CODESIGN_IDENTITY=... agent/macos/scripts/build_app.sh --skip-notarize
#
# Options:
#   --unsigned          ad-hoc sign instead of Developer ID; skips notarization and Gatekeeper checks.
#                       Never distribute such a build.
#   --skip-notarize     sign with Developer ID but do not notarize/staple (spctl checks are skipped).
#   --arch ARCH         architecture of the Python core: arm64 or x86_64 (default: host). The Poetry
#                       Python must run natively as ARCH (PyInstaller builds for its own interpreter).
#                       The Swift executable is universal regardless.
#   -h, --help          this text.
#
# Environment:
#   CODESIGN_IDENTITY      required unless --unsigned.
#   NOTARY_PROFILE         notarytool keychain profile (default rmirror-notarization).
#   NOTARY_KEYCHAIN        optional keychain file holding that profile (CI); default: login keychain.
#   BUILD_DIR              work and output directory (default agent/macos/build). Must not be in iCloud.
#   BUILD_NUMBER           CFBundleVersion (default: git commit count of HEAD).
#   SPARKLE_FEED_URL       } both set: Sparkle keys are written into Info.plist (see docs/sparkle.md).
#   SPARKLE_PUBLIC_ED_KEY  } otherwise the keys are absent and Sparkle stays inactive.
#   DMG_FINDER_LAYOUT=1    let create-dmg lay out the DMG window with Finder (AppleScript; needs
#                          Automation permission for Finder). Default: no Finder scripting.
#
# Output: $BUILD_DIR/app/rMirror.app and $BUILD_DIR/dist/rMirror-<version>-<arch>.dmg
# This script never uploads, tags or publishes anything.

set -euo pipefail

# ---------------------------------------------------------------------------------------------
# Paths, options
# ---------------------------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"          # agent/macos
AGENT_DIR="$(cd "$PKG_DIR/.." && pwd)"           # agent
REPO_DIR="$(cd "$AGENT_DIR/.." && pwd)"

UNSIGNED=0
SKIP_NOTARIZE=0
ARCH="$(uname -m)"

while [ $# -gt 0 ]; do
    case "$1" in
        --unsigned) UNSIGNED=1 ;;
        --skip-notarize) SKIP_NOTARIZE=1 ;;
        --arch)
            [ $# -ge 2 ] || { echo "--arch needs a value (arm64 or x86_64)" >&2; exit 2; }
            ARCH="$2"; shift ;;
        --arch=*) ARCH="${1#--arch=}" ;;
        -h|--help) sed -n '2,33p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
    shift
done

case "$ARCH" in
    arm64|x86_64) ;;
    *) echo "--arch must be arm64 or x86_64, got: $ARCH" >&2; exit 2 ;;
esac

NOTARY_PROFILE="${NOTARY_PROFILE:-rmirror-notarization}"
NOTARY_KEYCHAIN="${NOTARY_KEYCHAIN:-}"
CODESIGN_IDENTITY="${CODESIGN_IDENTITY:-}"
if [ "$UNSIGNED" -eq 1 ]; then
    SKIP_NOTARIZE=1
    SIGN_ID="-"
else
    if [ -z "$CODESIGN_IDENTITY" ]; then
        echo "ERROR: CODESIGN_IDENTITY is not set (or pass --unsigned for a local test build)." >&2
        exit 2
    fi
    SIGN_ID="$CODESIGN_IDENTITY"
fi

BUILD_DIR="${BUILD_DIR:-$PKG_DIR/build}"
mkdir -p "$BUILD_DIR"
BUILD_DIR="$(cd "$BUILD_DIR" && pwd -P)"

APP_NAME="rMirror"
PYI_DIR="$BUILD_DIR/pyinstaller"       # PyInstaller work + dist
SWIFT_DIR="$BUILD_DIR/swift"           # SwiftPM scratch path (kept between runs, incremental)
ICON_DIR="$BUILD_DIR/icon"
APP_DIR="$BUILD_DIR/app"
APP="$APP_DIR/$APP_NAME.app"
DMG_SRC="$BUILD_DIR/dmg-src"
DIST_DIR="$BUILD_DIR/dist"
VERIFY_DIR="$BUILD_DIR/verify"

# ---------------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------------

CURRENT_STEP="startup"
step() {
    CURRENT_STEP="$1"
    echo ""
    echo "==> [$CURRENT_STEP]"
}
on_exit() {
    local code=$?
    if [ "$code" -ne 0 ]; then
        echo "" >&2
        echo "BUILD FAILED in step: $CURRENT_STEP (exit $code)" >&2
    fi
}
trap on_exit EXIT

die() {
    echo "ERROR: $*" >&2
    exit 1
}

warn_loud() {
    echo "" >&2
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2
    echo "!! WARNING: $*" >&2
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2
    echo "" >&2
}

# rm -rf only for directories this script constructed under $BUILD_DIR.
safe_rm() {
    local target="$1"
    [ -n "$target" ] || die "safe_rm: empty path"
    case "$target" in
        /|/*/..|*/../*|..|.) die "safe_rm: refusing suspicious path: $target" ;;
    esac
    case "$target" in
        "$BUILD_DIR"/?*) ;;
        *) die "safe_rm: $target is not inside $BUILD_DIR" ;;
    esac
    [ "$BUILD_DIR" != "/" ] || die "safe_rm: BUILD_DIR is /"
    rm -rf "$target"
}

codesign_file() {
    # codesign_file <path> [extra codesign args...]
    local path="$1"; shift
    if [ "$UNSIGNED" -eq 1 ]; then
        codesign --force --sign - "$@" "$path"
    else
        codesign --force --sign "$SIGN_ID" --options runtime --timestamp "$@" "$path"
    fi
}

notary_args() {
    printf '%s\n' --keychain-profile "$NOTARY_PROFILE"
    if [ -n "$NOTARY_KEYCHAIN" ]; then
        printf '%s\n' --keychain "$NOTARY_KEYCHAIN"
    fi
}

# ---------------------------------------------------------------------------------------------
# (a) Preflight
# ---------------------------------------------------------------------------------------------

step "preflight"

case "$BUILD_DIR" in
    "$HOME/Library/Mobile Documents"|"$HOME/Library/Mobile Documents"/*|"$HOME/Library/CloudStorage"/*)
        die "BUILD_DIR is inside iCloud/File Provider storage ($BUILD_DIR). Use a local path." ;;
esac
# Any ancestor managed by a File Provider (iCloud Drive "Desktop & Documents" and similar)?
probe="$BUILD_DIR"
while [ -n "$probe" ] && [ "$probe" != "/" ]; do
    if xattr "$probe" 2>/dev/null | grep -q '^com\.apple\.fileprovider'; then
        die "BUILD_DIR $BUILD_DIR is under $probe, which has a com.apple.fileprovider xattr (iCloud/File Provider). Use a local path."
    fi
    probe="$(dirname "$probe")"
done
case "$BUILD_DIR" in
    "$HOME/Documents"|"$HOME/Documents"/*|"$HOME/Desktop"|"$HOME/Desktop"/*)
        echo "note: BUILD_DIR is under ~/Documents or ~/Desktop; if iCloud 'Desktop & Documents' is on, signing will fail with xattr errors." ;;
esac

for tool in swift poetry codesign xcrun lipo otool install_name_tool sips iconutil ditto file plutil create-dmg hdiutil shasum openssl curl git; do
    command -v "$tool" >/dev/null 2>&1 || die "required tool not found: $tool"
done

if [ "$UNSIGNED" -eq 0 ]; then
    if ! security find-identity -v -p codesigning | grep -qF "\"$CODESIGN_IDENTITY\""; then
        die "signing identity not found in the keychain search list: $CODESIGN_IDENTITY"
    fi
fi

VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$AGENT_DIR/app/__version__.py")"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "could not read a x.y.z version from agent/app/__version__.py (got '$VERSION')"
BUILD_NUMBER="${BUILD_NUMBER:-$(git -C "$REPO_DIR" rev-list --count HEAD)}"
[[ "$BUILD_NUMBER" =~ ^[0-9]+$ ]] || die "BUILD_NUMBER must be an integer, got '$BUILD_NUMBER'"
GIT_SHA="$(git -C "$REPO_DIR" rev-parse --short HEAD)"

SPARKLE_ON=0
if [ -n "${SPARKLE_FEED_URL:-}" ] && [ -n "${SPARKLE_PUBLIC_ED_KEY:-}" ]; then
    SPARKLE_ON=1
elif [ -n "${SPARKLE_FEED_URL:-}" ] || [ -n "${SPARKLE_PUBLIC_ED_KEY:-}" ]; then
    die "set both SPARKLE_FEED_URL and SPARKLE_PUBLIC_ED_KEY, or neither"
fi

echo "version:        $VERSION (build $BUILD_NUMBER, $GIT_SHA)"
echo "core arch:      $ARCH"
echo "build dir:      $BUILD_DIR"
echo "signing:        $([ "$UNSIGNED" -eq 1 ] && echo 'ad-hoc (--unsigned)' || echo "$CODESIGN_IDENTITY")"
echo "notarize:       $([ "$SKIP_NOTARIZE" -eq 1 ] && echo 'no' || echo "yes (profile $NOTARY_PROFILE)")"
echo "sparkle:        $([ "$SPARKLE_ON" -eq 1 ] && echo "on ($SPARKLE_FEED_URL)" || echo 'off (no feed/key)')"
echo "macOS:          $(sw_vers -productVersion) ($(uname -m))"
echo "xcode:          $(xcodebuild -version 2>/dev/null | tr '\n' ' ')"
echo "swift:          $(swift --version 2>&1 | head -1)"
echo "poetry:         $(poetry --version)"
echo "create-dmg:     $(create-dmg --version 2>&1 | head -1)"

# ---------------------------------------------------------------------------------------------
# (b) Python core (PyInstaller onedir)
# ---------------------------------------------------------------------------------------------

step "python core"
cd "$AGENT_DIR"
if ! poetry run python -c "import PyInstaller" >/dev/null 2>&1; then
    echo "installing Python dependencies (poetry install)"
    poetry install --no-root
fi
PY_ARCH="$(poetry run python -c 'import platform; print(platform.machine())')"
[ "$PY_ARCH" = "$ARCH" ] || die "Poetry's Python runs as $PY_ARCH but --arch is $ARCH. Build the $ARCH core on a $ARCH machine (CI: the Intel runner)."
echo "python:         $(poetry run python --version) ($PY_ARCH), PyInstaller $(poetry run python -c 'import PyInstaller; print(PyInstaller.__version__)')"

safe_rm "$PYI_DIR"
mkdir -p "$PYI_DIR"
poetry run pyinstaller --noconfirm --clean \
    --distpath "$PYI_DIR/dist" \
    --workpath "$PYI_DIR/work" \
    rmirror-core.spec 2>&1 | grep -Ev '^[0-9]+ INFO:' || true
CORE_SRC="$PYI_DIR/dist/rmirror-core"
[ -x "$CORE_SRC/rmirror-core" ] || die "PyInstaller did not produce $CORE_SRC/rmirror-core"
file "$CORE_SRC/rmirror-core"
file "$CORE_SRC/rmirror-core" | grep -q "$ARCH" || die "core executable is not $ARCH"

# ---------------------------------------------------------------------------------------------
# (c) Swift app (universal if possible)
# ---------------------------------------------------------------------------------------------

step "swift build"
cd "$PKG_DIR"
SWIFT_UNIVERSAL=1
if swift build -c release --scratch-path "$SWIFT_DIR" --arch arm64 --arch x86_64; then
    SWIFT_BIN="$(swift build -c release --scratch-path "$SWIFT_DIR" --arch arm64 --arch x86_64 --show-bin-path)"
else
    SWIFT_UNIVERSAL=0
    warn_loud "universal Swift build failed; falling back to a host-only ($(uname -m)) Swift executable. The app will NOT run on the other architecture."
    swift build -c release --scratch-path "$SWIFT_DIR"
    SWIFT_BIN="$(swift build -c release --scratch-path "$SWIFT_DIR" --show-bin-path)"
fi
[ -x "$SWIFT_BIN/RMirrorApp" ] || die "no RMirrorApp in $SWIFT_BIN"
[ -d "$SWIFT_BIN/Sparkle.framework" ] || die "no Sparkle.framework in $SWIFT_BIN"
lipo -info "$SWIFT_BIN/RMirrorApp"
# (lipo -verify_arch rejects its input on this toolchain, so compare `lipo -archs` instead)
SWIFT_ARCHS=" $(lipo -archs "$SWIFT_BIN/RMirrorApp") "
if [ "$SWIFT_UNIVERSAL" -eq 1 ]; then
    case "$SWIFT_ARCHS" in *" arm64 "*) ;; *) die "RMirrorApp has no arm64 slice" ;; esac
    case "$SWIFT_ARCHS" in *" x86_64 "*) ;; *) die "RMirrorApp has no x86_64 slice" ;; esac
fi
case "$SWIFT_ARCHS" in *" $ARCH "*) ;; *) die "RMirrorApp has no $ARCH slice" ;; esac

# ---------------------------------------------------------------------------------------------
# (d) Assemble rMirror.app
# ---------------------------------------------------------------------------------------------

step "icon"
safe_rm "$ICON_DIR"
mkdir -p "$ICON_DIR/AppIcon.iconset"
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$AGENT_DIR/resources/icon.png" \
        --out "$ICON_DIR/AppIcon.iconset/icon_${size}x${size}.png" >/dev/null
    sips -z $((size * 2)) $((size * 2)) "$AGENT_DIR/resources/icon.png" \
        --out "$ICON_DIR/AppIcon.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICON_DIR/AppIcon.iconset" -o "$ICON_DIR/AppIcon.icns"

step "assemble"
safe_rm "$APP_DIR"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$APP/Contents/Frameworks"

ditto "$SWIFT_BIN/RMirrorApp" "$APP/Contents/MacOS/RMirrorApp"
ditto "$CORE_SRC" "$APP/Contents/Resources/core"
ditto "$SWIFT_BIN/Sparkle.framework" "$APP/Contents/Frameworks/Sparkle.framework"
ditto "$ICON_DIR/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
printf 'APPL????' > "$APP/Contents/PkgInfo"

sed -e "s/__VERSION__/$VERSION/" \
    -e "s/__BUILD_NUMBER__/$BUILD_NUMBER/" \
    -e "s/__COPYRIGHT_YEAR__/$(date +%Y)/" \
    "$PKG_DIR/Resources/Info.plist" > "$APP/Contents/Info.plist"
if [ "$SPARKLE_ON" -eq 1 ]; then
    plutil -insert SUFeedURL -string "$SPARKLE_FEED_URL" "$APP/Contents/Info.plist"
    plutil -insert SUPublicEDKey -string "$SPARKLE_PUBLIC_ED_KEY" "$APP/Contents/Info.plist"
    plutil -insert SUEnableAutomaticChecks -bool YES "$APP/Contents/Info.plist"
fi
plutil -lint "$APP/Contents/Info.plist"
if grep -q '__[A-Z_]*__' "$APP/Contents/Info.plist"; then
    die "unfilled placeholder in Info.plist"
fi

# rpath so @rpath/Sparkle.framework resolves from Contents/MacOS (docs/sparkle.md section 1)
if ! otool -l "$APP/Contents/MacOS/RMirrorApp" | grep -q '@executable_path/../Frameworks'; then
    install_name_tool -add_rpath @executable_path/../Frameworks "$APP/Contents/MacOS/RMirrorApp"
fi
otool -l "$APP/Contents/MacOS/RMirrorApp" | grep -A2 LC_RPATH | grep path
otool -L "$APP/Contents/MacOS/RMirrorApp" | grep -q '@rpath/Sparkle.framework/Versions/B/Sparkle' \
    || die "RMirrorApp does not link @rpath/Sparkle.framework/Versions/B/Sparkle"

# ---------------------------------------------------------------------------------------------
# (e) Extended attributes: freshly assembled files must carry none (FinderInfo, quarantine, ...)
# ---------------------------------------------------------------------------------------------

step "clear xattrs"
xattr -cr "$APP"
# com.apple.provenance (macOS 13+) is kernel-managed, cannot be removed and is ignored by codesign.
# Anything else left over (FinderInfo, resource forks, quarantine) would break --strict verification.
LEFTOVER="$BUILD_DIR/xattr-leftover.txt"
xattr -lr "$APP" 2>/dev/null | grep -v ': com\.apple\.provenance:' > "$LEFTOVER" || true
if [ -s "$LEFTOVER" ]; then
    sed -n '1,20p' "$LEFTOVER"
    die "extended attributes other than com.apple.provenance remain on the bundle"
fi

# ---------------------------------------------------------------------------------------------
# (f) Sign inside-out (never --deep)
# ---------------------------------------------------------------------------------------------

step "sign core"
CORE_DIR="$APP/Contents/Resources/core"
CORE_EXE="$CORE_DIR/rmirror-core"
CORE_ENTITLEMENTS="$PKG_DIR/Resources/core.entitlements"
MACHO_LIST="$BUILD_DIR/core-macho.txt"
: > "$MACHO_LIST"
while IFS= read -r -d '' f; do
    [ "$f" = "$CORE_EXE" ] && continue
    if file -b "$f" | grep -q 'Mach-O'; then
        printf '%s\n' "$f" >> "$MACHO_LIST"
    fi
done < <(find "$CORE_DIR" -type f -print0)
echo "signing $(wc -l < "$MACHO_LIST" | tr -d ' ') Mach-O files in the core, then the core executable"
while IFS= read -r f; do
    codesign_file "$f" || die "codesign failed: $f"
done < "$MACHO_LIST"
if [ -f "$CORE_ENTITLEMENTS" ]; then
    echo "core entitlements: $CORE_ENTITLEMENTS"
    codesign_file "$CORE_EXE" --entitlements "$CORE_ENTITLEMENTS"
else
    echo "core entitlements: none"
    codesign_file "$CORE_EXE"
fi

step "sign sparkle"
FW="$APP/Contents/Frameworks/Sparkle.framework"
FWV="$FW/Versions/B"
[ -d "$FWV" ] || die "Sparkle.framework has no Versions/B"
# Order from docs/sparkle.md section 2 (XPC services kept and signed)
codesign_file "$FWV/XPCServices/Installer.xpc"
codesign_file "$FWV/XPCServices/Downloader.xpc" --preserve-metadata=entitlements
codesign_file "$FWV/Autoupdate"
codesign_file "$FWV/Updater.app"
codesign_file "$FW"

step "sign app"
APP_ENTITLEMENTS="$PKG_DIR/Resources/app.entitlements"
if [ -f "$APP_ENTITLEMENTS" ]; then
    codesign_file "$APP" --entitlements "$APP_ENTITLEMENTS"
else
    codesign_file "$APP"
fi

# ---------------------------------------------------------------------------------------------
# (g) Verify the app, smoke-test the signed core
# ---------------------------------------------------------------------------------------------

step "verify app"
codesign --verify --deep --strict --verbose=2 "$APP"
codesign -dv "$APP" 2>&1 | grep -E 'Identifier|Format|flags|TeamIdentifier|Timestamp' || true

step "smoke-test signed core"
"$SCRIPT_DIR/smoke_core.sh" "$CORE_EXE"

# ---------------------------------------------------------------------------------------------
# (h) DMG
# ---------------------------------------------------------------------------------------------

step "dmg"
DMG_NAME="$APP_NAME-$VERSION-$ARCH.dmg"
DMG="$DIST_DIR/$DMG_NAME"
mkdir -p "$DIST_DIR"
[ -n "$DMG_NAME" ] && rm -f "$DMG"
safe_rm "$DMG_SRC"
mkdir -p "$DMG_SRC"
ditto "$APP" "$DMG_SRC/$APP_NAME.app"

DMG_ARGS=(
    --volname "$APP_NAME"
    --volicon "$ICON_DIR/AppIcon.icns"
    --window-pos 200 120
    --window-size 600 400
    --icon-size 100
    --icon "$APP_NAME.app" 150 190
    --hide-extension "$APP_NAME.app"
    --app-drop-link 450 190
    --no-internet-enable
    --filesystem APFS
    --format ULFO
)
if [ "${DMG_FINDER_LAYOUT:-0}" != "1" ]; then
    DMG_ARGS+=(--skip-jenkins)
fi
create-dmg "${DMG_ARGS[@]}" "$DMG" "$DMG_SRC" || die "create-dmg failed"
[ -f "$DMG" ] || die "create-dmg did not produce $DMG"
if [ "$UNSIGNED" -eq 1 ]; then
    codesign --force --sign - "$DMG"
else
    codesign --force --sign "$SIGN_ID" --timestamp "$DMG"
fi
codesign --verify --strict --verbose=2 "$DMG"

# ---------------------------------------------------------------------------------------------
# (i) Notarize and staple
#
# Apple: notarize and staple the outermost container you distribute. Notarizing the DMG makes
# Apple record tickets for everything inside it (the app included); `stapler staple` attaches the
# DMG's ticket to the DMG. The app inside is not stapled itself; Gatekeeper finds its ticket online
# when the app is first opened after being copied out. (Stapling the app as well would need a
# second submission of the app on its own before the DMG is made.)
# ---------------------------------------------------------------------------------------------

NOTARY_ID=""
if [ "$SKIP_NOTARIZE" -eq 0 ]; then
    step "notarize"
    NOTARY_ARGS=()
    while IFS= read -r a; do NOTARY_ARGS+=("$a"); done < <(notary_args)
    SUBMIT_JSON="$BUILD_DIR/notary-submit.json"
    SUBMIT_ERR="$BUILD_DIR/notary-submit.err"
    status=""
    for attempt in 1 2 3 4; do
        echo "submitting $DMG_NAME (attempt $attempt)"
        rc=0
        xcrun notarytool submit "$DMG" "${NOTARY_ARGS[@]}" --wait --timeout 60m \
            --output-format json > "$SUBMIT_JSON" 2> "$SUBMIT_ERR" || rc=$?
        NOTARY_ID="$(plutil -extract id raw -o - "$SUBMIT_JSON" 2>/dev/null || true)"
        status="$(plutil -extract status raw -o - "$SUBMIT_JSON" 2>/dev/null || true)"
        echo "notarytool exit $rc, id ${NOTARY_ID:-none}, status ${status:-none}"
        if [ -n "$status" ]; then
            break
        fi
        tail -n 30 "$SUBMIT_ERR" >&2 || true
        if grep -qiE 'HTTP status code: 403|agreement|unauthori[sz]ed|HTTP status code: 401|invalid credentials|No Keychain password item' "$SUBMIT_ERR"; then
            die "notarization refused (credentials or agreement); not retrying"
        fi
        if [ "$attempt" -lt 4 ]; then
            echo "transient notarization error? retrying in 60 s"
            sleep 60
        fi
    done
    [ -n "$status" ] || die "notarization did not return a status after 4 attempts"
    if [ "$status" != "Accepted" ]; then
        echo "notarization status: $status (submission $NOTARY_ID)" >&2
        if [ -n "$NOTARY_ID" ]; then
            xcrun notarytool log "$NOTARY_ID" "${NOTARY_ARGS[@]}" >&2 || true
        fi
        die "notarization not accepted"
    fi
    echo "notarization accepted: $NOTARY_ID"

    step "staple"
    xcrun stapler staple "$DMG"
fi

# ---------------------------------------------------------------------------------------------
# (j) Final checks (all must pass)
# ---------------------------------------------------------------------------------------------

step "final checks"
echo "--- codesign --verify --deep --strict (app)"
codesign --verify --deep --strict --verbose=2 "$APP"
if [ "$SKIP_NOTARIZE" -eq 0 ]; then
    echo "--- stapler validate (dmg)"
    xcrun stapler validate "$DMG"
    echo "--- spctl (dmg)"
    spctl -a -vv -t open --context context:primary-signature "$DMG"

    echo "--- spctl (app copied out of the mounted dmg)"
    safe_rm "$VERIFY_DIR"
    mkdir -p "$VERIFY_DIR/mnt"
    hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$VERIFY_DIR/mnt" "$DMG" >/dev/null
    copy_rc=0
    ditto "$VERIFY_DIR/mnt/$APP_NAME.app" "$VERIFY_DIR/$APP_NAME.app" || copy_rc=$?
    [ -L "$VERIFY_DIR/mnt/Applications" ] || copy_rc=1
    hdiutil detach "$VERIFY_DIR/mnt" >/dev/null || hdiutil detach -force "$VERIFY_DIR/mnt" >/dev/null
    [ "$copy_rc" -eq 0 ] || die "could not copy the app out of the DMG (or no Applications link)"
    spctl -a -vv "$VERIFY_DIR/$APP_NAME.app"
else
    echo "(notarization skipped: no stapler/spctl checks)"
fi

DMG_SHA="$(shasum -a 256 "$DMG" | cut -d' ' -f1)"
DMG_BYTES="$(stat -f %z "$DMG")"

step "summary"
echo "app:        $APP ($(du -sh "$APP" | cut -f1))"
echo "  core:     $(du -sh "$APP/Contents/Resources/core" | cut -f1)"
echo "  sparkle:  $(du -sh "$APP/Contents/Frameworks/Sparkle.framework" | cut -f1)"
echo "  swift:    $(du -sh "$APP/Contents/MacOS/RMirrorApp" | cut -f1) ($(lipo -archs "$APP/Contents/MacOS/RMirrorApp"))"
echo "dmg:        $DMG"
echo "size:       $DMG_BYTES bytes ($(du -h "$DMG" | cut -f1))"
echo "sha256:     $DMG_SHA"
echo "version:    $VERSION (build $BUILD_NUMBER)"
[ -n "$NOTARY_ID" ] && echo "notary id:  $NOTARY_ID"
[ "$SWIFT_UNIVERSAL" -eq 1 ] || warn_loud "Swift executable is host-only ($(uname -m)), not universal."
[ "$UNSIGNED" -eq 1 ] && warn_loud "UNSIGNED (ad-hoc) build: for local testing only, do not distribute."
[ "$UNSIGNED" -eq 0 ] && [ "$SKIP_NOTARIZE" -eq 1 ] && warn_loud "NOT notarized (--skip-notarize): do not distribute."
CURRENT_STEP="done"
exit 0
