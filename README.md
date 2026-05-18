# Epson LS12000 — Home Assistant integration (authenticated)

Local-polling Home Assistant integration for the Epson Pro Cinema / Home
Cinema LS12000 4K laser projector. Unlike the popular HACS Epson
integrations, this one performs the **authenticated** handshakes for both
PJLink and ESC/VP.net, so it works on projectors that have a network
password set.

## What it does

| Surface          | Backed by                                 |
|------------------|-------------------------------------------|
| `media_player`   | Power, source (HDMI1/HDMI2), color mode   |
| `remote`         | Raw `KEY xx` codes + arbitrary ESC/VP21   |
| `select`         | Color Mode, Aspect, Dynamic Range, Color Space, Frame Interpolation, Image Preset |
| `number`         | Light Output (LUMLEVEL)                   |
| `button`         | Recall Image Memory 1–5 (`POPMEM 02 0x`)  |

## Protocols

- **PJLink** (TCP 4352) — MD5 challenge-response per the JBMIA spec. Used
  to verify power state when ESC/VP21 is unavailable.
- **ESC/VP.net** (TCP 3629) — `CONNECT` handshake with the optional
  `Password` header (plain text, 16-byte STR). Once the projector returns
  status `0x20 OK`, the same socket carries ASCII ESC/VP21 commands. The
  client keeps the socket warm with a `\r` keepalive every 4 minutes to
  avoid the 10-minute idle cutoff documented in the ESC/VP.net manual §5.6.

## Install (HACS, private repo)

1. `git init` this folder, push to a private GitHub repo, push.
2. In Home Assistant: **HACS → Integrations → ⋮ → Custom repositories**.
   Add your repo URL, category **Integration**.
3. **Download** "Epson LS12000 (authenticated)". Restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Epson LS12000**.
   Enter:
    - IP / hostname
    - PJLink password (leave blank if PJLink is unprotected)
    - ESC/VP.net password (the projector's **Web Control** password)

## Install (no HACS)

Copy `custom_components/epson_ls12000/` into your Home Assistant
`/config/custom_components/` directory and restart.

## Projector setup checklist

In the projector's network menu, make sure:

- **Standby Mode** is set to **Communication On** (otherwise the
  projector is unreachable in standby and Home Assistant won't be able to
  power it on).
- **PJLink** is enabled; if you set a PJLink password, enter the same one
  in the integration.
- **Network Control** (the ESC/VP.net listener on port 3629) is enabled.
- **Web Control Password** — this is the password the ESC/VP.net
  `CONNECT` handshake uses. Up to 16 ASCII characters.

## Limitations

- LS12000 firmware ignores most picture-setting commands when the
  projector's "Operation Password" mode is enabled — only PWR, ZOOM,
  FOCUS, LENS, HLENS, DISTORTION and LENSADJMODE accept commands in that
  mode. The integration's `select`/`number` entities will fail silently
  with `ERR` until you disable Operation Password mode on the projector.
- `B&W Cinema` color mode is only present on the LS12000B (EAI / Japan
  retail variant); it's commented out in `const.py`.
- Source switching codes are firmware-dependent. HDMI1 is `SOURCE 30`
  per the official command list; HDMI2 is sent as `SOURCE A0` based on
  the convention used by other modern Epson home projectors. If HDMI2
  doesn't work for you, file an issue with the value you confirmed
  works via the projector's web debug page.

## Credits

Based on Seiko Epson's published *ESC/VP21 Command User's Guide* (Rev C),
*ESC/VP21 Command List* (Rev S), and *ESC/VP.net Software Development
Manual* (Rev F). Not affiliated with Seiko Epson Corporation.
