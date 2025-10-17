from __future__ import annotations

import argparse
import os
import re
import subprocess
import shutil
import sys
import threading
import unittest
from pathlib import Path
from typing import List, Optional, Tuple, \
    Union  # Union might be needed for PopenResult type hints for older Pythons, but | is fine for 3.10+
import logging
import json  # Added for parsing ffprobe JSON output

# =============================================================================
# 0.  FFmpeg resolver
# =============================================================================
_FFMPEG = "ffmpeg"
_FFPROBE = "ffprobe"


# Logging setup function
def _setup_logging():
    log_file_name = "app_converter.log"
    try:
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            log_file_path = Path(sys.executable).parent / log_file_name
        else:
            log_file_path = Path(__file__).resolve().parent / log_file_name
    except Exception:  # Fallback if path resolution fails for some reason
        log_file_path = Path(log_file_name)

    logging.basicConfig(
        filename=str(log_file_path),
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s",
        filemode='a'
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(formatter)
    logging.getLogger().addHandler(console_handler)

    logging.info("Application logging initialized.")
    logging.info(f"Initial FFmpeg path: {_FFMPEG}, FFprobe path: {_FFPROBE}")


def _resolve_ffmpeg(ffmpeg_arg: Optional[Path | str]) -> None:
    global _FFMPEG, _FFPROBE
    logging.info(f"Attempting to resolve FFmpeg. Argument provided: {ffmpeg_arg}")

    ffmpeg_exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    ffprobe_exe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"

    resolved_ffmpeg_path: Optional[str] = None
    resolved_ffprobe_path: Optional[str] = None
    source_of_resolution = "default"

    if ffmpeg_arg:
        logging.info(f"Checking --ffmpeg argument: {ffmpeg_arg}")
        p_arg = Path(ffmpeg_arg).expanduser().resolve()
        temp_ffmpeg: Optional[Path] = None
        temp_ffprobe: Optional[Path] = None

        if p_arg.is_file():
            temp_ffmpeg = p_arg
            temp_ffprobe = p_arg.with_name(
                ffprobe_exe_name.split('.')[0] + p_arg.suffix)
            logging.info(f"Argument is a file. ffmpeg: {temp_ffmpeg}, ffprobe guess: {temp_ffprobe}")
        elif p_arg.is_dir():
            temp_ffmpeg = p_arg / ffmpeg_exe_name
            temp_ffprobe = p_arg / ffprobe_exe_name
            logging.info(f"Argument is a directory. ffmpeg: {temp_ffmpeg}, ffprobe: {temp_ffprobe}")

        if temp_ffmpeg and temp_ffmpeg.is_file() and \
                temp_ffprobe and temp_ffprobe.is_file():
            resolved_ffmpeg_path = str(temp_ffmpeg.resolve())
            resolved_ffprobe_path = str(temp_ffprobe.resolve())
            source_of_resolution = f"argument '{ffmpeg_arg}'"
            logging.info(f"Resolved from argument: ffmpeg='{resolved_ffmpeg_path}', ffprobe='{resolved_ffprobe_path}'")
        else:
            logging.warning(f"Could not resolve ffmpeg/ffprobe from argument path: {ffmpeg_arg}")

    if not resolved_ffmpeg_path:
        logging.info("Checking System PATH for ffmpeg/ffprobe.")
        path_ffmpeg = shutil.which(ffmpeg_exe_name)
        path_ffprobe = shutil.which(ffprobe_exe_name)
        if path_ffmpeg and path_ffprobe:
            resolved_ffmpeg_path = path_ffmpeg
            resolved_ffprobe_path = path_ffprobe
            source_of_resolution = "System PATH"
            logging.info(
                f"Resolved from System PATH: ffmpeg='{resolved_ffmpeg_path}', ffprobe='{resolved_ffprobe_path}'")
        else:
            logging.info("Not found in System PATH.")

    if not resolved_ffmpeg_path:
        logging.info("Checking bundled layouts for ffmpeg/ffprobe.")
        source_of_resolution = "bundled files"

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # When frozen, _MEIPASS is the path to the temporary bundle directory
            here = Path(sys._MEIPASS)
            logging.info(f"Application is frozen. Using bundle_dir for bundled search: {here}")
        else:
            # Not frozen, determine path based on __file__ or cwd
            try:
                here = Path(__file__).resolve().parent
            except NameError:  # if __file__ is not defined (e.g. interactive session)
                here = Path.cwd()
                logging.warning(f"__file__ not defined, using current working directory for bundled search: {here}")

        script_dir_ffmpeg = here / ffmpeg_exe_name
        script_dir_ffprobe = here / ffprobe_exe_name
        logging.info(
            f"Checking next to script/executable: ffmpeg='{script_dir_ffmpeg}', ffprobe='{script_dir_ffprobe}'")
        if script_dir_ffmpeg.is_file() and script_dir_ffprobe.is_file():
            resolved_ffmpeg_path = str(script_dir_ffmpeg)
            resolved_ffprobe_path = str(script_dir_ffprobe)
            logging.info("Resolved from script/executable directory.")
        else:
            logging.info("Checking subdirectories for ffmpeg/ffprobe.")
            for item in here.iterdir():
                if item.is_dir() and item.name.lower().startswith("ffmpeg"):
                    bin_dir_ffmpeg = item / "bin" / ffmpeg_exe_name
                    bin_dir_ffprobe = item / "bin" / ffprobe_exe_name
                    root_dir_ffmpeg = item / ffmpeg_exe_name
                    root_dir_ffprobe = item / ffprobe_exe_name

                    if bin_dir_ffmpeg.is_file() and bin_dir_ffprobe.is_file():
                        resolved_ffmpeg_path = str(bin_dir_ffmpeg.resolve())
                        resolved_ffprobe_path = str(bin_dir_ffprobe.resolve())
                        logging.info(f"Resolved from subdirectory bin: {item.name}")
                        break
                    elif root_dir_ffmpeg.is_file() and root_dir_ffprobe.is_file():
                        resolved_ffmpeg_path = str(root_dir_ffmpeg.resolve())
                        resolved_ffprobe_path = str(root_dir_ffprobe.resolve())
                        logging.info(f"Resolved from subdirectory root: {item.name}")
                        break
            if not resolved_ffmpeg_path:
                logging.info("Not found in subdirectories.")

    if resolved_ffmpeg_path and resolved_ffprobe_path:
        _FFMPEG = resolved_ffmpeg_path
        _FFPROBE = resolved_ffprobe_path
        logging.info(f"FFmpeg resolved to: {_FFMPEG}")
        logging.info(f"FFprobe resolved to: {_FFPROBE}")
    else:
        logging.warning(f"Could not resolve ffmpeg/ffprobe using any method. Using defaults: {_FFMPEG}, {_FFPROBE}")

    final_ffmpeg_executable = shutil.which(_FFMPEG)
    if not final_ffmpeg_executable:
        search_locations_tried = [
            f"  - Argument --ffmpeg: {ffmpeg_arg if ffmpeg_arg else 'not provided (or path invalid)'}",
            f"  - System PATH for '{ffmpeg_exe_name}'",
            f"  - Next to script: {Path(__file__).resolve().parent / ffmpeg_exe_name if '__file__' in globals() else 'N/A (interactive?)'}",
            "  - In 'ffmpeg*' subdirectories (e.g., ./ffmpeg-xyz/ffmpeg.exe or ./ffmpeg-xyz/bin/ffmpeg.exe)",
        ]
        error_message = (
                f"FFmpeg ('{_FFMPEG}') not found or not executable. Last attempt based on: {source_of_resolution}.\n"
                "Search locations checked (in order):\n" +
                "\n".join(search_locations_tried) +
                "\n\nPlease ensure ffmpeg is installed, accessible via PATH, bundled correctly, or specified via --ffmpeg."
        )
        logging.critical(error_message)
        sys.exit(1)
    _FFMPEG = final_ffmpeg_executable
    logging.info(f"Final verified FFmpeg executable: {_FFMPEG}")

    final_ffprobe_executable = shutil.which(_FFPROBE)
    if not final_ffprobe_executable:
        search_locations_tried = [
            f"  - Argument --ffmpeg (for ffprobe near ffmpeg): {ffmpeg_arg if ffmpeg_arg else 'not provided (or path invalid)'}",
            f"  - System PATH for '{ffprobe_exe_name}'",
            f"  - Next to script: {Path(__file__).resolve().parent / ffprobe_exe_name if '__file__' in globals() else 'N/A (interactive?)'}",
            "  - In 'ffmpeg*' subdirectories (e.g., ./ffmpeg-xyz/ffprobe.exe or ./ffmpeg-xyz/bin/ffprobe.exe)",
        ]
        error_message = (
                f"ffprobe ('{_FFPROBE}') not found or not executable. Last attempt based on: {source_of_resolution}.\n"
                "Search locations checked (in order):\n" +
                "\n".join(search_locations_tried) +
                "\n\nPlease ensure ffprobe is installed (usually with ffmpeg), accessible via PATH, bundled correctly, or specified via --ffmpeg."
        )
        logging.critical(error_message)
        sys.exit(1)
    _FFPROBE = final_ffprobe_executable
    logging.info(f"Final verified FFprobe executable: {_FFPROBE}")


# =============================================================================
# 1.  Helpers – codecs, sanitised stderr, file operations
# =============================================================================

class PopenResult:
    """A class to mimic subprocess.CompletedProcess for Popen."""

    def __init__(self, args: List[str], returncode: int, stdout: Optional[bytes | str], stderr: Optional[bytes | str]):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _popen_run(cmd: List[str], capture_output: bool = False, text: bool = False, check: bool = False,
               errors: Optional[str] = None, **kwargs) -> PopenResult:
    """
    Runs a command using subprocess.Popen, mimicking subprocess.run,
    but with CREATE_NO_WINDOW flag on Windows to prevent console flashing.
    """
    creationflags = 0
    if os.name == 'nt':
        creationflags = subprocess.CREATE_NO_WINDOW

    cmd_str = [str(c) for c in cmd]  # Ensure all command parts are strings

    # Popen's 'errors' argument is only used if text=True (or universal_newlines=True)
    popen_errors = errors if text else None

    try:
        process = subprocess.Popen(
            cmd_str,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=text,
            errors=popen_errors,
            creationflags=creationflags,
            **kwargs
        )
        stdout, stderr = process.communicate()
        returncode = process.returncode
    except FileNotFoundError as e:
        # Mimic FileNotFoundError behavior of subprocess.run if executable not found
        logging.error(f"Error running command {' '.join(cmd_str)}: {e}", exc_info=True)
        err_msg = f"Executable not found: {cmd_str[0]}"
        return PopenResult(args=cmd_str, returncode=e.errno if hasattr(e, 'errno') else 1,
                           stdout=b'' if not text else '', stderr=err_msg.encode() if not text else err_msg)
    except Exception as e:  # Catch other Popen-related errors
        logging.error(f"Unexpected error running command {' '.join(cmd_str)}: {e}", exc_info=True)
        err_msg = str(e)
        return PopenResult(args=cmd_str, returncode=1, stdout=b'' if not text else '',
                           stderr=err_msg.encode() if not text else err_msg)

    if check and returncode != 0:
        raise subprocess.CalledProcessError(returncode, cmd_str, output=stdout, stderr=stderr)

    return PopenResult(args=cmd_str, returncode=returncode, stdout=stdout, stderr=stderr)


SUPPORTED_EXTS = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wma"}

_FFMPEG_IGNORE_LINES = re.compile(
    r"^(ffmpeg version\b|"
    r"built with\b|"
    r"configuration:|"
    r"libav\w+\s+.*?\s+/\s+.*|"
    r"\s*--(?:[a-zA-Z0-9_-]+=.*|[\w-]+)|"
    r"Incorrect BOM value|"
    r"Error reading comment frame, skipped)"
)


def _clean_ffmpeg_err(raw: bytes) -> str:
    lines = raw.decode(errors="ignore").splitlines()
    meaningful_lines = [ln for ln in lines if not _FFMPEG_IGNORE_LINES.match(ln)]
    return "\n".join(meaningful_lines[-15:]) if meaningful_lines else "(no ffmpeg stderr captured)"


HQ_CODEC: dict[str, List[str]] = {
    ".mp3": ["-c:a", "libmp3lame", "-b:a", "320k", "-compression_level", "0"],
    ".m4a": ["-c:a", "aac", "-b:a", "512k", "-movflags", "+faststart"],
    ".aac": ["-c:a", "aac", "-b:a", "512k"],
    ".flac": ["-c:a", "flac", "-compression_level", "8"],
    ".wav": ["-c:a", "pcm_s24le"],
    ".wma": ["-c:a", "wmapro", "-b:a", "320k"]
}

SAFE_CODEC: dict[str, List[str]] = {
    ".mp3": ["-c:a", "libmp3lame", "-b:a", "320k"],
    ".m4a": ["-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart"],
    ".aac": ["-c:a", "aac", "-b:a", "256k"],
    ".flac": ["-c:a", "flac"],
    ".wav": ["-c:a", "pcm_s16le"],
    ".wma": ["-c:a", "wmav2", "-b:a", "192k"]
}


def _codec_for_ext(ext: str, safe: bool = False) -> List[str]:
    ext = ext.lower()
    default_codec = ["-c:a", "aac", "-b:a", "320k"]
    if ext in [".flac", ".wav"]:  # For lossless, default to safe copy-like options if not specified
        default_codec = SAFE_CODEC.get(ext, ["-c:a", "copy"])  # Should ideally not happen if ext is supported

    return (SAFE_CODEC if safe else HQ_CODEC).get(ext, default_codec)


def find_audio_files(folder: Path, recursive: bool) -> List[Path]:
    pattern = "**/*" if recursive else "*"
    return [p for p in folder.glob(pattern) if p.suffix.lower() in SUPPORTED_EXTS and p.is_file()]


def _get_audio_metadata(path: Path) -> Tuple[Optional[int], Optional[int]]:
    """
    Gets sample rate (Hz) and bitrate (bps) of the first audio stream.
    Tries ffprobe, falls back to ffmpeg, and finally assumes 44100 Hz if both fail.
    """
    sample_rate: Optional[int] = None
    bit_rate: Optional[int] = None

    # --- Method 1: ffprobe (strict, but fast and clean) ---
    cmd_probe = [
        _FFPROBE, "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "a:0", str(path)
    ]
    logging.debug(f"Executing ffprobe for metadata: {' '.join(cmd_probe)}")
    try:
        process = _popen_run(cmd_probe, capture_output=True, text=True, check=False, errors="ignore")
        if process.returncode == 0 and process.stdout:
            ffprobe_output = json.loads(process.stdout)
            if ffprobe_output and "streams" in ffprobe_output and len(ffprobe_output["streams"]) > 0:
                stream = ffprobe_output["streams"][0]
                sr_str = stream.get("sample_rate")
                if sr_str and sr_str.isdigit():
                    sample_rate = int(sr_str)
                br_str = stream.get("bit_rate")
                if br_str and br_str.isdigit():
                    bit_rate = int(br_str)

                if sample_rate:
                    logging.info(f"Successfully got metadata for {path.name} via ffprobe.")
                    return sample_rate, bit_rate
    except Exception as e:
        logging.warning(f"ffprobe failed for {path.name}: {e}", exc_info=False)

    logging.warning(f"ffprobe failed for {path.name}. Falling back to ffmpeg.")

    # --- Method 2: ffmpeg (more resilient, but requires parsing stderr) ---
    cmd_ffmpeg = [_FFMPEG, "-i", str(path)]
    logging.debug(f"Executing ffmpeg for metadata fallback: {' '.join(cmd_ffmpeg)}")
    try:
        process = _popen_run(cmd_ffmpeg, capture_output=True, text=True, errors="ignore")
        output = process.stderr
        if output:
            sr_match = re.search(r"(\d+)\s+Hz", output)
            br_match = re.search(r"(\d+)\s+kb/s", output)
            if sr_match:
                sample_rate = int(sr_match.group(1))
                logging.info(f"Successfully got sample rate for {path.name} via ffmpeg fallback.")
            if br_match:
                bit_rate = int(br_match.group(1)) * 1000
    except Exception as e:
        logging.error(f"ffmpeg fallback for {path.name} failed with an unexpected error: {e}", exc_info=True)

    # --- Method 3: Assume 44100 Hz as a final fallback ---
    if sample_rate is None:
        logging.warning(f"All methods failed to get metadata for {path.name}. ASSUMING 44100 Hz.")
        sample_rate = 44100

    return sample_rate, bit_rate


# =============================================================================
# 2.  Conversion function with automatic retry
# =============================================================================

def convert_to_432(src: Path, dst: Path, original_sr: int, target_sr: int, original_bitrate_bps: Optional[int]) -> None:
    logging.info(f"Converting {src} to {dst} with original SR {original_sr}, target SR {target_sr}")
    dst.parent.mkdir(parents=True, exist_ok=True)

    # CORRECTED: The pitch shift calculation MUST use the original sample rate.
    chain = f"asetrate={original_sr}*432/440,aresample={target_sr}"

    def _run(cmd_list: List[str]):
        logging.debug(f"Executing ffmpeg command: {' '.join(cmd_list)}")
        return _popen_run(cmd_list, capture_output=True, text=False)

    def _adjust_bitrate_in_options(codec_options: List[str], orig_bps: Optional[int]) -> List[str]:
        if orig_bps is None:
            return codec_options
        adjusted_options = list(codec_options)
        try:
            b_a_idx = adjusted_options.index("-b:a")
            if b_a_idx + 1 < len(adjusted_options):
                target_br_str = adjusted_options[b_a_idx + 1]
                target_bps = -1
                if target_br_str.lower().endswith('k'):
                    target_bps = int(target_br_str[:-1]) * 1000
                elif target_br_str.isdigit():
                    target_bps = int(target_br_str)
                if target_bps != -1 and orig_bps < target_bps:
                    adjusted_options[b_a_idx + 1] = f"{orig_bps // 1000}k"
                    logging.info(
                        f"Adjusting target bitrate from {target_br_str} to original {adjusted_options[b_a_idx + 1]} for {src.name}")
        except (ValueError, IndexError):
            pass
        return adjusted_options

    base_cmd_list = [
        _FFMPEG, "-y", "-i", str(src),
        "-map", "0:a?", "-map", "0:v?", "-c:v", "copy",
        "-af", chain,
    ]
    ext = dst.suffix.lower()

    hq_options = _adjust_bitrate_in_options(_codec_for_ext(ext, safe=False), original_bitrate_bps)
    hq_cmd_list = base_cmd_list + hq_options + [str(dst)]
    proc = _run(hq_cmd_list)

    if proc.returncode == 0:
        logging.info(f"Successfully converted {src.name} (HQ settings) to {dst.name}")
        return

    hq_stderr_cleaned = _clean_ffmpeg_err(proc.stderr) if proc.stderr is not None else "(no ffmpeg stderr captured)"
    logging.warning(f"HQ conversion failed for {src.name}. Retrying with safe settings. Error:\n{hq_stderr_cleaned}")

    safe_options = _adjust_bitrate_in_options(_codec_for_ext(ext, safe=True), original_bitrate_bps)
    safe_cmd_list = base_cmd_list + safe_options + [str(dst)]
    proc_safe = _run(safe_cmd_list)
    if proc_safe.returncode == 0:
        logging.info(f"Successfully converted {src.name} (Safe preset) to {dst.name}")
        return

    safe_stderr_cleaned = _clean_ffmpeg_err(
        proc_safe.stderr) if proc_safe.stderr is not None else "(no ffmpeg stderr captured)"
    final_err_message = f"HQ error:\n{hq_stderr_cleaned}\nSafe error:\n{safe_stderr_cleaned}"
    raise subprocess.CalledProcessError(proc_safe.returncode, proc_safe.args, stderr=final_err_message)


# =============================================================================
# 3.  GUI and Drag‑and‑drop
# =============================================================================
try:
    import tkinter as _tk
    from tkinter import filedialog as _filedialog, messagebox as _messagebox, ttk as _ttk
except (ModuleNotFoundError, ImportError):
    _tk = _filedialog = _messagebox = _ttk = None

if _tk is not None:
    try:
        from tkinterdnd2 import DND_FILES as _DND_FILES, TkinterDnD as _TkDnD
    except (ModuleNotFoundError, ImportError):
        _TkDnD = None
        _DND_FILES = "Files"
else:
    _TkDnD = None
    _DND_FILES = "Files"


def _parse_drop_data(data: str) -> Optional[Path]:
    if not data: return None
    s = data.strip()
    if s.startswith("{") and s.endswith("}") and len(s) > 1: s = s[1:-1].strip()
    if not s: return None
    if '\n' in s: s = s.split('\n')[0].strip()
    if not Path(s).exists():
        logging.warning(f"Parsed drop data '{s}' does not exist as a path.")
        return None
    return Path(s)


if _tk is not None and _messagebox is not None and _filedialog is not None and _ttk is not None:
    class _ConverterGUI:
        def __init__(self, root: "_tk.Tk", args: argparse.Namespace) -> None:
            self.root = root
            self.args = args
            root.title("Batch 432 Hz Converter")
            root.resizable(False, False)
            self.src: Optional[Path] = None
            self.dst_base: Optional[Path] = None
            self.thread: Optional[threading.Thread] = None
            self._build()
            self._apply_initial_args()

        def _build(self):
            pad = {"padx": 10, "pady": 4}
            f_src = _ttk.Frame(self.root)
            f_src.grid(row=0, column=0, sticky="ew", **pad)
            _ttk.Label(f_src, text="Source ▶").pack(side="left")
            self.var_src = _tk.StringVar()
            self.entry_src = _ttk.Entry(f_src, textvariable=self.var_src, width=48)
            self.entry_src.pack(side="left", fill="x", expand=True, padx=(5, 0))
            _ttk.Button(f_src, text="Browse…", command=self._browse_src).pack(side="left", padx=(5, 0))

            if _TkDnD is not None and hasattr(self.entry_src, 'drop_target_register'):
                self.entry_src.drop_target_register(_DND_FILES)
                self.entry_src.dnd_bind('<<Drop>>', self._ondrop_src)

            f_out = _ttk.Frame(self.root)
            f_out.grid(row=1, column=0, sticky="ew", **pad)
            _ttk.Label(f_out, text="Output ▶").pack(side="left")
            self.var_out = _tk.StringVar()
            self.entry_out = _ttk.Entry(f_out, textvariable=self.var_out, width=48)
            self.entry_out.pack(side="left", fill="x", expand=True, padx=(5, 0))
            _ttk.Button(f_out, text="Browse…", command=self._browse_out).pack(side="left", padx=(5, 0))

            f_opt = _ttk.Frame(self.root)
            f_opt.grid(row=2, column=0, sticky="w", **pad)
            self.rec = _tk.BooleanVar(value=self.args.recursive)
            self.keep = _tk.BooleanVar(value=self.args.keep)
            _ttk.Checkbutton(f_opt, text="Recursive", variable=self.rec).pack(side="left")
            _ttk.Checkbutton(f_opt, text="Skip existing", variable=self.keep).pack(side="left", padx=(10, 0))

            self.bar = _ttk.Progressbar(self.root, length=420, mode="determinate")
            self.bar.grid(row=3, column=0, **pad)
            self.btn = _ttk.Button(self.root, text="Start", command=self._start)
            self.btn.grid(row=4, column=0, **pad)

        def _apply_initial_args(self):
            if self.args.folder:
                p = Path(self.args.folder).resolve()
                if p.is_dir():
                    self._set_src(p)
                else:
                    _messagebox.showwarning("Warning",
                                            f"The provided source folder is not a valid directory:\n{self.args.folder}")
            if self.args.outdir:
                self._set_out(Path(self.args.outdir).resolve())
            elif self.src and not self.var_out.get():
                self._set_out(self.src.parent / f"{self.src.name}_432Hz")

        def _browse_src(self):
            d = _filedialog.askdirectory(title="Select Source Folder")
            if d: self._set_src(Path(d))

        def _browse_out(self):
            d = _filedialog.askdirectory(title="Select Output Base Folder")
            if d: self._set_out(Path(d))

        def _ondrop_src(self, event):
            p = _parse_drop_data(event.data)
            if p and p.is_dir():
                self._set_src(p)
            else:
                _messagebox.showwarning("Invalid Drop", "Please drop a folder, not a file.")

        def _set_src(self, p: Path):
            self.src = p.resolve()
            self.var_src.set(str(self.src))
            if not self.var_out.get() and self.src.is_dir():
                self._set_out(self.src.parent / f"{self.src.name}_432Hz")

        def _set_out(self, p: Path):
            self.dst_base = p.resolve()
            self.var_out.set(str(self.dst_base))

        def _start(self):
            if self.thread and self.thread.is_alive():
                _messagebox.showwarning("Busy", "Conversion is already in progress.")
                return
            if not self.src or not self.src.is_dir():
                _messagebox.showerror("Error", "Please select a valid source folder.")
                return
            self.dst_base = Path(self.var_out.get()).resolve()
            if not self.dst_base:
                _messagebox.showerror("Error", "Please select an output folder.")
                return
            try:
                self.dst_base.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                _messagebox.showerror("Error", f"Cannot create output folder:\n{self.dst_base}\n{e}")
                return

            self.btn.config(state="disabled")
            self.bar["value"] = 0
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
            self._poll()

        def _poll(self):
            if self.thread and self.thread.is_alive():
                self.root.after(200, self._poll)
            else:
                self.btn.config(state="normal")
                if self.bar["value"] == self.bar["maximum"] and self.bar["maximum"] > 0:
                    _messagebox.showinfo("Done", f"Conversion complete!\nFiles are in: {self.dst_base}")
                self.bar["value"] = 0

        def _worker(self):
            assert self.src and self.dst_base, "Source or destination not set"
            files = find_audio_files(self.src, self.rec.get())
            total = len(files)
            if not total:
                self.root.after(0, lambda: _messagebox.showinfo("Info", "No supported audio files found."))
                return

            self.bar.config(maximum=total)
            errors_occurred = False
            for idx, f_path in enumerate(files, 1):
                self.root.after(0, lambda i=idx: self.bar.config(value=i))
                ext_out = ".mp3" if f_path.suffix.lower() == ".wma" else f_path.suffix
                rel_path = f_path.relative_to(self.src)
                dst_file = self.dst_base / rel_path.with_name(f"{f_path.stem}_432{ext_out}")

                try:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    logging.error(f"GUI Worker: Error creating directory for {dst_file.name}: {e}", exc_info=True)
                    self.root.after(0, lambda f=dst_file.name, m=e: _messagebox.showerror("File Error",
                                                                                          f"Could not create directory for:\n{f}\n\n{m}"))
                    errors_occurred = True
                    continue

                if self.keep.get() and dst_file.exists() and dst_file.stat().st_size > 0:
                    logging.info(f"GUI Worker: Skipping existing file: {dst_file}")
                    continue

                original_sample_rate, original_bitrate = _get_audio_metadata(f_path)

                # The check for None is now effectively gone, as _get_audio_metadata will always return a value
                # (or the assumed default). This prevents the "Skipped" message for metadata reasons.

                target_sample_rate = 48000
                try:
                    # CORRECTED: Pass the original sample rate to the conversion function.
                    convert_to_432(f_path, dst_file, original_sample_rate, target_sample_rate, original_bitrate)
                except subprocess.CalledProcessError as e_conv:
                    logging.error(f"GUI Worker: Conversion failed for {f_path.name}: {e_conv.stderr}", exc_info=False)
                    self.root.after(0,
                                    lambda p=f_path.name, err=e_conv.stderr: _messagebox.showerror("Conversion Error",
                                                                                                   f"Failed to convert:\n{p}\n\nError:\n{err}"))
                    errors_occurred = True
                except Exception as e_gen:
                    logging.error(f"GUI Worker: Unexpected error converting {f_path.name}: {e_gen}", exc_info=True)
                    self.root.after(0, lambda p=f_path.name, err=e_gen: _messagebox.showerror("Conversion Error",
                                                                                              f"Unexpected error converting:\n{p}\n\nError:\n{err}"))
                    errors_occurred = True

            if errors_occurred:
                self.root.after(0, lambda: _messagebox.showwarning("Done",
                                                                   "Conversion finished, but some files had errors. Check log."))


# =============================================================================
# 4.  Arg‑parser & tests
# =============================================================================

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="440→432 Hz batch converter (GUI)")
    p.add_argument("folder", type=Path, nargs="?", default=None,
                   help="Optional: Source music folder to pre-fill in GUI.")
    p.add_argument("-r", "--recursive", action="store_true", help="Pre-select recursive search in GUI.")
    p.add_argument("--keep", action="store_true", help="Pre-select skipping existing files in GUI.")
    p.add_argument("--ffmpeg", dest="ffmpeg_path", type=Path,
                   help="Path to ffmpeg folder/executable for FFmpeg/FFprobe resolution.")
    p.add_argument("--out", dest="outdir", type=Path, help="Optional: Destination base folder to pre-fill in GUI.")
    p.add_argument("--test", action="store_true", help="Run self‑tests and exit.")
    return p


class _Tests(unittest.TestCase):
    def test_codec_quality(self):
        self.assertIn("-b:a", _codec_for_ext(".mp3"))
        self.assertIn("512k", _codec_for_ext(".aac"))
        self.assertTrue(_codec_for_ext(".wma"))
        self.assertTrue(_codec_for_ext(".wma", safe=True))

    def test_parse_drop_data(self):
        Path("./tmp_test_dir").mkdir(exist_ok=True)
        self.assertEqual(_parse_drop_data("{./tmp_test_dir}"), Path("./tmp_test_dir"))
        Path("./tmp_test_dir").rmdir()


def _run_tests():
    logging.info("Running self-tests...")
    try:
        _resolve_ffmpeg(None)
    except SystemExit:
        logging.warning("FFmpeg/FFprobe not found during test setup. Some tests might be limited.")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(_Tests))
    runner = unittest.TextTestRunner(verbosity=2)
    rc = runner.run(suite)
    sys.exit(0 if rc.wasSuccessful() else 1)


# =============================================================================
# 5.  Entrypoint
# =============================================================================

def main():
    _setup_logging()
    args = _build_parser().parse_args()
    logging.info(f"Application started with arguments: {args}")

    if args.test:
        _run_tests()
        return

    try:
        _resolve_ffmpeg(args.ffmpeg_path)
    except SystemExit:
        if _tk and _messagebox:
            _messagebox.showerror("FFmpeg Error", "FFmpeg/FFprobe not found. Please see app_converter.log for details.")
        else:
            print("CRITICAL: FFmpeg/FFprobe not found. Check log.", file=sys.stderr)
        sys.exit(1)

    if _tk is None:
        logging.critical("Tkinter components not available. GUI cannot run.")
        print("CRITICAL ERROR: Tkinter is not installed or not working correctly.", file=sys.stderr)
        sys.exit(1)

    root_tk_instance = None
    try:
        if _TkDnD is not None:
            root_tk_instance = _TkDnD.Tk()
        else:
            root_tk_instance = _tk.Tk()
            logging.warning("TkinterDnD not available, drag and drop will not work.")
    except _tk.TclError as e:
        logging.critical(f"Failed to initialize Tkinter root window: {e}", exc_info=True)
        print(f"CRITICAL ERROR: Failed to initialize Tkinter root window: {e}", file=sys.stderr)
        sys.exit(1)

    if root_tk_instance:
        logging.info("Starting GUI.")
        _ConverterGUI(root_tk_instance, args)
        root_tk_instance.mainloop()
        logging.info("GUI mainloop finished.")


if __name__ == "__main__":
    main()