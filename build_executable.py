import PyInstaller.__main__
import os
import shutil
from pathlib import Path

# --- CONFIGURATION ---
# The name of your main python script.
MAIN_SCRIPT = "main.py"

# The name you want for your final .exe file.
EXE_NAME = "AudioConverter432"


# --- END OF CONFIGURATION ---


def find_ffmpeg_bin_directory(start_path: Path) -> Path | None:
    """
    Scans the starting path for a directory starting with 'ffmpeg-'
    and returns the 'bin' subdirectory within it.
    """
    print("Searching for FFmpeg directory...")
    for item in start_path.iterdir():
        if item.is_dir() and item.name.startswith("ffmpeg-"):
            print(f"Found potential FFmpeg folder: '{item.name}'")
            bin_path = item / "bin"
            if bin_path.exists() and bin_path.is_dir():
                print(f"Found 'bin' directory at: '{bin_path}'")
                return bin_path
    return None


def create_executable():
    """
    Uses PyInstaller to bundle the Python script and its assets
    into a single standalone executable file.
    """
    print("--- Starting Executable Build ---")

    project_dir = Path(__file__).parent
    main_script_path = project_dir / MAIN_SCRIPT

    if not main_script_path.exists():
        print(f"ERROR: Main script '{MAIN_SCRIPT}' not found. Please ensure it is in the same directory.")
        return

    # 1. Clean up previous builds
    print("\n1. Cleaning up previous build artifacts...")
    for folder in ["build", "dist"]:
        if (project_dir / folder).exists():
            shutil.rmtree(project_dir / folder)
    spec_file = project_dir / f"{EXE_NAME}.spec"
    if spec_file.exists():
        spec_file.unlink()

    # 2. Find the FFmpeg 'bin' directory automatically
    print("\n2. Locating FFmpeg assets...")
    ffmpeg_bin_path = find_ffmpeg_bin_directory(project_dir)

    if not ffmpeg_bin_path:
        print("\nERROR: Could not find the FFmpeg 'bin' directory.")
        print("Please make sure the unzipped FFmpeg folder (e.g., 'ffmpeg-master-latest...')")
        print("is placed in the same directory as this build script.")
        return

    # 3. Prepare the PyInstaller command
    pyinstaller_command = [
        str(main_script_path),
        "--noconfirm",
        "--onefile",
        "--windowed",
        f"--name={EXE_NAME}",
    ]

    # Add the entire contents of the 'bin' folder to the executable's root.
    # This includes ffmpeg.exe, ffprobe.exe, and all required .dll files.
    print(f"\n3. Bundling all files from '{ffmpeg_bin_path}'...")
    pyinstaller_command.append(f"--add-data={ffmpeg_bin_path}{os.pathsep}.")

    # 4. Run PyInstaller
    print("\n4. Running PyInstaller... (This may take a moment)")
    print(f"   Command: pyinstaller {' '.join(pyinstaller_command)}")

    try:
        PyInstaller.__main__.run(pyinstaller_command)
        output_path = project_dir / "dist" / f"{EXE_NAME}.exe"
        print("\n--- Build Successful! ---")
        print(f"Executable is located at: {output_path.resolve()}")
    except Exception as e:
        print(f"\n--- An Error Occurred During Build ---")
        print(f"PyInstaller failed with the following error: {e}")


if __name__ == "__main__":
    create_executable()