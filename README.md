# FootballIQ Tagger

A desktop application for football analysts to tag match events using keyboard shortcuts and track players using OpenCV — all stored in a local SQLite database.

## Features

- **Video playback** — MP4, AVI, MOV support with frame-by-frame stepping
- **Keyboard event tagging** — P, S, T, D, G, C, F for Pass, Shot, Tackle, Dribble, Goal, Cross, Foul
- **Pitch coordinate mapping** — 4-point homography calibration (pixel → real pitch 0–120 × 0–80 m)
- **Player tracking** — OpenCV CSRT multi-player tracker (up to 11 players) *(Phase 3)*
- **Analytics** — KDE heatmaps, pass maps via mplsoccer
- **Export** — CSV and JSON export of all tagged events

## Architecture

Event-driven MVC with PyQt5 Signals & Slots. Modules never call each other directly — all communication is via signals.

```
ui/             → VideoWidget, Sidebar, MainWindow
core/           → VideoPlayer, EventTagger, PitchMapper, PlayerTracker
data/           → Database (SQLite), HeatmapGenerator, Exporter
```

## Installation

**1. Clone the repo**
```bash
git clone https://github.com/<your-username>/footballiq-tagger.git
cd footballiq-tagger
```

**2. Create a virtual environment**
```bash
python -m venv venv
```

**3. Activate it**
```bash
# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

**4. Install dependencies**
```bash
pip install -r requirements.txt
```

**5. Run**
```bash
python main.py
```

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| PyQt5 | ≥ 5.15 | GUI framework and Signals/Slots |
| opencv-contrib-python | == 4.10.0.84 | Video playback and CSRT player tracking |
| mplsoccer | ≥ 1.6 | Pitch visualization and KDE heatmaps |
| matplotlib | ≥ 3.7 | Heatmap rendering |
| numpy | ≥ 1.24 | Array operations and coordinate transforms |
| pandas | ≥ 2.0 | Data manipulation and CSV export |

> **Note:** Use `opencv-contrib-python` only — do not install `opencv-python` alongside it as they conflict.

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `P` | Tag: Pass |
| `S` | Tag: Shot |
| `T` | Tag: Tackle |
| `D` | Tag: Dribble |
| `G` | Tag: Goal |
| `C` | Tag: Cross |
| `F` | Tag: Foul |
| `SPACE` | Play / Pause |
| `←` / `→` | Seek ±5 seconds |
| `Shift+←` / `Shift+→` | Step one frame |
| `1`–`9` | Select active player |
| `H` | Generate heatmap |
| `E` | Export events to CSV |
| `Ctrl+Z` | Undo last tag |
| `Ctrl+C` | Pitch calibration mode |
| `Q` | Quit |

## Roadmap

- [x] v1.0 — Video playback, keyboard tagging, CSV export
- [ ] v1.1 — Pitch calibration UI, match/player management
- [ ] v1.2 — OpenCV CSRT player tracking
- [ ] v1.3 — Heatmaps, pass maps, shot maps
- [ ] v2.0 — AI auto-tagging (YOLO)

## License

MIT
