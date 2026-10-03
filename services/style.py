import os
import re
from fabric.core.service import Service, Property
from fabric.utils import monitor_file
from gi.repository import GLib
from loguru import logger
from plugin_loader import apply_plugin_css
from services.paths import get_user_config_dir, get_repo_dir, resolve_style_file, get_user_style_dirs, get_user_style_dir
from services.fonts import font_service


def compile_border_css(content: str) -> str:
    """Compiles custom border CSS, supporting CSS variable syntax like --radius-m: 12px;"""
    var_matches = re.findall(r'--([a-zA-Z0-9_-]+)\s*:\s*([^;]+);', content)
    added = []
    existing = set(re.findall(r'@define\s+([a-zA-Z0-9_-]+)', content))
    for k, v in var_matches:
        if k not in existing and (k.startswith('radius') or 'radius' in k):
            added.append(f"@define {k} {v.strip()};")
    if added:
        return "\n".join(added) + "\n" + content
    return content


def compile_color_css(content: str) -> str:
    """Compiles custom color CSS, supporting CSS variable syntax like --primary: #...;"""
    var_matches = re.findall(r'--([a-zA-Z0-9_-]+)\s*:\s*([^;]+);', content)
    added = []
    existing = set(re.findall(r'@define-color\s+([a-zA-Z0-9_-]+)', content))
    for k, v in var_matches:
        if k not in existing and not k.startswith('radius'):
            added.append(f"@define-color {k} {v.strip()};")
    if added:
        return "\n".join(added) + "\n" + content
    return content


def compile_resolved_stylesheet(reload_callback=None) -> str | None:
    """
    Loads style.css and resolves every @import "<file>" with resolve_style_file(fname),
    ensuring user overrides in ~/.config/agility-shell/custom_style/ (such as user borders.css,
    colors.css, fonts.css) take precedence over static repo defaults.
    Also compiles user font definitions (including automatic Google Fonts download & registration)
    and appends custom.css if present in the user style directory.
    """
    target_style = resolve_style_file("style.css")
    if not os.path.isfile(target_style):
        return None

    try:
        with open(target_style, "r") as f:
            content = f.read()

        def _replace_import(match: re.Match) -> str:
            fname = match.group(1).strip()
            if fname in ("fonts.css", "font.css"):
                compiled_fonts = font_service.get_compiled_font_css(on_installed=reload_callback)
                return f"\n/* --- Font Definitions --- */\n{compiled_fonts}\n"

            if fname in ("borders.css", "border.css"):
                resolved = resolve_style_file(fname)
                if os.path.isfile(resolved):
                    try:
                        with open(resolved, "r") as bf:
                            compiled_border = compile_border_css(bf.read())
                        return f"\n/* --- Border Definitions --- */\n{compiled_border}\n"
                    except Exception as be:
                        logger.warning(f"[StyleService] Error reading border file {resolved}: {be}")
                return match.group(0)

            if fname in ("colors.css", "color.css"):
                resolved = resolve_style_file(fname)
                if os.path.isfile(resolved):
                    try:
                        with open(resolved, "r") as cf:
                            compiled_color = compile_color_css(cf.read())
                        return f"\n/* --- Color Definitions --- */\n{compiled_color}\n"
                    except Exception as ce:
                        logger.warning(f"[StyleService] Error reading color file {resolved}: {ce}")
                return match.group(0)

            resolved = resolve_style_file(fname)
            if os.path.isfile(resolved):
                return f'@import "{resolved}";'
            return match.group(0)

        resolved_css = re.sub(r'@import\s+(?:url\()?["\']?([^"\')]+)["\']?\)?\s*;', _replace_import, content)

        user_custom = None
        for sdir in get_user_style_dirs():
            for cname in ["custom.css", "style.css"]:
                candidate = os.path.join(sdir, cname)
                # Don't import target_style into itself if target_style was user style.css
                if os.path.isfile(candidate) and os.path.abspath(candidate) != os.path.abspath(target_style):
                    user_custom = candidate
                    break
            if user_custom:
                break

        if user_custom and os.path.isfile(user_custom):
            try:
                with open(user_custom, "r") as uf:
                    custom_content = uf.read()
                resolved_css += f"\n/* --- Custom Overrides ({user_custom}) --- */\n{custom_content}\n"
            except Exception as ue:
                logger.warning(f"[StyleService] Error reading custom stylesheet {user_custom}: {ue}")
                resolved_css += f'\n@import "{user_custom}";\n'

        return resolved_css
    except Exception as e:
        logger.error(f"[StyleService] Error resolving stylesheet: {e}")
        return None


class StyleService(Service):

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._style_changed = False
        self._reload_timer_id: int | None = None

        self._style_monitors = []
        for sdir in get_user_style_dirs():
            os.makedirs(sdir, exist_ok=True)
            try:
                mon = monitor_file(sdir)
                mon.connect("changed", self._on_style_file_changed)
                self._style_monitors.append(mon)
            except Exception as e:
                logger.debug(f"[StyleService] Monitor error for {sdir}: {e}")

        repo_style_dir = os.path.join(get_repo_dir(), "style")
        if os.path.isdir(repo_style_dir):
            try:
                repo_mon = monitor_file(repo_style_dir)
                repo_mon.connect("changed", self._on_style_file_changed)
                self._style_monitors.append(repo_mon)
            except Exception as e:
                logger.debug(f"[StyleService] Repo style monitor not attached: {e}")

    def _on_style_file_changed(self, *_):
        if self._reload_timer_id is not None:
            GLib.source_remove(self._reload_timer_id)
        self._reload_timer_id = GLib.timeout_add(100, self._debounced_reload)

    def _debounced_reload(self):
        self._reload_timer_id = None
        self.reload()
        return GLib.SOURCE_REMOVE

    @Property(bool, default_value=False)
    def style_changed(self) -> bool:
        return self._style_changed

    def reload(self, *_):
        try:
            resolved_css = compile_resolved_stylesheet(reload_callback=self.reload)
            if resolved_css:
                target_style = resolve_style_file("style.css")
                base_dir = os.path.dirname(target_style) if os.path.isfile(target_style) else "."
                self.app.set_stylesheet_from_string(
                    style_string=resolved_css,
                    compile=True,
                    base_path=base_dir,
                )

            GLib.timeout_add(100, apply_plugin_css, self.app)

            self._style_changed = not self._style_changed
            self.notify("style-changed")

        except Exception as e:
            logger.error(f"[StyleService] Error reloading styles: {e}")
