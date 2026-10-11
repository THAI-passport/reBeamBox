"""Per-model profiles for the NN family. See docs/models.md for the evidence behind each field."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    key: str
    marketing: str
    names: tuple            # extra BLE name filters (substring, case/punctuation insensitive)
    video_max_s: float      # default cap for GIF and video
    size: int               # default picture edge in pixels (BLE)
    still_mode: str         # nn20 still encoding: "gif" (type 5, one-frame container) or "album" (type 6, IMB)
    notes: str = ""


# "E-badge" is the name seen advertising on a Niji and a Nano in pairing mode (third-party reports).
COMMON_NAMES = ("E-badge",)

PROFILES = {
    "nikko": Profile("nikko", "NIKKO (Beambox e-Badge Pulse), flagship", ("Nikko",) + COMMON_NAMES, 3.0, 368, "gif",
                     "retail data: 3 s video; app code allows 10 s"),
    "nano": Profile("nano", "NANO (Lite), essential", ("Nano",) + COMMON_NAMES, 3.0, 368, "gif",
                    "same cap as nikko (assumption); app code allows 10 s"),
    "niji": Profile("niji", "NIJI, 1.53 inch touch", ("Niji",) + COMMON_NAMES, 5.0, 368, "gif",
                    "app trimmer caps video at 5 s for NIJI (confirmed in code)"),
}


def get(key):
    return PROFILES.get((key or "").lower())
