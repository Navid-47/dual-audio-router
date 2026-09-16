# Dual Audio Router

Route **Windows system audio** to **two Bluetooth headphones** at the same time — so two people can listen to the same lecture, video, or call.

Built with [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) (WASAPI loopback), [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), and the [Hallmark](https://github.com/nutlope/hallmark) design system (Cobalt / Workbench).

**Windows only.** Python 3.11+.

## Features

- Captures whatever plays on your default Windows output (WASAPI loopback)
- Fans the same audio stream to two separate Bluetooth devices
- Echo/feedback prevention checks before routing starts
- Desktop app with device picker, activity log, and start/stop controls

## Quick start (from source)

```powershell
git clone https://github.com/YOUR_USERNAME/dual-audio-router.git
cd dual-audio-router
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m dual_audio_router
```

## Windows setup (important — prevents echo)

1. **Settings → System → Sound → Output** → set **default** to **Laptop Speakers** (not Bluetooth).
2. **Mute laptop speakers** to 0%. You listen only through the headphones via this app.
3. Pair and connect **two** Bluetooth headphones. Do **not** set either as default.
4. In the app, pick the **WASAPI** entries for each headphone (matching sample rate).

## Usage

1. Launch **Dual Audio Router**.
2. Click **Refresh devices** if you just connected headphones.
3. Select **Headphone 1** and **Headphone 2** from the dropdowns.
4. Click **Start routing**, play audio on your PC, then **Stop** when done.

### CLI (optional)

```powershell
python -m dual_audio_router.cli
# or after pip install:
dual-audio-router-cli
```

## Build a Windows installer

Requires [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer wizard.

```powershell
pip install -r requirements-dev.txt
.\scripts\build.ps1
```

Outputs:

| Artifact | Location |
|----------|----------|
| Portable app folder | `dist\Dual Audio Router\` |
| Setup `.exe` | `installer\output\DualAudioRouter-Setup.exe` |

Run the setup exe on any Windows 10/11 PC — no Python required.

## Project layout

```
dual-audio-router/
├── dual_audio_router/     # Application package
│   ├── core.py            # Audio engine (loopback → 2 outputs)
│   ├── gui.py             # Desktop UI
│   └── cli.py             # Optional terminal UI
├── installer/             # PyInstaller spec + Inno Setup script
├── scripts/build.ps1      # One-command build
├── pyproject.toml
└── README.md
```

## How it works

```
[Apps: YouTube, Zoom, …]
        ↓
 Windows default output (muted laptop speakers)
        ↓
 WASAPI loopback capture  ──→  Dual Audio Router  ──→  BT headphone 1
                                              └──→  BT headphone 2
```

Loopback records the digital signal sent to the default device. The router reads that stream and writes identical chunks to both Bluetooth outputs in parallel.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Echo / delayed duplicate | Default output must be **speakers**, not a BT device you're routing to |
| Buzz / crackle | Pick **48000 Hz WASAPI** devices; refresh after connecting BT |
| "Cannot start" validation error | Don't pick the default device or loopback source as an output |
| No loopback device | Confirm WASAPI works: `python -m pyaudiowpatch` |

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

- [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) — WASAPI loopback support for PortAudio
