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
    """Gets sample rate (Hz) and bitrate (bps) of the first audio stream."""
    cmd = [
        _FFPROBE, "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "a:0", str(path)
    ]
    logging.debug(f"Executing ffprobe for metadata: {' '.join(cmd)}")
    sample_rate: Optional[int] = None
    bit_rate: Optional[int] = None

    try:
        process = _popen_run(cmd, capture_output=True, text=True, check=False, errors="ignore")

        if process.returncode != 0:
            stderr_output = process.stderr.strip() if process.stderr else "N/A"
            logging.error(
                f"ffprobe failed for metadata on {path}. Return code: {process.returncode}. Stderr: {stderr_output}",
                exc_info=False)
            return None, None

        if process.stdout is None:
            logging.error(f"ffprobe returned no stdout for metadata on {path}.")
            return None, None

        ffprobe_output = json.loads(process.stdout)
        if ffprobe_output and "streams" in ffprobe_output and len(ffprobe_output["streams"]) > 0:
            stream = ffprobe_output["streams"][0]

            sr_str = stream.get("sample_rate")
            if sr_str and sr_str.isdigit():
                sample_rate = int(sr_str)
            else:
                logging.warning(f"Could not parse sample_rate ('{sr_str}') for {path}.")

            br_str = stream.get("bit_rate")
            if br_str and br_str.isdigit():
                bit_rate = int(br_str)
            elif stream.get("codec_type") == "audio":
                # For lossless or uncompressed, bitrate might not be explicitly set in the same way
                # or might be very high. We are mostly interested for lossy codecs.
                if stream.get("codec_name") not in ["pcm_s16le", "pcm_s24le", "flac", "alac", "wavpack", "truehd",
                                                    "dts"]:  # Added more lossless
                    logging.warning(
                        f"Could not parse bit_rate ('{br_str}') for {path} (codec: {stream.get('codec_name')}). Will proceed without bitrate adjustment if needed.")
        else:
            logging.warning(f"No audio streams found or unexpected JSON structure for {path}.")

    except subprocess.CalledProcessError as e:
        stderr_output = e.stderr.strip() if isinstance(e.stderr, str) else e.stderr.decode(
            errors='ignore').strip() if isinstance(e.stderr, bytes) else 'N/A'
        logging.error(
            f"ffprobe execution failed for metadata on {path}. Return code: {e.returncode}. Stderr: {stderr_output}",
            exc_info=False)
    except json.JSONDecodeError:
        logging.error(f"Failed to decode ffprobe JSON output for {path}.", exc_info=True)
    except ValueError:  # Catches int() conversion errors if isdigit passed but value is problematic
        logging.error(f"ffprobe for {path} returned non-integer rate/bitrate.", exc_info=True)
    except Exception:
        logging.error(f"ffprobe encountered an unexpected error for metadata on {path}.", exc_info=True)

    return sample_rate, bit_rate


# =============================================================================
# 2.  Conversion function with automatic retry
# =============================================================================

def convert_to_432(src: Path, dst: Path, sr: int, original_bitrate_bps: Optional[int]) -> None:
    logging.info(f"Converting {src} to {dst} with target SR {sr}, original bitrate {original_bitrate_bps} bps")
    dst.parent.mkdir(parents=True, exist_ok=True)
    chain = f"asetrate={sr}*432/440,aresample={sr},atempo=440/432"

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
                    # Use original bitrate if it's lower than the target, convert to string 'XXXk' or raw bps
                    adjusted_options[b_a_idx + 1] = f"{orig_bps // 1000}k" if orig_bps % 1000 == 0 else str(orig_bps)
                    logging.info(
                        f"Adjusting target bitrate from {target_br_str} to original {adjusted_options[b_a_idx + 1]} for {src.name}")
                elif target_bps == -1:
                    logging.warning(
                        f"Could not parse target bitrate '{target_br_str}' from codec options for {src.name}.")
            else:
                logging.warning(f"Malformed codec options: '-b:a' found without a value for {src.name}.")
        except ValueError:  # '-b:a' not in list or int() conversion failed
            pass  # No bitrate option to adjust, or it's not in a parseable format
        except Exception as e_br_adj:
            logging.error(f"Error adjusting bitrate for {src.name}: {e_br_adj}", exc_info=True)
        return adjusted_options

    base_cmd_list = [
        _FFMPEG, "-y", "-i", str(src),
        "-map", "0:a?", "-map", "0:v?", "-c:v", "copy",  # Keep video stream if present
        "-af", chain,
    ]
    ext = dst.suffix.lower()

    hq_options_base = _codec_for_ext(ext, safe=False)
    if ext not in [".flac", ".wav"]:  # Bitrate adjustment mainly for lossy
        hq_options_final = _adjust_bitrate_in_options(hq_options_base, original_bitrate_bps)
    else:
        hq_options_final = hq_options_base

    hq_cmd_list = base_cmd_list + hq_options_final + [str(dst)]
    proc = _run(hq_cmd_list)

    if proc.returncode == 0:
        logging.info(f"Successfully converted {src.name} (HQ settings) to {dst.name}")
        return

    hq_stderr_cleaned = _clean_ffmpeg_err(proc.stderr) if proc.stderr is not None else "(no ffmpeg stderr captured)"
    logging.warning(
        f"HQ conversion failed for {src.name}. Return code: {proc.returncode}. Error:\n{hq_stderr_cleaned}")

    safe_options_base = _codec_for_ext(ext, safe=True)
    if ext not in [".flac", ".wav"]:
        safe_options_final = _adjust_bitrate_in_options(safe_options_base, original_bitrate_bps)
    else:
        safe_options_final = safe_options_base

    safe_cmd_list = base_cmd_list + safe_options_final + [str(dst)]
    proc_safe = _run(safe_cmd_list)
    if proc_safe.returncode == 0:
        logging.info(f"Successfully converted {src.name} (Safe preset) to {dst.name} after HQ failed.")
        return

    safe_stderr_cleaned = _clean_ffmpeg_err(
        proc_safe.stderr) if proc_safe.stderr is not None else "(no ffmpeg stderr captured)"
    logging.error(
        f"Safe conversion also failed for {src.name}. Return code: {proc_safe.returncode}. Error:\n{safe_stderr_cleaned}")
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
        _DND_FILES = "Files"  # Fallback for type hinting if needed, not functional
else:
    _TkDnD = None
    _DND_FILES = "Files"


def _parse_drop_data(data: str) -> Optional[Path]:
    if not data: return None
    s = data.strip()
    # Handle paths wrapped in {} or just plain paths
    if s.startswith("{") and s.endswith("}") and len(s) > 1: s = s[1:-1].strip()
    if not s: return None
    # Further sanitize if multiple files are dropped (common on some OS, take first)
    # This is a simple approach; more robust parsing might be needed for complex drop data
    if '\n' in s: s = s.split('\n')[0].strip()
    if not Path(s).exists():  # Basic check if path seems plausible before returning
        logging.warning(f"Parsed drop data '{s}' does not exist as a path.")
        # Optionally, try to handle if it's a list of quoted paths, e.g. "path1" "path2"
        # For now, keeping it simple.
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
                    logging.warning(f"Initial source folder from argument is not a valid directory: {self.args.folder}")
                    _messagebox.showwarning("Warning",
                                            f"The provided source folder is not a valid directory:\n{self.args.folder}")

            if self.args.outdir:
                p_out = Path(self.args.outdir).resolve()
                # No need to check is_dir for output, it will be created
                self._set_out(p_out)
            elif self.src and not self.var_out.get():  # Auto-suggest output if src is set and output is empty
                self._set_out(self.src.parent / f"{self.src.name}_432Hz")

        def _browse_src(self):
            try:
                d = _filedialog.askdirectory(title="Select Source Folder")
                if d: self._set_src(Path(d))
            except Exception as e:
                logging.error("Error browsing for source folder.", exc_info=True)
                _messagebox.showerror("Error", f"Failed to select source folder:\n{e}")

        def _browse_out(self):
            try:
                d = _filedialog.askdirectory(title="Select Output Base Folder")
                if d: self._set_out(Path(d))
            except Exception as e:
                logging.error("Error browsing for output folder.", exc_info=True)
                _messagebox.showerror("Error", f"Failed to select output folder:\n{e}")

        def _ondrop_src(self, event):
            p = _parse_drop_data(event.data)
            if p and p.is_dir():
                self._set_src(p)
            elif p:  # Dropped item was parsed but not a directory
                logging.warning(f"Dropped item is not a directory: {p}")
                _messagebox.showwarning("Invalid Drop", "Please drop a folder, not a file.")
            else:  # Dropped item could not be parsed or was empty
                logging.warning(f"Failed to parse dropped data: {event.data}")
                _messagebox.showerror("Drop Error", "Could not understand the dropped item.")

        def _set_src(self, p: Path):
            self.src = p.resolve()
            self.var_src.set(str(self.src))
            if not self.var_out.get() and self.src.is_dir():  # If output is empty, suggest one
                self._set_out(self.src.parent / f"{self.src.name}_432Hz")

        def _set_out(self, p: Path):
            self.dst_base = p.resolve()  # Resolve to make it an absolute path
            self.var_out.set(str(self.dst_base))

        def _start(self):
            logging.info("GUI: Start button clicked.")
            if self.thread and self.thread.is_alive():
                logging.warning("GUI: Conversion already in progress.")
                _messagebox.showwarning("Busy", "Conversion is already in progress.")
                return

            if not self.src or not self.src.exists() or not self.src.is_dir():
                logging.error("GUI: Invalid source folder.")
                _messagebox.showerror("Error", "Please select a valid source folder.")
                return

            if not self.var_out.get():  # Check if output field is empty
                logging.error("GUI: Output folder not set.")
                _messagebox.showerror("Error", "Please select an output folder.")
                return
            else:  # Ensure self.dst_base is set from the potentially user-edited field
                self.dst_base = Path(self.var_out.get()).resolve()

            if self.dst_base:  # dst_base should always be set if var_out.get() was true
                try:
                    self.dst_base.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    logging.error(f"GUI: Cannot create output folder {self.dst_base}", exc_info=True)
                    _messagebox.showerror("Error", f"Cannot create output folder:\n{self.dst_base}\n{e}")
                    return
            else:  # Should not happen if logic above is correct
                logging.error("GUI: Output folder path is somehow not defined.")
                _messagebox.showerror("Error", "Output folder path is not defined.")
                return

            logging.info("GUI: Starting conversion worker thread.")
            self.btn.config(state="disabled")
            self.bar["value"] = 0
            self.thread = threading.Thread(target=self._worker, daemon=True)
            setattr(self.thread, 'error_occurred_worker', False)  # Custom attribute to track errors
            self.thread.start()
            self._poll()

        def _poll(self):
            if self.thread and self.thread.is_alive():
                self.root.after(200, self._poll)
            else:
                self.btn.config(state="normal")
                # Check custom error flag from worker thread
                worker_had_errors = self.thread and hasattr(self.thread, 'error_occurred_worker') and getattr(
                    self.thread, 'error_occurred_worker')

                if worker_had_errors:
                    logging.info("GUI: Poll detected worker finished with errors.")
                    # Optionally, show a generic error message or rely on per-file messages
                    # _messagebox.showwarning("Done", "Conversion finished, but some files had errors. Check log.")
                elif self.bar["maximum"] == 0 and self.bar["value"] == 0:  # No files processed
                    logging.info("GUI: Poll detected worker finished (no files found or processed).")
                    # No message needed here as _worker shows "No supported audio files found."
                elif self.bar["value"] == self.bar["maximum"] and self.bar[
                    "maximum"] > 0:  # All files processed successfully
                    logging.info("GUI: Poll detected worker finished successfully.")
                    _messagebox.showinfo("Done", f"Conversion complete!\nFiles are in: {self.dst_base}")
                else:  # Interrupted or unexpected state
                    logging.info("GUI: Poll detected worker finished (state indeterminate or interrupted).")

                self.bar["value"] = 0  # Reset progress bar

        def _worker(self):
            assert self.src and self.dst_base, "Source or destination base not set in worker"
            logging.info(
                f"GUI Worker: Started. Source: {self.src}, DestBase: {self.dst_base}, Recursive: {self.rec.get()}, Keep: {self.keep.get()}")

            worker_errors = False
            try:
                files = find_audio_files(self.src, self.rec.get())
                total = len(files)
                logging.info(f"GUI Worker: Found {total} audio files.")

                if not total:
                    self.root.after(0, lambda: _messagebox.showinfo("Info", "No supported audio files found."))
                    self.bar.config(maximum=0, value=0)  # Ensure bar reflects no work
                    return

                self.bar.config(maximum=total)

                for idx, f_path in enumerate(files, 1):
                    # Check if thread should continue (e.g., if GUI is closing)
                    if not (
                            self.thread and self.thread.is_alive()):  # A bit redundant if daemon=True, but good for explicit stop
                        logging.warning("GUI Worker: Thread interruption detected.")
                        worker_errors = True  # Mark that we didn't finish all files
                        break

                    ext_out = ".mp3" if f_path.suffix.lower() == ".wma" else f_path.suffix
                    codec_suffix = ext_out  # User selected this line, keeping it.
                    self.root.after(0, lambda current_idx=idx: self.bar.config(value=current_idx))  # Update progress

                    rel_path = f_path.relative_to(self.src)
                    dst_file = self.dst_base / rel_path.parent / f"{f_path.stem}_432{ext_out}"

                    try:
                        dst_file.parent.mkdir(parents=True, exist_ok=True)
                    except OSError as e_mkdir:
                        logging.error(f"GUI Worker: Error creating directory for {dst_file.name}: {e_mkdir}",
                                      exc_info=True)
                        self.root.after(0,
                                        lambda file_name=dst_file.name, err_msg=str(e_mkdir): _messagebox.showerror(
                                            "File Error",
                                            f"Could not create directory for:\n{file_name}\n\n{err_msg}"))
                        worker_errors = True
                        continue

                    if self.keep.get() and dst_file.exists() and dst_file.stat().st_size > 0:
                        logging.info(f"GUI Worker: Skipping existing file: {dst_file}")
                        continue

                    logging.info(f"GUI Worker: Processing {f_path} -> {dst_file}")
                    original_sample_rate, original_bitrate = _get_audio_metadata(f_path)

                    if original_sample_rate is None:
                        logging.warning(f"GUI Worker: Could not get sample rate for {f_path.name}, skipping.")
                        self.root.after(0, lambda p_name=f_path.name: _messagebox.showwarning("Skipped",
                                                                                              f"Could not get metadata for:\n{p_name}\nSkipping conversion."))
                        worker_errors = True
                        continue

                    target_sample_rate = 48000  # Default target SR for resampling consistency

                    try:
                        convert_to_432(f_path, dst_file, target_sample_rate, original_bitrate)
                        logging.info(f"GUI Worker: Successfully converted {f_path.name} to {dst_file.name}")
                    except subprocess.CalledProcessError as e_conv:
                        # stderr from CalledProcessError is already cleaned by convert_to_432's final raise
                        logging.error(f"GUI Worker: Conversion failed for {f_path.name}: {e_conv.stderr}",
                                      exc_info=False)
                        self.root.after(0, lambda p_name=f_path.name, err_details=e_conv.stderr: _messagebox.showerror(
                            "Conversion Error", f"Failed to convert:\n{p_name}\n\nError:\n{err_details}"))
                        worker_errors = True
                    except Exception as e_conv_generic:
                        logging.error(f"GUI Worker: Unexpected error converting {f_path.name}: {e_conv_generic}",
                                      exc_info=True)
                        self.root.after(0, lambda p_name=f_path.name, err_details=str(
                            e_conv_generic): _messagebox.showerror("Conversion Error",
                                                                   f"Unexpected error converting:\n{p_name}\n\nError:\n{err_details}"))
                        worker_errors = True

                # After the loop
                if not worker_errors and total > 0:  # All files processed without error
                    self.root.after(0, lambda: self.bar.config(value=total))  # Ensure bar is full

                if worker_errors:  # If any error occurred during the loop
                    setattr(self.thread, 'error_occurred_worker', True)


            except Exception as e_outer:  # Catch-all for unexpected errors in the worker's main try block
                logging.critical(f"GUI Worker: Unhandled exception in worker thread: {e_outer}", exc_info=True)
                self.root.after(0, lambda err_msg=str(e_outer): _messagebox.showerror("Critical Worker Error",
                                                                                      f"A critical error occurred in the conversion process:\n{err_msg}"))
                setattr(self.thread, 'error_occurred_worker', True)  # Signal error to poll
            finally:
                logging.info(f"GUI Worker: Finished. Errors occurred: {worker_errors}")
                # Ensure the error status is set on the thread object if not already
                if worker_errors and self.thread and not getattr(self.thread, 'error_occurred_worker', False):
                    setattr(self.thread, 'error_occurred_worker', True)


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
        # Test WMA to ensure it's defined
        self.assertTrue(_codec_for_ext(".wma"))
        self.assertTrue(_codec_for_ext(".wma", safe=True))

    def test_parse_drop_data(self):
        # Create dummy files/dirs for Path(s).exists() check in _parse_drop_data if strict
        # For now, assuming _parse_drop_data might not always check existence or test env handles it
        Path("./tmp_test_dir").mkdir(exist_ok=True)
        Path("./tmp_test_file.txt").touch(exist_ok=True)

        self.assertEqual(_parse_drop_data("{./tmp_test_dir}"), Path("./tmp_test_dir"))
        self.assertEqual(_parse_drop_data("./tmp_test_dir"), Path("./tmp_test_dir"))
        # self.assertEqual(_parse_drop_data("{C:/Program Files/My App}"), Path("C:/Program Files/My App")) # OS specific
        self.assertEqual(_parse_drop_data("  {./tmp_test_dir}  "), Path("./tmp_test_dir"))
        self.assertIsNone(_parse_drop_data(""))
        self.assertIsNone(_parse_drop_data("   "))
        self.assertIsNone(_parse_drop_data("{}"))
        self.assertIsNone(_parse_drop_data("{ }"))
        # Test with a file path, should return None if only dirs are expected by caller, but parser might allow
        # self.assertEqual(_parse_drop_data("./tmp_test_file.txt"), Path("./tmp_test_file.txt"))

        # Cleanup
        Path("./tmp_test_file.txt").unlink(missing_ok=True)
        Path("./tmp_test_dir").rmdir()


def _run_tests():
    logging.info("Running self-tests...")
    try:
        _resolve_ffmpeg(None)  # Basic check that resolver runs
    except SystemExit:
        logging.warning(
            "FFmpeg/FFprobe not found during test setup for _resolve_ffmpeg. Some tests might be limited but will proceed.")
        # Don't exit here, let other tests run if possible

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(_Tests))
    runner = unittest.TextTestRunner(verbosity=2)
    rc = runner.run(suite)
    logging.info(f"Self-tests completed. Success: {rc.wasSuccessful()}")
    sys.exit(0 if rc.wasSuccessful() else 1)


# =============================================================================
# 5.  Entrypoint
# =============================================================================

def main():
    _setup_logging()  # Initialize logging first
    args = _build_parser().parse_args()
    logging.info(f"Application started with arguments: {args}")

    if args.test:
        _run_tests()
        return  # Exit after tests

    try:
        _resolve_ffmpeg(args.ffmpeg_path)
    except SystemExit:  # _resolve_ffmpeg calls sys.exit(1) on failure
        # This error is already logged by _resolve_ffmpeg
        if _tk and _messagebox:  # If GUI components are available, show message box
            _messagebox.showerror("FFmpeg Error",
                                  "FFmpeg/FFprobe not found or not configured correctly. Please see app_converter.log for details. The application will now exit.")
        else:  # Fallback to console if Tkinter isn't loaded/failed
            print("CRITICAL: FFmpeg/FFprobe not found. Check log. Exiting.", file=sys.stderr)
        logging.critical("Exiting due to FFmpeg resolution failure caught in main.")
        sys.exit(1)  # Ensure exit if SystemExit was caught from _resolve_ffmpeg

    if _tk is None or _ttk is None or _filedialog is None or _messagebox is None:
        logging.critical("Tkinter components (tk, ttk, filedialog, messagebox) not available. GUI cannot run.")
        print(
            "CRITICAL ERROR: Tkinter is not installed or not working correctly.\n"
            "This application requires Tkinter for its graphical interface.\n"
            "Please ensure Python's Tkinter module is installed and functional.",
            file=sys.stderr
        )
        sys.exit(1)

    root_tk_instance = None
    try:
        if _TkDnD is not None:
            root_tk_instance = _TkDnD.Tk()
            logging.info("TkinterDnD available, using TkinterDnD.Tk().")
        else:
            root_tk_instance = _tk.Tk()
            logging.warning(
                "TkinterDnD not available, using standard tk.Tk(). Drag and drop for source folder will not work.")
            if _messagebox:  # Show a non-critical warning if messagebox is available
                _messagebox.showwarning("Drag and Drop Unavailable",
                                        "The tkinterdnd2 library was not found. Drag and drop for the source folder will be disabled.")
    except _tk.TclError as e:
        logging.critical(f"Failed to initialize Tkinter root window: {e}", exc_info=True)
        print(f"CRITICAL ERROR: Failed to initialize Tkinter root window: {e}", file=sys.stderr)
        sys.exit(1)

    if root_tk_instance:
        logging.info("Starting GUI.")
        _ConverterGUI(root_tk_instance, args)
        root_tk_instance.mainloop()
        logging.info("GUI mainloop finished.")
    else:  # Should not be reached if TclError is caught
        logging.critical("Tkinter root instance is None after attempting creation. GUI cannot run.")
        print("CRITICAL ERROR: Failed to create Tkinter root window. The application cannot run.", file=sys.stderr)
        sys.exit(1)

    logging.info("Application finished.")


if __name__ == "__main__":
    main()