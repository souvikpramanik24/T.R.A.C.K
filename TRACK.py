from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import time
import os
import signal
from datetime import datetime

app = Flask(__name__)
CORS(app)

# =====================================================================
# Configuration
# =====================================================================

SCRCPY_PATH = r"C:\Tools for new system\scrcpy-win64-v2.4\scrcpy-win64-v3.3.1-bmw\scrcpy.exe"
ADB_PATH = r"C:\Tools for new system\scrcpy-win64-v2.4\scrcpy-win64-v3.3.1-bmw\adb.exe"

# Track active recordings
# Structure:
# {
#   display_id: {
#       "process": process,
#       "temp_file": temp_mp4_file,
#       "folder_name": target_folder,
#       "ecu": ecu_name,
#       "display_name": display_name_clean,
#       "start_time_str": timestamp
#   }
# }
active_recordings = {}

# =====================================================================
# Start Recording
# =====================================================================

@app.route('/start', methods=['POST'])
def start_recording():
    data = request.json
    
    ecu = data.get('ecu', 'UnknownECU')
    software_version = data.get('software_version', 'UnknownVer')
    displays = data.get('displays', [])

    if not displays:
        return jsonify({"error": "No display IDs provided"}), 400

    # Sanitize the folder name
    safe_sw_ver = "".join(c for c in software_version if c.isalnum() or c in ".-_")
    safe_ecu = "".join(c for c in ecu if c.isalnum() or c in ".-_")
    folder_name = f"{safe_ecu}_{safe_sw_ver}"

    # Create the target directory if it doesn't exist
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    # Generate start timestamp: HHMMSSDDMMYYYY
    start_time_str = datetime.now().strftime("%H%M%S%d%m%Y")
    started_displays = []

    for disp in displays:
        d_id = str(disp.get('id'))
        
        # Clean up the display name for the filename (e.g., "PHUD-Driver" -> "PHUD_Driver")
        raw_name = disp.get('name', f'Disp{d_id}')
        d_name = raw_name.replace(' ', '_').replace('-', '_')
        d_name = "".join(c for c in d_name if c.isalnum() or c == '_')

        if d_id in active_recordings:
            continue

        # Use a temporary filename while recording is active
        temp_filename = os.path.join(folder_name, f"temp_recording_disp{d_id}_{start_time_str}.mp4")

        cmd = [
            SCRCPY_PATH,
            "--display-id", str(d_id),
            "--no-playback",
            "--video-bit-rate", "2M",
            "--max-fps", "30",
            "--max-size", "1280",
            "--record", temp_filename
        ]

        try:
            # Set up startupinfo to completely hide the new console window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0 # SW_HIDE

            # CREATE_NEW_CONSOLE ensures the process can receive graceful Windows close messages
            process = subprocess.Popen(
                cmd,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Instantly register the process and metadata
            active_recordings[d_id] = {
                "process": process,
                "temp_file": temp_filename,
                "folder_name": folder_name,
                "ecu": safe_ecu,
                "display_name": d_name,
                "start_time_str": start_time_str
            }
            
            started_displays.append(d_id)
            print(f"[STARTED] Display {d_id} -> {temp_filename}")
            
            # Give ADB 1.5 seconds to push the server to the vehicle
            time.sleep(1.5)

        except Exception as e:
            print(f"[ERROR] Failed to start display {d_id}: {e}")

    return jsonify({
        "status": "recording started",
        "displays_started": started_displays
    }), 200

# =====================================================================
# Stop Recording
# =====================================================================

@app.route('/stop', methods=['POST'])
def stop_recording():
    stopped_displays = []

    # 1. Send an ADB command to kill the scrcpy server on the Android side.
    try:
        subprocess.run(
            [ADB_PATH, "shell", "pkill", "-f", "scrcpy.Server"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"[WARNING] ADB pkill failed: {e}")

    # Generate end timestamp: HHMMSSDDMMYYYY
    end_time_str = datetime.now().strftime("%H%M%S%d%m%Y")

    # 2. Cleanup, verify Windows processes, and rename files
    for d_id, recording_info in list(active_recordings.items()):
        process = recording_info["process"]
        temp_file = recording_info["temp_file"]

        try:
            print(f"[STOPPING] Display {d_id} - Finalizing MP4...")

            # Polite Windows taskkill
            subprocess.run(
                ["taskkill", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            try:
                # Wait up to 10 seconds for scrcpy to finish writing the MP4 moov atom
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print(f"[WARNING] Graceful stop timed out for display {d_id}. Force killing.")
                process.kill()
                process.wait()

            # If the temp file saved successfully, rename it to the final format
            if os.path.exists(temp_file):
                final_filename = os.path.join(
                    recording_info["folder_name"],
                    f"{recording_info['ecu']}_{recording_info['display_name']}_{recording_info['start_time_str']}_{end_time_str}.mp4"
                )
                
                # os.replace handles renaming cleanly even on Windows
                os.replace(temp_file, final_filename)
                
                size_mb = os.path.getsize(final_filename) / (1024 * 1024)
                print(f"[SUCCESS] MP4 saved: {final_filename} ({size_mb:.2f} MB)")

            stopped_displays.append(d_id)

        except Exception as e:
            print(f"[ERROR] Failed stopping display {d_id}: {e}")

    active_recordings.clear()

    return jsonify({
        "status": "recordings stopped",
        "displays": stopped_displays
    }), 200

# =====================================================================
# Main
# =====================================================================

if __name__ == '__main__':
    try:
        subprocess.run(
            [ADB_PATH, "root"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"[WARNING] adb root failed: {e}")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )