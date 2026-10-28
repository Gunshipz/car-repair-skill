# Garage server (optional)

Everything here is optional. The skill works without a server. These parts run on any small Linux box with
Docker and systemd:

- **MyGarage** (https://github.com/homelabforge/mygarage, MIT): a self-hosted vehicle app. This skill uses only
  its LiveLink feature: live OBD data from a WiCAN dongle (https://github.com/meatpiHQ/wican-fw). `carkit garage`
  reads drives and telemetry from it.
- **The yard watch**: `carkit yard watch` every 6 hours by systemd. It sends a Telegram message when a car you're
  watching arrives at a Utah self-pull yard.

Everything lives in `/home/USER/garage/`, except the two units in `/etc/systemd/system/`.

## Install

1. Run `server/deploy.sh --host IP --user USER [--key FILE]` from your PC. It copies the files with tar over ssh,
   because rsync isn't needed, and installs the units with your user filled in. It doesn't start anything.
2. On the server, create `~/garage/.env` (mode 600) with `TELEGRAM_BOT_TOKEN=` and `TELEGRAM_CHAT_ID=`.
3. Start it with `cd ~/garage && docker compose up -d`. Then open `http://IP:8686`, create the admin user, set
   Settings → System → auth mode to local, turn on LiveLink, and create a LiveLink token.
4. On your PC, write `~/.config/carkit/config.json` with `mygarage_url`, `mygarage_user`, `mygarage_password`
   and `wican_token`. Keep this file private.
5. Check it with `python -I server/ingest_check.py`. It creates a test car and a fake WiCAN, posts data the way a
   WiCAN does, reads the value back, and deletes both. A bare HTTP 202 proves nothing, because MyGarage answers
   202 even when it drops the data.
6. Edit `~/garage/yard/watchlist.json` and run `sudo systemctl start garage-yard.service` once. Read
   `journalctl -u garage-yard.service`. When the first run looks right, run
   `sudo systemctl enable --now garage-yard.timer`.

## Things that aren't obvious

- **The WiCAN webhook URL** is `http://IP:8686/api/v1/livelink/ingest`. A new device must send a status message
  first, and its telemetry is stored only after the device is linked to a VIN.
- **A MyGarage "session" is a drive,** built from movement. An idling car never opens one, so pull idle data by
  time window.
- **Stock WiCAN firmware doesn't send trouble codes to MyGarage,** so an empty code list there means nothing.
- **Pull N Save isn't watched,** because it serves a bot challenge to scripts.
- **To move to another host,** stop compose and the timer, then copy `~/garage` with
  `ssh old 'tar -C ~ -cf - garage' | ssh new 'tar -C ~ -xf -'`. Run `deploy.sh` for the new host, start it, and
  change the WiCAN's webhook URL.
