#!/usr/bin/env bash
# Build the complete Linux release from this checkout and the sibling ATVVoice checkout.
set -euo pipefail
umask 022
here="$(cd "$(dirname "$0")" && pwd)"
version="${1:-1.1.1-1}"
atvvoice_source="${ATVVOICE_SOURCE:-$here/../../ATVVoice}"
output="$here/../dist/linux"
dpkg --validate-version "$version"

cargo build --manifest-path "$atvvoice_source/Cargo.toml" --target-dir "$atvvoice_source/target" --release --locked
binary="$atvvoice_source/target/release/atvvoice"
atvvoice_version="$(/usr/bin/python3 -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["package"]["version"])' "$atvvoice_source/Cargo.toml")"
arch="$(dpkg --print-architecture)"
stage="$(mktemp -d)"
trap 'command rm -rf "$stage"' EXIT
root="$stage/package"
mkdir -p "$root/DEBIAN" "$output" "$stage/debian"

install -Dm755 "$binary" "$root/usr/bin/atvvoice"
strip "$root/usr/bin/atvvoice"
for source in vremoter_gui.py vremoter_linux.py; do
    install -Dm644 "$here/$source" "$root/usr/lib/vremoter/$source"
done
install -Dm755 "$here/debian/setup.py" "$root/usr/bin/vremoter-setup"
install -Dm755 "$here/debian/vremoter-gui" "$root/usr/bin/vremoter-gui"
install -Dm755 "$here/pair-remote.sh" "$root/usr/bin/vremoter-pair"
install -Dm644 "$here/config.example.toml" "$root/usr/share/vremoter/config.example.toml"
install -Dm644 "$here/vremoter-linux.service" "$root/usr/share/vremoter/legacy-vremoter-linux.service"
install -Dm644 "$here/vremoter-gui.desktop" "$root/usr/share/vremoter/legacy-vremoter-gui.desktop"
install -Dm644 "$here/debian/atvvoice.service" "$root/usr/lib/systemd/user/atvvoice.service"
sed 's|%h/.local/lib/vremoter/|/usr/lib/vremoter/|' "$here/vremoter-linux.service" > "$stage/vremoter-linux.service"
install -Dm644 "$stage/vremoter-linux.service" "$root/usr/lib/systemd/user/vremoter-linux.service"
mkdir -p "$root/usr/lib/systemd/user/default.target.wants"
for unit in atvvoice vremoter-linux; do
    ln -s "../$unit.service" "$root/usr/lib/systemd/user/default.target.wants/$unit.service"
done
install -Dm644 "$here/debian/vremoter-gui.desktop" "$root/usr/share/applications/vremoter-gui.desktop"
install -Dm644 "$here/debian/vremoter-autostart.desktop" "$root/etc/xdg/autostart/vremoter-autostart.desktop"
install -Dm644 "$here/debian/70-vremoter.rules" "$root/usr/lib/udev/rules.d/70-vremoter.rules"
mkdir -p "$root/usr/lib/modules-load.d"
echo uinput > "$root/usr/lib/modules-load.d/vremoter.conf"
install -Dm644 "$here/../Resources/RemoteImages/chromecast-voice-remote.png" "$root/usr/lib/vremoter/assets/chromecast-voice-remote.png"
icon="$here/../Design/vRemoter-Logo-v1/vRemoter-app-icon-v9.png"
install -Dm644 "$icon" "$root/usr/lib/vremoter/assets/vRemoter-app-icon-v9.png"
install -Dm644 "$icon" "$root/usr/share/icons/hicolor/512x512/apps/vremoter.png"
install -Dm644 "$here/../LICENSE" "$root/usr/share/doc/vremoter/copyright"
install -Dm644 "$atvvoice_source/LICENSE" "$root/usr/share/doc/vremoter/ATVVoice-LICENSE"
install -Dm644 "$here/debian/RELEASE.md" "$root/usr/share/doc/vremoter/RELEASE.md"
cat > "$stage/changelog.Debian" <<EOF
vremoter ($version) unstable; urgency=medium

  * Bundle the Linux console, ATVVoice, user services, desktop launchers,
    pairing helper, configuration migration and device access rules.

 -- longqi <longqi90@gmail.com>  $(date -R)
EOF
gzip -n -9 -c "$stage/changelog.Debian" > "$root/usr/share/doc/vremoter/changelog.Debian.gz"
for script in postinst prerm postrm; do
    install -m755 "$here/debian/$script" "$root/DEBIAN/$script"
done

# Use the build system's library metadata rather than guessing a compatible glibc version.
cat > "$stage/debian/control" <<EOF
Source: vremoter
Section: sound
Priority: optional
Maintainer: longqi <longqi90@gmail.com>

Package: vremoter
Architecture: $arch
Description: Chromecast Voice Remote console, key mapper and microphone
EOF
libs="$(cd "$stage" && dpkg-shlibdeps -O -e"$root/usr/bin/atvvoice" | sed -n 's/^shlibs:Depends=//p')"
test -n "$libs"
cat > "$root/DEBIAN/control" <<EOF
Package: vremoter
Version: $version
Architecture: $arch
Section: sound
Priority: optional
Maintainer: longqi <longqi90@gmail.com>
Installed-Size: $(du -sk "$root/usr" "$root/etc" | awk '{sum += $1} END {print sum}')
Depends: $libs, python3 (>= 3.11), python3-evdev, python3-dbus, python3-gi, python3-pyqt6, qt6-wayland, bluez, pipewire, pipewire-bin, pipewire-pulse, pulseaudio-utils, wireplumber, systemd (>= 249), init-system-helpers (>= 1.64), udev, kmod
Provides: atvvoice (= $atvvoice_version)
Conflicts: atvvoice
Replaces: atvvoice
Description: Chromecast Voice Remote console, key mapper and microphone
 Includes the vRemoter Linux GUI, button mapping and voice hooks, the
 vRemoter-compatible ATVVoice daemon, systemd user services, desktop
 launchers, pairing tool and active-session device access rules.
EOF
echo /etc/xdg/autostart/vremoter-autostart.desktop > "$root/DEBIAN/conffiles"
(
    cd "$root"
    find usr etc -type f -print0 | sort -z | xargs -0 md5sum > DEBIAN/md5sums
)
package="$output/vremoter_${version}_${arch}.deb"
dpkg-deb --root-owner-group --build "$root" "$package"
cp "$here/debian/RELEASE.md" "$output/RELEASE.md"
{
    echo "vRemoter: $(git -C "$here/.." rev-parse HEAD) (plus working-tree packaging changes)"
    echo "ATVVoice: $(git -C "$atvvoice_source" rev-parse HEAD)"
    echo "Architecture: $arch"
    echo "Library dependencies: $libs"
    echo "ATVVoice version: $atvvoice_version"
} > "$output/vremoter_${version}_${arch}.build-info.txt"
chmod 644 "$output/RELEASE.md" "$output/vremoter_${version}_${arch}.build-info.txt"
(
    cd "$output"
    sha256sum "$(basename "$package")" "vremoter_${version}_${arch}.build-info.txt" RELEASE.md > "vremoter_${version}_${arch}.sha256"
)
echo "Release: $package"
