# E-Ink Dashboard

This Home Assistant addon drives a drives a [Waveshare 2.7" e-Paper HAT](https://www.amazon.com/dp/B075FQKSZ9) 
attached to a Raspberry Pi 4B that runs Home Assistant OS.

The dashboard shows the current time and date, along with a countdown to the next sunrise/sunset. Pressing 
one of the 4 buttons on the display will change the view. After 18s of no input, it returns to the default 
view.

The views are:

| Button | View | Content |
|---|---|---|
| *(idle)* | **Clock** | Big time, date, sunrise/sunset countdown |
| 1 | **Main** | Time, uptime, current weather, count of pending `update.*` entities |
| 2 | **Messages** | Active persistent notifications + open HA "Repairs" issues |
| 3 | **Diagnostics** | CPU temp/load/mem/disk, Core + Supervisor versions, add-on health |
| 4 | *(undefined)* | Placeholder view ("coming soon"). |

The pictured unit is mounted in one of [these](https://www.amazon.com/dp/B09QG349ZL) mini towers, which allows 
access to the GPIO pins via 90 degree headers.

## Requirements & Notes

This code is tested on:

* Raspberry Pi 4B (8GB)
* Home Assistant OS 18.3
* Core 2026.9.4
* Supervisor 2026.09.3
* Waveshare 2.7" e-Paper HAT V1

The code is pretty straightforward and probably insensitive to changes to Home Assistant itself. It is, however, 
written to target V1 of the Waveshare HAT. This variant is older, and doesn't support partial refreshes, so 
every update to the screen makes it turn all black, then all white, then load the content. **This is not a bug.**

The same code and libraries should work on the current V2 of the display, which _does_ support partial refreshes,
so updating the display doesn't run through the black-white cycle. I just haven't tested it.

The display requires SPI be enabled on the Pi. This isn't enabled by default in HAOS; you need to get a root 
shell and enable that manually.

## Installation

The overall process is pretty simple:

1. Power down the Pi
2. Connect the display to your Pi
3. Ensure that SPI is enabled on your Pi ([jump to instructions](#enabling-spi))
4. In the Home Assistant dashboard:
    - Navigate to Settings → Apps → Install App.
    - Click on the ⋮ and select Repositories.
    - Click Add.
    - Enter `https://github.com/robsears/haos-eink-hat`.


### Enabling SPI

You'll need a spare USB drive (any size) and a machine to format it on.

1. Format the USB drive with a partition **labeled `CONFIG`** (exact,
   case-sensitive), filesystem FAT/ext4/NTFS.

```sh
lsblk # figure out the device path for the USB device; ex: /dev/sdX
sudo umount /dev/sdX*
sudo parted /dev/sdX --script -- mklabel msdos mkpart primary fat32 1MiB 100%
sudo mkfs.vfat -n CONFIG /dev/sdX1
lsblk -f /dev/sdX1 # Verify the label
mkdir -p /tmp/config-usb # create a temporary mountpoint
sudo mount /dev/sdX1 /tmp/config-usb # mount the USB to the temp mountpoint
```

2. Create a plain-text file named exactly `authorized_keys` (no extension) 
   containing your SSH *public* key, one per line. It must use
   LF line endings, not CRLF — if you edit it on Windows/macOS, double check.
   If you don't already have a keypair: `ssh-keygen -t ed25519` on your dev
   machine, then use the `.pub` file's contents.

```sh
# if you don't already have an SSH key:
mkdir -p ~/.ssh && ssh-keygen -t ed25519 -f ~/.ssh/haos_debug -N ""

# write ssh public key out to `authorized_keys`:
cat ~/.ssh/<your-ssh-key>.pub | sudo tee /tmp/config-usb/authorized_keys

# unmount the drive
sudo umount /tmp/config-usb
```

3. Insert the USB drive into the Pi.
4. Boot the Pi with the drive inserted (or Settings → System → ⋮ → Reboot
   Host), or, if you already have any SSH access, run `ha os import` to pick
   it up without a reboot.

You should now be able to SSH into the Pi and get a root shell with:

```sh
ssh root@<your-pi-hostname-or-ip>.local -p 22222
```

using the private key matching what you put on the USB drive. Confirm:

```sh
cat /etc/os-release   # should say Home Assistant OS
```

(If this instead says `Alpine Linux`, you're still in a container
somewhere — you skipped `login`, or you're connected to the wrong thing.)

You can edit `/mnt/boot/config.txt` directly with `vi`, or use a one-liner to 
append the SPI param to the end of the file:

```sh
grep -q '^dtparam=spi=on' /mnt/boot/config.txt || echo 'dtparam=spi=on' >> /mnt/boot/config.txt
```

Once that change is made, sync the writes and reboot:

```sh
sync
reboot
```

Once the Pi comes back online, reconnect via SSH with:

```sh
ssh root@<your-pi-hostname-or-ip>.local -p 22222
```

Back in the root shell, check that the SPI and GPIO devices are initialized:

```sh
ls /dev/spidev*     # -> /dev/spidev0.0  /dev/spidev0.1
ls /dev/gpiochip*   # -> /dev/gpiochip0 (and maybe others)
```

On a **Pi 4** this should be `gpiochip0` — the RP1-southbridge chip
renumbering that puts header GPIOs on `gpiochip4` is a Pi 5 thing, not
relevant here. `gpiochip0` is what's already hardcoded in
`addon/eink_dashboard/app/buttons.py` (`GPIO_CHIP_PATH`) and
`app/waveshare_epd/epdconfig.py`, and assumed by `config.yaml`'s `devices:`
list — if your `ls` shows something else, update all three.

If `/dev/spidev0.0` doesn't show up after reboot, double-check the line
actually made it into the *live* `config.txt`

Once all of this has been completed, you'll want to turn off the root access.

From inside a root shell session, with the USB stick still attached:

```sh
mkdir /tmp/usb
mount /dev/sdX1 /tmp/usb # replace sdX1 with whatever device is correct for your USB stick
rm /tmp/usb/authorized_keys
reboot now
```

This drops the authorized keys from the USB and reboots the Pi. When it comes 
back online, you should no longer be able to SSH in as root:

```sh
ssh root@<your-pi-hostname-or-ip>.local -p 22222
ssh: connect to host <your-pi-hostname-or-ip>.local port 22222: Connection refused
```