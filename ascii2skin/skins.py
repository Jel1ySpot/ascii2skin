"""The 29 skin/weapon pairs used by the original `skin secret` challenge.

The order matters: position *i* of the input string uses ``DEFAULT_SKINS[i]``.
For inputs longer than 29 characters the list wraps around.
"""

from __future__ import annotations

from dataclasses import dataclass

# Native (un-cropped) preview size on pattern.wiki and the crop used by the
# challenge author (the bottom strip holds the pattern.wiki watermark).
MODEL_SIZES = {
    "cs2": {"native": (1920, 1440), "cropped": (1920, 1296)},
    "csgo": {"native": (1000, 750), "cropped": (1000, 649)},
}


@dataclass(frozen=True)
class Skin:
    pattern_id: str
    weapon_id: str
    name: str
    model: str = "cs2"

    @property
    def key(self) -> str:
        """Stable directory name used by the reference-image cache."""
        return f"{self.pattern_id}__{self.weapon_id}"

    @property
    def cropped_size(self) -> tuple[int, int]:
        return MODEL_SIZES[self.model]["cropped"]

    @property
    def native_size(self) -> tuple[int, int]:
        return MODEL_SIZES[self.model]["native"]


# Order copied from the solved challenge (image 1 .. image 29).
DEFAULT_SKINS: tuple[Skin, ...] = (
    Skin("aq_oiled", "weapon_ak47", "AK-47 | Case Hardened", "cs2"),
    Skin("am_kimono_sunrise", "weapon_m4a1", "M4A4 | Daybreak", "csgo"),
    Skin("soch_mountains_m4a1s", "weapon_m4a1_silencer", "M4A1-S | Solitude", "cs2"),
    Skin("am_awp_pawpaw", "weapon_awp", "AWP | Pawpaw", "csgo"),
    Skin("hye_earth_mandala_lc", "weapon_taser", "Zeus x27 | Earth Mandala", "cs2"),
    Skin("aa_fade", "weapon_glock", "Glock-18 | Fade", "cs2"),
    Skin("soe_roses", "weapon_glock", "Glock-18 | Coral Bloom", "cs2"),
    Skin("aq_deagle_case_hardened_2", "weapon_deagle", "Desert Eagle | Heat Treated", "cs2"),
    Skin("hy_marina_sunrise", "weapon_elite", "Dual Berettas | Marina", "csgo"),
    Skin("aa_fade_red_blue", "weapon_fiveseven", "Five-SeveN | Blueberry Cherry", "cs2"),
    Skin("am_tec_9_sea_salt", "weapon_tec9", "Tec-9 | Sea Salt", "csgo"),
    Skin("spe_scarf_print", "weapon_hkp2000", "P2000 | Royal Baroque", "cs2"),
    Skin("hye_pink_coral", "weapon_p250", "P250 | Red Tide", "cs2"),
    Skin("soe_purple", "weapon_usp_silencer", "USP-S | Sleeping Beauty", "cs2"),
    Skin("hye_zeds", "weapon_ak47", "AK-47 | Breakthrough", "cs2"),
    Skin("sp_nukestripe_orange_aug", "weapon_aug", "AUG | Radiation Hazard", "csgo"),
    Skin("am_nuclear_skulls2_famas", "weapon_famas", "FAMAS | Underworld", "csgo"),
    Skin("aq_titanium_rainbow_galilar", "weapon_galilar", "Galil AR | Rainbow Spoon", "cs2"),
    Skin("am_kimono_sunrise", "weapon_m4a1", "M4A4 | Daybreak", "csgo"),
    Skin("cu_sg553_pulse", "weapon_sg556", "SG 553 | Pulse", "csgo"),
    Skin("hye_animal_print_90s", "weapon_m4a1_silencer", "M4A1-S | Nightclubbing", "cs2"),
    Skin("hy_technowar_rwb", "weapon_awp", "AWP | Pop Art", "csgo"),
    Skin("hy_arctic_contrast", "weapon_g3sg1", "G3SG1 | Arctic Camo", "csgo"),
    Skin("hy_webs_darker", "weapon_scar20", "SCAR-20 | Crimson Web", "csgo"),
    Skin("am_intelligence_orange", "weapon_ssg08", "SSG 08 | Detection", "csgo"),
    Skin("aa_mp9_fuji_pink", "weapon_mp9", "MP9 | Fuji", "csgo"),
    Skin("mp7_amberline", "weapon_mp7", "MP7 | Amberline", "cs2"),
    Skin("cu_catskulls_p90", "weapon_p90", "P90 | Cat Skulls", "csgo"),
    Skin("hye_geobirds_sunrise", "weapon_bizon", "PP-Bizon | Thermal Current", "cs2"),
)

SKINS_BY_KEY = {s.key: s for s in DEFAULT_SKINS}
