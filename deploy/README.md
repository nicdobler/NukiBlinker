# Mini PC Deployment

## First-time install

```sh
# On the mini PC:
git clone https://github.com/nicdobler/NukiBlinker.git ~/nukiblinker
cd ~/nukiblinker
bash deploy/install.sh
```

Then edit `~/nukiblinker/config.yaml` (bridge IPs, settings) and `~/nukiblinker/secrets.yaml` (Nuki/Hue tokens — kept separate so UI saves can't wipe them, #123) with your actual values and restart:

```sh
docker compose restart
```

## Auto-start on boot (systemd)

```sh
sudo cp ~/nukiblinker/deploy/nukiblinker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nukiblinker
```

## Update

```sh
bash ~/nukiblinker/deploy/update.sh
```

## Useful commands

| Command | Description |
|---|---|
| `docker compose logs -f` | Follow live logs |
| `docker compose restart` | Restart after config change |
| `docker compose down` | Stop |
| `docker compose up -d` | Start |
| `curl localhost:8080/health` | Health check |

## Config checklist

Before starting, you need:

1. **Nuki Bridge** — IP + API token (Nuki app → Bridge → Manage → Enable API)
2. **Hue Bridge** — IP + API key (press link button, then pair via web UI or curl)
3. **Light IDs** — which Hue lights to blink (find via web UI discover or `curl http://<hue-ip>/api/<key>/lights`)
4. **Speaker names** (optional) — Google Nest names as they appear on the network
