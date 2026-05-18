"""Constants for the Epson LS12000 integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "epson_ls12000"
MANUFACTURER: Final = "Epson"
MODEL: Final = "LS12000"

CONF_PJLINK_PORT: Final = "pjlink_port"
CONF_PJLINK_PASSWORD: Final = "pjlink_password"
CONF_ESCVP_PORT: Final = "escvp_port"
CONF_ESCVP_PASSWORD: Final = "escvp_password"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_PJLINK_PORT: Final = 4352
DEFAULT_ESCVP_PORT: Final = 3629
DEFAULT_SCAN_INTERVAL: Final = 15

# Default per-command timeout. PWR ON/OFF require longer; coordinator overrides.
ESCVP_TIMEOUT: Final = 5.0
PJLINK_TIMEOUT: Final = 5.0

# PWR? response codes (ESC/VP21 §4.1 / LS12000 sheet row 18)
PWR_STATE = {
    "00": "standby",
    "01": "on",
    "02": "warmup",
    "03": "cooldown",
    "04": "network_standby",
    "05": "abnormal",
}

# SOURCE codes for the LS12000. Sheet only lists HDMI1=30 as "OK";
# HDMI2=A0 is the documented value on other modern Epson home models —
# leave it in the map but expect ERR on firmware that doesn't accept it.
SOURCE_TO_CODE = {
    "HDMI1": "30",
    "HDMI2": "A0",
}
CODE_TO_SOURCE = {v: k for k, v in SOURCE_TO_CODE.items()}

# CMODE (LS12000 sheet row 162)
CMODE_TO_CODE = {
    "Dynamic": "06",
    "Natural": "07",
    "Bright Cinema": "0C",
    "Cinema": "15",
    "Vivid": "23",
    # "B&W Cinema": "20",  # LS12000B (EAI) only — uncomment if applicable
}
CODE_TO_CMODE = {v: k for k, v in CMODE_TO_CODE.items()}

# ASPECT (LS12000 sheet row 62)
ASPECT_TO_CODE = {
    "Auto": "30",
    "Full": "40",
    "Zoom": "50",
    "Native": "60",
    "Anamorphic Wide": "80",
    "Horiz. Squeeze": "90",
}
CODE_TO_ASPECT = {v: k for k, v in ASPECT_TO_CODE.items()}

# DYNRANGE (LS12000 sheet row 277)
DYNRANGE_TO_CODE = {
    "Auto": "00",
    "SDR": "01",
    "HDR10": "21",
    "HLG": "30",
}
CODE_TO_DYNRANGE = {v: k for k, v in DYNRANGE_TO_CODE.items()}

# CLRSPACE (LS12000 sheet row 274)
CLRSPACE_TO_CODE = {
    "Auto": "00",
    "BT.709": "01",
    "BT.2020": "02",
}
CODE_TO_CLRSPACE = {v: k for k, v in CLRSPACE_TO_CODE.items()}

# MCFI frame interpolation (LS12000 sheet row 271)
MCFI_TO_CODE = {
    "Off": "00",
    "Low": "01",
    "Normal": "02",
    "High": "03",
}
CODE_TO_MCFI = {v: k for k, v in MCFI_TO_CODE.items()}

# IMGPRESET (LS12000 sheet row 248)
PRESET_TO_CODE = {
    "Off": "00",
    "Preset 1": "01",
    "Preset 2": "02",
    "Preset 3": "03",
    "Preset 4": "04",
    "Preset 5": "05",
}
CODE_TO_PRESET = {v: k for k, v in PRESET_TO_CODE.items()}

# Remote KEY codes from the LS12000 sheet (Operation tab, "OK" rows only)
KEY_CODES = {
    "power": "01",
    "menu": "03",
    "esc": "05",
    "enter": "16",
    "up": "35",
    "down": "36",
    "left": "37",
    "right": "38",
    "source": "48",
}

# ERR? codes (ESC/VP21 §5) — only the ones relevant to the LS12000
ERR_CODES = {
    "00": "OK",
    "01": "Fan error",
    "03": "Lamp failure at power on",
    "04": "High internal temperature",
    "06": "Lamp error",
    "0C": "Low air flow",
    "0D": "Air filter sensor",
    "0E": "Power supply (ballast)",
    "10": "Cooling system (Peltier)",
    "11": "Cooling system (pump)",
    "1A": "Lens shift",
    "1C": "No lens",
    "1E": "Power supply voltage",
    "1F": "Other error",
}
