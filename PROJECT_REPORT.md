# FootballIQ Tagger — Project Report

**Date:** 2026-03-22
**Status:** Active Development
**Platform:** Windows 11 Desktop Application
**Language:** Python 3.x
**License:** MIT

---

## 1. Executive Summary

FootballIQ Tagger is a desktop application built for football analysts and coaches to manually tag match events from video footage. The analyst loads a video file, calibrates the virtual pitch, selects a player, and uses single-key shortcuts to log events (passes, shots, tackles, etc.) in real time. All tagged data is persisted locally in SQLite and can be exported to CSV or JSON. The application also provides post-match analytics — KDE position heatmaps, pass maps with arrows, and shot maps — rendered directly on a scaled football pitch using the `mplsoccer` library.

---

## 2. Goals & Motivation

| Goal | Description |
|---|---|
| Speed | Tag events as fast as the analyst can watch, with no mouse workflow during playback |
| Accuracy | Map click coordinates to real pitch dimensions via homography calibration |
| Analytics | Provide immediate visual feedback on player movement and passing patterns |
| Portability | Fully offline, single-machine SQLite storage — no cloud dependency |
| Extensibility | Modular MVC architecture to support future AI-assisted tagging |

---

## 3. Features

### 3.1 Video Playback
- Load MP4, AVI, MOV, MKV files via OpenCV
- Play / Pause (`Space`), Seek ±5 s (`← →`), Frame step (`Shift+← →`)
- Real-time timestamp display in sidebar

### 3.2 Event Tagging
Seven event types, each mapped to a single key:

| Key | Event | Outcome Prompt |
|---|---|---|
| `P` | Pass | Complete / Incomplete |
| `S` | Shot | On Target / Off Target / Blocked |
| `T` | Tackle | — |
| `D` | Dribble | — |
| `G` | Goal | — |
| `C` | Cross | Complete / Incomplete |
| `F` | Foul | — |

- Pass and Cross events capture **two clicks** — origin then destination
- `Esc` cancels a pending destination click
- **Undo stack** (20 events) with `Ctrl+Z`

### 3.3 Pitch Calibration
- 4-point click calibration (`Ctrl+C`) maps the four corner points of the visible pitch to real-world coordinates (0–120 m × 0–80 m)
- OpenCV `findHomography` computes the perspective transform
- All tagged events and tracking samples are stored with both video-pixel and pitch-metre coordinates

### 3.4 Player Tracking
- CSRT multi-tracker (OpenCV contrib) initiated by drag-selecting a bounding box on any player
- **Drift guard:** if a tracker moves > 80 px in one frame, it snaps back to the velocity-predicted position
- **Overlap correction:** trackers with IoU > 0.30 are resolved
- **YOLO re-anchoring:** every 10 frames, YOLOv8n detections are matched to active trackers (IoU ≥ 0.25) and bounding boxes are updated — preventing the tracker from following the wrong player after occlusions
- Supports up to 11 simultaneous trackers (one per outfield player)
- Tracking positions saved to the database for heatmap generation

### 3.5 AI Auto-Detection
- YOLOv8n (ultralytics) detects players and ball on demand
- Detected bounding boxes are overlaid on the video frame
- Ball detection automatically sets the tag click location

### 3.6 Match & Player Management
- Create a match with home/away team names and date
- Load a previously saved match (restores event log and player list)
- Add players with name, jersey number, and team
- Select active player via sidebar combo or `1–9` number keys

### 3.7 Analytics Visualizations
All charts rendered via `mplsoccer` on a dark-themed pitch:

| Shortcut | View | Description |
|---|---|---|
| `H` | Position Heatmap | KDE density plot of all tracking positions |
| `M` | Pass Map | Pass origins with arrows to destinations |
| `N` | Shot Map | Red dots for shots, gold stars for goals |

Analytics can be filtered to a single player or shown for the entire match.

### 3.8 Export
- `Ctrl+E` — CSV export of all events for the active match
- `Ctrl+J` — JSON export (formatted, with all coordinate and outcome fields)

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        ui/                                   │
│  MainWindow ──── VideoWidget (display + mouse input)         │
│       │            │                                         │
│       └────── Sidebar (player list, event log, shortcuts)    │
└────────────────────────┬────────────────────────────────────┘
                         │  PyQt5 Signals / Slots
┌────────────────────────▼────────────────────────────────────┐
│                       core/                                  │
│  VideoPlayer    EventTagger    PitchMapper    PlayerTracker  │
│  (OpenCV cap)   (tag + undo)   (homography)  (CSRT + YOLO)  │
│                                                              │
│                       AutoTagger (YOLOv8n)                  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                       data/                                  │
│      Database (SQLite3)          HeatmapGenerator            │
│      Thread-safe wrapper         (mplsoccer / matplotlib)    │
└─────────────────────────────────────────────────────────────┘
```

**Design principle:** No module calls another module directly. All inter-module communication is via PyQt5 signals and slots. This makes components independently testable and replaceable.

---

## 5. Database Schema

**SQLite3 database** (`footballiq.db`), created automatically on first run.

### `matches`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Match label |
| home_team | TEXT | |
| away_team | TEXT | |
| date | TEXT | |
| created_at | TIMESTAMP | Default: now |

### `players`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| match_id | INTEGER FK | → matches.id |
| name | TEXT | |
| number | INTEGER | Jersey number |
| team | TEXT | |

### `events`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| match_id | INTEGER FK | → matches.id |
| player_id | INTEGER FK | → players.id |
| event_type | TEXT | pass/shot/tackle/dribble/goal/cross/foul |
| timestamp | REAL | Video time in seconds |
| frame_number | INTEGER | |
| video_x/y | REAL | Click pixel coords |
| pitch_x/y | REAL | Real-world metres (if calibrated) |
| outcome | TEXT | complete/incomplete/on target/off target/blocked |
| dest_video_x/y | REAL | Pass/cross destination pixel |
| dest_pitch_x/y | REAL | Pass/cross destination metres |
| tagged_at | TIMESTAMP | |

### `tracking`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| match_id | INTEGER FK | |
| player_id | INTEGER FK | |
| frame_number | INTEGER | |
| timestamp | REAL | |
| video_x/y | REAL | Bounding box centre pixel |
| pitch_x/y | REAL | Mapped pitch coordinates |

---

## 6. Module Breakdown

| Module | Lines | Responsibility |
|---|---|---|
| `ui/main_window.py` | ~663 | Orchestration, menus, keyboard shortcuts, all signal wiring |
| `ui/video_widget.py` | ~180 | Frame rendering, click/drag input, overlay drawing |
| `ui/sidebar.py` | ~100+ | Player selector, event log, status indicators |
| `core/player_tracker.py` | 290 | CSRT + drift guard + YOLO re-anchoring |
| `data/database.py` | 198 | SQLite ORM wrapper, thread lock |
| `data/heatmap.py` | 162 | Heatmap, pass map, shot map rendering |
| `core/video_player.py` | 136 | OpenCV capture, playback controls |
| `core/event_tagger.py` | 117 | Event creation, undo stack, 2-click flow |
| `core/auto_tagger.py` | 66 | YOLOv8n detection wrapper |
| `core/pitch_mapper.py` | 69 | Homography calibration and transform |
| `main.py` | 22 | Entry point, High-DPI + Fusion style |

**Total:** ~2,000 lines of Python

---

## 7. Dependencies

| Package | Version | Purpose |
|---|---|---|
| PyQt5 | ≥ 5.15 | GUI framework and Signals/Slots |
| opencv-contrib-python | == 4.10.0.84 | Video playback and CSRT tracker |
| mplsoccer | ≥ 1.6 | Pitch visualization and KDE heatmaps |
| matplotlib | ≥ 3.7 | Heatmap and map rendering |
| numpy | ≥ 1.24 | Array operations and coordinate transforms |
| pandas | ≥ 2.0 | Data manipulation and CSV export |
| ultralytics | ≥ 8.0 | YOLOv8n player/ball detection |

> `opencv-contrib-python` must be the sole OpenCV install — do not install `opencv-python` alongside it.

---

## 8. Known Limitations

1. **No tests** — The `tests/` directory exists but contains no test cases. Core logic (especially `PitchMapper` and `PlayerTracker`) is untested.
2. **CSRT drift** — Despite the drift guard and YOLO re-anchoring, heavy occlusion (crowded penalty areas) can still cause tracker loss.
3. **Single match at a time** — The UI does not support multi-match comparison or simultaneous views.
4. **Manual calibration** — Pitch calibration must be repeated every time a camera angle changes. No automatic recalibration.
5. **YOLO model download** — YOLOv8n weights are downloaded on first use; no offline bundling.
6. **No video scrubbing UI** — Seek is keyboard-only (±5 s steps); there is no visual timeline/scrubber widget.
7. **README roadmap is stale** — All milestones up to v2.0 are already implemented but marked as pending in `README.md`.

---

## 9. Roadmap (Suggested)

| Priority | Feature |
|---|---|
| High | Add unit tests for `PitchMapper`, `EventTagger`, `Database` |
| High | Fix stale README roadmap checkboxes |
| Medium | Video timeline scrubber widget |
| Medium | Automatic camera re-calibration detection |
| Medium | Multi-match analytics (compare players across games) |
| Low | YOLO model bundling for offline use |
| Low | Dark-mode theme toggle |
| Low | Clip export (short video clips around tagged events) |

---

## 10. File Structure

```
footballiq_tagger/
├── core/
│   ├── auto_tagger.py        # YOLOv8n player & ball detection
│   ├── event_tagger.py       # Event tagging + undo stack
│   ├── pitch_mapper.py       # Homography calibration
│   ├── player_tracker.py     # CSRT + drift guard + YOLO re-anchoring
│   └── video_player.py       # OpenCV playback engine
├── data/
│   ├── database.py           # SQLite3 persistence
│   └── heatmap.py            # Analytics visualizations
├── ui/
│   ├── main_window.py        # Main window + dialogs
│   ├── sidebar.py            # Player list, event log, shortcuts
│   └── video_widget.py       # Frame display + input capture
├── tests/                    # (empty)
├── FootballQ Tgger Documentation/
│   ├── FootballIQ_Tagger_Documentation.pdf
│   ├── footballiq_wireframes.html
│   └── screen.png / screen (2).png
├── main.py
├── README.md
├── requirements.txt
└── footballiq.db             # SQLite database (runtime)
```

---

*Report generated 2026-03-22*
