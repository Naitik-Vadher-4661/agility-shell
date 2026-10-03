import os
import re
import threading
import urllib.request
import urllib.parse
import subprocess
from loguru import logger

import gi
gi.require_version("PangoCairo", "1.0")
from gi.repository import GLib, PangoCairo

from services.paths import get_user_config_dir, get_search_data_dirs, get_repo_dir

FONTS_CACHE_DIR = os.path.expanduser("~/.local/share/fonts/agility-shell")


def init_installed_fonts() -> None:
    """Registers all previously downloaded Agility Shell fonts with PangoCairo."""
    if not os.path.isdir(FONTS_CACHE_DIR):
        return

    try:
        fm = PangoCairo.font_map_get_default()
        loaded = 0
        for root, _, files in os.walk(FONTS_CACHE_DIR):
            for file in files:
                if file.lower().endswith((".ttf", ".otf")):
                    font_path = os.path.join(root, file)
                    try:
                        if fm.add_font_file(font_path):
                            loaded += 1
                    except Exception:
                        pass
        if loaded > 0:
            fm.changed()
            logger.debug(f"[FontService] Initialized {loaded} local fonts into Pango font map")
    except Exception as e:
        logger.warning(f"[FontService] Could not initialize installed fonts: {e}")


def resolve_user_font_file() -> str | None:
    """
    Searches for a user font stylesheet in priority order:
    1. ~/.config/agility-shell/styles/font.css
    2. ~/.config/agility-shell/styles/fonts.css
    3. ~/.config/agility-shell/style/font.css
    4. ~/.config/agility-shell/style/fonts.css
    """
    user_config = get_user_config_dir()
    candidates = [
        os.path.join(user_config, "styles", "font.css"),
        os.path.join(user_config, "styles", "fonts.css"),
        os.path.join(user_config, "style", "font.css"),
        os.path.join(user_config, "style", "fonts.css"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def extract_google_font_families(url: str) -> list[str]:
    """Extracts font family names from a Google Fonts URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        families = []
        for item in qs.get("family", []):
            name = item.split(":")[0].replace("+", " ").strip()
            if name:
                families.append(name)
        return families
    except Exception as e:
        logger.error(f"[FontService] Error extracting family from URL {url}: {e}")
        return []


class FontService:
    def __init__(self):
        self._downloading_families: set[str] = set()
        self._installed_families: set[str] = set()
        os.makedirs(FONTS_CACHE_DIR, exist_ok=True)
        init_installed_fonts()

    def is_family_downloaded(self, family_name: str) -> bool:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", family_name.lower())
        target_dir = os.path.join(FONTS_CACHE_DIR, slug)
        if not os.path.isdir(target_dir):
            return False
        return any(f.endswith((".ttf", ".otf")) for f in os.listdir(target_dir))

    def ensure_font_downloaded(self, family_name: str, google_url: str, on_installed=None) -> None:
        if self.is_family_downloaded(family_name) or family_name in self._downloading_families:
            return

        self._downloading_families.add(family_name)
        logger.info(f"[FontService] Downloading custom Google font '{family_name}' in background...")

        def _worker():
            try:
                slug = re.sub(r"[^a-zA-Z0-9_-]", "_", family_name.lower())
                target_dir = os.path.join(FONTS_CACHE_DIR, slug)
                os.makedirs(target_dir, exist_ok=True)

                req = urllib.request.Request(
                    google_url,
                    headers={"User-Agent": "curl/7.68.0"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    css_data = resp.read().decode("utf-8", errors="replace")

                ttf_urls = re.findall(r"url\((https://[^\)]+\.ttf)\)", css_data)
                if not ttf_urls:
                    ttf_urls = re.findall(r"url\((https://fonts\.gstatic\.com/[^\)]+)\)", css_data)

                if not ttf_urls:
                    logger.warning(f"[FontService] No font binaries found for '{family_name}' at {google_url}")
                    return

                downloaded_paths = []
                for idx, f_url in enumerate(ttf_urls):
                    ext = os.path.splitext(f_url.split("?")[0])[1] or ".ttf"
                    local_file = os.path.join(target_dir, f"font_{idx}{ext}")
                    urllib.request.urlretrieve(f_url, local_file)
                    downloaded_paths.append(local_file)

                logger.info(f"[FontService] Downloaded {len(downloaded_paths)} font files for '{family_name}'")

                try:
                    subprocess.run(["fc-cache", "-f", os.path.expanduser("~/.local/share/fonts")], check=False)
                except Exception:
                    pass

                def _register_on_main():
                    try:
                        fm = PangoCairo.font_map_get_default()
                        for p in downloaded_paths:
                            try:
                                fm.add_font_file(p)
                            except Exception:
                                pass
                        fm.changed()
                        logger.info(f"[FontService] Successfully registered '{family_name}' in PangoCairo")
                    except Exception as err:
                        logger.error(f"[FontService] Failed to add font to Pango: {err}")

                    self._installed_families.add(family_name)
                    if on_installed:
                        on_installed()
                    return False

                GLib.idle_add(_register_on_main)

            except Exception as e:
                logger.error(f"[FontService] Error downloading font '{family_name}': {e}")
            finally:
                self._downloading_families.discard(family_name)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def get_compiled_font_css(self, on_installed=None) -> str:
        """
        Reads user font stylesheet (if present) or default fonts.css.
        If a Google Fonts import URL is detected, schedules background download,
        strips the remote HTTP import, and injects font variables and global font-family rules.
        """
        font_file = resolve_user_font_file()
        if not font_file:
            # Fall back to default repo fonts.css
            default_path = os.path.join(get_repo_dir(), "style", "fonts.css")
            if os.path.isfile(default_path):
                try:
                    with open(default_path, "r") as f:
                        return f.read()
                except Exception:
                    pass
            return "@define mixed-mono unset;\n@define always-mono unset;\n"

        try:
            with open(font_file, "r") as f:
                raw_content = f.read()
        except Exception as e:
            logger.error(f"[FontService] Error reading font file {font_file}: {e}")
            return "@define mixed-mono unset;\n@define always-mono unset;\n"

        # Match @import url("https://fonts.googleapis.com/...") or @import "https://..." or raw https://fonts.googleapis.com/...
        import_pattern = re.compile(r'@import\s+(?:url\()?["\']?(https://fonts\.googleapis\.com/[^"\')]+)["\']?\)?\s*;?')
        raw_url_pattern = re.compile(r'^\s*(https://fonts\.googleapis\.com/\S+)\s*$', re.MULTILINE)

        found_urls = import_pattern.findall(raw_content)
        found_urls.extend(raw_url_pattern.findall(raw_content))

        # Deduplicate while preserving order
        unique_urls = list(dict.fromkeys(found_urls))

        cleaned_content = import_pattern.sub("/* Google Font imported */", raw_content)
        cleaned_content = raw_url_pattern.sub("/* Google Font imported */", cleaned_content)

        if not unique_urls:
            return cleaned_content

        primary_family = None
        for u in unique_urls:
            families = extract_google_font_families(u)
            for fam in families:
                if not primary_family:
                    primary_family = fam
                self.ensure_font_downloaded(fam, u, on_installed=on_installed)

        injected_css = ""
        if primary_family:
            is_mono = any(term in primary_family.lower() for term in ["mono", "code", "console"])
            fallback = "monospace" if is_mono else "sans-serif"
            injected_css = (
                f"\n/* Auto-injected Agility Shell font definitions for '{primary_family}' */\n"
                f'@define mixed-mono "{primary_family}";\n'
                f'@define always-mono "{primary_family}";\n'
                f'* {{\n'
                f'    font-family: "{primary_family}", {fallback};\n'
                f'}}\n'
            )

        return injected_css + "\n" + cleaned_content


# Singleton instance
font_service = FontService()
