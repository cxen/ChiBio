# Making a golden Chi.Bio image

Goal: flash the blessed Chi.Bio image **once**, apply the fixes, then capture a
snapshot you can restore forever after. This removes the dependency on EOL
Debian apt repos at provisioning time and preserves the kernel/device-tree
patches (they live inside the image, so a restore keeps them automatically).

> Do **not** substitute a newer mainline BeagleBone image — see `TODO.md` (P2).
> The I2C-bus / watchdog-GPIO / PWM kernel patches are baked into the Chi.Bio
> Debian 10.5 / 4.19 image and are not a portable patch set.

## 1. Build a known-good device (once)

1. Flash the latest Chi.Bio image to an SD card (Etcher / `dd`) and boot the BBB.
2. Run the modified `setup.sh` (it now repoints apt to `archive.debian.org`
   before installing — see that file). Confirm the app starts via `cb.sh` and
   that all reactors are detected.

## 2. Capture the snapshot

Easiest path — image the card from another machine (no extra tooling on the BBB):

```sh
# Shut the BBB down, move the SD card to a Linux/macOS reader, find the device:
#   Linux:  lsblk        (e.g. /dev/sdX)
#   macOS:  diskutil list (e.g. /dev/diskN — then use /dev/rdiskN for speed)
sudo dd if=/dev/sdX of=chibio-golden.img bs=4M status=progress
```

This captures the full system including the kernel mods. If you provisioned the
**eMMC** instead of an SD card, either pull an image of the eMMC the same way
from a USB-booted session, or use the rcn-ee eMMC flasher flow below.

## 3. (Optional) shrink the image

A raw `dd` image is the full card size. Shrink it so it flashes fast and fits
smaller cards:

```sh
# https://github.com/Drewsif/PiShrink
sudo pishrink.sh -z chibio-golden.img    # -z also gzips it
```

## 4. Restore to a new device

```sh
# With Etcher: select chibio-golden.img(.gz) -> target SD -> Flash.
# Or by hand:
sudo dd if=chibio-golden.img of=/dev/sdX bs=4M status=progress && sync
```

Boot it — the device is ready, with no apt/network step required.

## Notes

- **eMMC flasher (alternative to dd):** rcn-ee images ship
  `/opt/scripts/tools/eMMC/` and an eMMC-flasher service. Booting an SD whose
  `/boot/uEnv.txt` has the `init-eMMC-flasher-*` `cmdline=` line uncommented
  will clone the SD onto the eMMC on next boot. Useful for mass-provisioning,
  but plain `dd` capture/restore is simpler for keeping one golden image.
- **SSH host keys:** every device restored from the image shares the same host
  keys. Fine on the isolated USB-gadget network Chi.Bio uses; regenerate with
  `sudo rm /etc/ssh/ssh_host_* && sudo dpkg-reconfigure openssh-server` if you
  ever put devices on a shared network.
- **Re-capture after changes:** treat the golden image as the source of truth —
  when you change the app or OS config on the reference device, re-snapshot.
