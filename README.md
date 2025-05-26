# 432 Hz Batch Converter 🎵

**Turn whole music folders from standard 440 Hz to 432 Hz with a single click.**
A Tk-based GUI + CLI, ships its own FFmpeg so users don’t have to install anything.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)
![PyInstaller](https://img.shields.io/badge/Built%20with-PyInstaller-ff69b4)
![License](https://img.shields.io/github/license/YOUR-NAME/432hz-converter)

---

## ✨ Features

| | |
|---|---|
| **Drag-and-drop GUI** | Pick source & output folders, progress bar, optional recursion. |
| **Smart FFmpeg resolver** | Finds `ffmpeg.exe`/`ffprobe.exe` next to the app, inside *ffmpeg-* sub-folders, or on **PATH**; override with `--ffmpeg`. |
| **HQ → Safe fallback** | First tries highest-quality codec flags, then retries with safe presets if the build lacks a feature. |
| **Keeps original bit-rate** | Reads bitrate with `ffprobe`; avoids unwanted up/down-sizing. |
| **No flashing consoles** | All FFmpeg calls run with *CREATE_NO_WINDOW* on Windows. |
| **Portable EXE** | `pyinstaller --onefile`, bundles FFmpeg; double-click to run on PCs without Python. |
| **Verbose logging** | `app_converter.log` written beside the EXE; warnings surface in GUI. |

---

## 📦 Quick start (source)

```bash
# clone & enter
$ git clone https://github.com/YOUR-NAME/432hz-converter.git
$ cd 432hz-converter

# create isolated env (optional but recommended)
$ python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate

# install runtime deps
$ pip install -r requirements.txt  # tkinterdnd2, tqdm

# run the GUI
$ python batch_432_converter.py
```

### CLI example

```bash
python batch_432_converter.py "D:/Albums" -r \
       --out "E:/Converted" --keep
```

---

## 🛠 Build a portable EXE (Windows)

```bash
pip install pyinstaller

pyinstaller --onefile --noconsole \
           --add-binary "ffmpeg/ffmpeg.exe;." \
           --add-binary "ffmpeg/ffprobe.exe;." \
           --hidden-import tkinterdnd2 \
           --icon assets/icon.ico \
           batch_432_converter.py
```

Result appears in `dist/batch_432_converter.exe`.

---

## 🖥 Screenshot

![GUI screenshot](assets/screenshot.png)

---

## 📚 Code layout

```text
batch_432_converter.py   main script (GUI + CLI)
ffmpeg/                  put static FFmpeg build here (ffmpeg.exe, ffprobe.exe)
assets/                  icons, screenshots
requirements.txt         runtime deps for developers
```

---

## 🚧 Roadmap

- [ ] macOS notarised `.app` bundle
- [ ] Real-time preview player with SoX
- [ ] Dark theme via `ttkbootstrap`
- [ ] GitHub Actions: auto-build EXE on every tag

---

## 🤝 Contributing

Pull requests are welcome! Please open an issue first to discuss any major change.
Run `python batch_432_converter.py --test` before committing—unit tests must pass.

---

## 📄 License

MIT © 2025 YOUR NAME
