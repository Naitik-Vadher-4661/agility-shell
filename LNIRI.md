# Lniri Liquid Glass Support for Agility Shell

Agility Shell includes out-of-the-box support for **[Lniri](https://github.com/TattvaOrg/Lniri)**, the liquid-glass optical refraction engine for the Niri Wayland compositor.

With Lniri, Agility Shell’s bar, popouts, Dash, and on-screen displays can be transformed into physical optical liquid glass featuring fluid surface-tension curvature, dynamic wallpaper edge-lighting, caustic bevels, and chromatic prism dispersion.

---

## Table of Contents

1. [How Lniri Affects Agility Shell](#1-how-lniri-affects-agility-shell)
2. [Surface Namespaces](#2-surface-namespaces)
3. [Quick Setup (1-Line Enable)](#3-quick-setup-1-line-enable)
4. [Tuning Agility Shell for Optimal Glass](#4-tuning-agility-shell-for-optimal-glass)
5. [Shader Parameters Reference](#5-shader-parameters-reference)
6. [Curated Aesthetic Presets](#6-curated-aesthetic-presets)
7. [Zero Dependency & Standalone Independence](#7-zero-dependency--standalone-independence)

---

## 1. How Lniri Affects Agility Shell

Agility Shell components are rendered as Wayland **layer-shell surfaces** (`wlr-layer-shell`). 

Lniri intercepts layer-shell rendering via hardware fragment shaders (`clipped_surface.frag`) to create real-time physical optics:

```
┌────────────────────────────────────────────────────────┐
│  Desktop Wallpaper Layer (Wayland Layer::Background)   │  ◄── Must be active (awww / swww / hyprpaper)
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│   Lniri Liquid Glass Shader Engine                     │  ◄── Refracts wallpaper via `xray true`
│   (Snell law refraction, SDF bevel, glow, fringing)    │      Curves edges using `geometry-corner-radius`
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│   Agility Shell Layer Surfaces                         │  ◄── Set opacity to 40% - 70% in Dash Settings
│   (Bar, Dash, Applets, Notifications, OSD)             │      Glass shines through translucent surfaces
└────────────────────────────────────────────────────────┘
```

- **Refraction & Magnification**: The wallpaper behind the bar and applets is bent according to Snell's law ($IOR = 1.0 + \text{refraction-strength}$).
- **Optical Bevel & Meniscus**: Edges curve smoothly using Signed Distance Field (SDF) mathematics matching the window's corner radius.
- **Dynamic Edge Lighting**: Colors from the wallpaper bleed organically into the outer rim of the bar and popouts.
- **Prism Fringing**: Chromatic dispersion separates red, green, and blue light along glass edges like a crystal prism.

---

## 2. Surface Namespaces

Agility Shell registers standard, predictable namespaces across all layer surfaces:

| Component | Layer Surface Namespace | Layer | Typical Corner Radius |
| :--- | :--- | :--- | :--- |
| **Top / Bottom Bar** | `agility-shell-bar` | Top | `14` (Floating) / `0` (Full-width) |
| **Dash Launcher & Settings** | `agility-shell-dash` | Overlay | `24` |
| **Applet Menus & Popouts** | `agility-shell-applet` | Top | `16` |
| **On-Screen Display (OSD)** | `agility-shell-osd` | Overlay | `18` |
| **Notification Toasts** | `agility-shell-notifications` | Overlay | `16` |
| **Desktop Canvas Widgets** | `agility-shell-desktop-applets`| Bottom | `20` |
| **Wallpaper Gallery/Drawer** | `agility-shell-wallpaper-.*` | Top | `20` |

---

## 3. Quick Setup (1-Line Enable)

Agility Shell automatically seeds a ready-to-use Lniri template file to `~/.config/agility-shell/config/lniri.kdl`.

To activate liquid glass across the entire shell:

1. Open your compositor config (`~/.config/niri/config.kdl` or `~/.config/lniri/config.kdl`).
2. Add this single line:

```kdl
include "~/.config/agility-shell/config/lniri.kdl"
```

> **Note**: You do **not** need to include `niri.kdl` when using `lniri.kdl`. `lniri.kdl` automatically imports `niri.kdl` internally to provide all keybindings, startup commands, and layout rules, and then attaches the liquid glass shader rules.
>
> - **In Lniri**: Use ONLY `include "~/.config/agility-shell/config/lniri.kdl"`
> - **In Vanilla Niri**: Use ONLY `include "~/.config/agility-shell/config/niri.kdl"`

3. Reload your compositor with `niri msg action reload-config` or restart your session.

---

## 4. Tuning Agility Shell for Optimal Glass

For the glass refraction to be fully visible, follow these recommended settings:

### A. Enable Floating Bar
In Dash (`Super+D`) -> **Settings** -> **Layout**:
- Toggle **Floating Bar** to **ON**.
- This creates rounded margins around the bar, allowing Lniri's meniscus curvature to frame the bar edges.

### B. Adjust Surface Transparency
If the surface is 100% solid, it will cover the refracted background:
- In Dash (`Super+D`) -> **Settings** -> **Appearance**:
  - Set **Bar Background Opacity** to **50% – 70%**.
  - Set **Bar Widgets Opacity** to **70% – 85%**.
  - Set **Dash Backdrop Dim** to **40% – 60%**.
- Or customize your own translucent colors in `~/.config/agility-shell/custom_style/color.css`:
  ```css
  :root {
      --background: rgba(20, 24, 34, 0.45);
      --surface_container_high: rgba(30, 36, 52, 0.55);
  }
  ```

### C. Active Wallpaper Daemon
A wallpaper tool (`awww`, `swww`, `hyprpaper`, or `swaybg`) **must** be active. In Wayland, an unpainted background is pure black (`#000000`). Bending black pixels results in black ($0 \times \text{anything} = 0$), hiding all liquid glass reflections and highlights.

### D. Disable White Window Border Frames
To keep the pure optical glass aesthetic without artificial solid frames, ensure window borders are turned off in your `config.kdl`:
```kdl
layout {
    focus-ring {
        off
    }
    border {
        off
    }
}
```

---

## 5. Shader Parameters Reference

You can customize the `liquid-glass { ... }` block inside any `layer-rule` in `~/.config/agility-shell/config/lniri.kdl`:

| Parameter | Type | Default | Range | Description |
| :--- | :--- | :--- | :--- | :--- |
| `mode` | string | `"liquid"` | `"liquid"` / `"kwin-glass"` | `"liquid"` uses fluid water-drop curvature; `"kwin-glass"` uses caustic bevel and Oklab saturation. |
| `liquidity` | float | `0.85` | `0.0` – `2.0` | Controls fluid surface-tension curvature. `0.0` is flat glass; `1.0` is deep water-drop reflection. |
| `refraction-strength` | float | `3.8` | `1.0` – `6.0` | Overall magnitude of optical refraction ($IOR = 1.0 + \text{strength}$). |
| `power-factor` | float | `3.2` | `2.0` – `15.0` | Falloff curve from the edge inward (lower = wider glass bevel). |
| `refraction-power` | float | `1.2` | `0.5` – `2.0` | Exponential power applied to displacement vectors. |
| `fringing` | float | `0.35` | `0.0` – `1.0` | Chromatic dispersion (RGB prism separation along glass edges). |
| `edge-lighting` | float | `0.65` | `0.0` – `1.0` | Blends wallpaper colors dynamically onto outer window borders. |
| `glow-weight` | float | `0.25` | `0.0` – `0.6` | Specular rim highlight and shadow line intensity along the boundary. |
| `saturation` | float | `1.15` | `0.5` – `1.5` | Color saturation multiplier of the refracted background. |
| `vibrancy` | float | `0.40` | `0.0` – `0.5` | Luminance and vibrancy boost for glass substrates. |
| `adaptive-dim` | float | `0.05` | `0.0` – `0.5` | Darkens glass over very bright wallpapers for text readability. |
| `adaptive-boost` | float | `0.05` | `0.0` – `0.5` | Lightens glass over very dark wallpapers. |
| `lens-distortion` | float | `0.15` | `0.0` – `0.5` | Barrel distortion across the surface. |

---

## 6. Curated Aesthetic Presets

You can replace the `liquid-glass { ... }` block in `config/lniri.kdl` with any of these pre-tuned presets:

### Preset 1: Liquid Prism (Default)
*Fluid water-droplet reflection with vivid wallpaper edge-lighting and prism dispersion.*
```kdl
liquid-glass {
    mode "liquid"
    liquidity 0.85
    refraction-strength 3.8
    power-factor 3.2
    refraction-power 1.2
    fringing 0.35
    edge-lighting 0.65
    glow-weight 0.25
    saturation 1.15
    vibrancy 0.40
    lens-distortion 0.15
}
```

### Preset 2: Subtle Crystal
*Clean, low-distortion glass with a delicate optical bevel.*
```kdl
liquid-glass {
    mode "liquid"
    liquidity 0.30
    refraction-strength 2.0
    power-factor 2.5
    refraction-power 0.8
    fringing 0.15
    edge-lighting 0.40
    glow-weight 0.15
    saturation 1.05
    vibrancy 0.20
    lens-distortion 0.05
}
```

### Preset 3: Frosted Smoked Glass
*High-contrast tinted glass engineered for busy or high-brightness wallpapers.*
```kdl
liquid-glass {
    mode "liquid"
    liquidity 0.50
    refraction-strength 2.5
    power-factor 3.0
    refraction-power 1.0
    fringing 0.20
    edge-lighting 0.40
    glow-weight 0.10
    saturation 1.00
    vibrancy 0.20
    adaptive-dim 0.35
    lens-distortion 0.08
}
```

### Preset 4: Cyberpunk Neon Rim
*Electric edge illumination with intense highlights and high saturation.*
```kdl
liquid-glass {
    mode "liquid"
    liquidity 0.85
    refraction-strength 4.5
    power-factor 3.5
    refraction-power 1.5
    fringing 0.60
    edge-lighting 1.00
    glow-weight 0.50
    saturation 1.35
    vibrancy 0.50
    lens-distortion 0.25
}
```

---

## 7. Zero Dependency & Standalone Independence

- **No hard dependencies**: Agility Shell does not require Lniri to run. If you use vanilla Niri, Hyprland, Mango, Sway, or any other Wayland compositor, Agility Shell functions completely normally.
- **No performance penalty**: When Lniri is not present, layer-rules simply do not execute, and Agility Shell uses its native GTK / Wayland rendering pipeline.
- **Independent workflows**: Users who only use Lniri without Agility Shell can use Lniri independently; users who only use Agility Shell without Lniri can use Agility Shell independently.
