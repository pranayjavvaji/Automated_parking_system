import cv2
import numpy as np
import subprocess
import sqlite3
import re
import time

# --- CONFIGURATION ---
FFMPEG_PATH = r"C:\Users\javva\Downloads\Final_year_project\ffmpeg\bin\ffmpeg.exe"
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
FRAME_SIZE = FRAME_WIDTH * FRAME_HEIGHT * 3  # Raw BGR size

def get_rtsp_url():
    """Fetch the first camera URL from database"""
    try:
        conn = sqlite3.connect('parking_system.db')
        cursor = conn.cursor()
        cursor.execute("SELECT stream_url, username, password FROM dvr_devices LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            print("❌ Error: Database is empty (no DVR found).")
            return None
            
        raw_url, username, password = row
        print(f"🔹 Found DB Entry: {raw_url}")

        # Basic SmartPSS Parsing Logic
        if "rtsp://" in raw_url:
            return raw_url
            
        # Extract ports
        rtsp_match = re.search(r'rtspport=(\d+)', raw_url)
        if rtsp_match:
            port = rtsp_match.group(1)
        else:
            # Fallback for some URL formats
            port = "554" 
            print("⚠️ Warning: Could not find 'rtspport', guessing 554")

        # Construct URL (Assuming localhost tunnel)
        final_url = f"rtsp://{username}:{password}@127.0.0.1:{port}/cam/realmonitor?channel=1&subtype=0"
        return final_url

    except Exception as e:
        print(f"❌ Database Error: {e}")
        return None

def run_test():
    rtsp_url = get_rtsp_url()
    if not rtsp_url:
        return

    print(f"🚀 Connecting to: {rtsp_url}")

    # FFmpeg Command
    command = [
        FFMPEG_PATH,
        '-rtsp_transport', 'tcp',
        '-i', rtsp_url,
        '-f', 'image2pipe',
        '-pix_fmt', 'bgr24',
        '-vcodec', 'rawvideo',
        '-an',
        '-r', '15',
        '-s', f'{FRAME_WIDTH}x{FRAME_HEIGHT}',
        '-'
    ]

    try:
        # Start FFmpeg
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**7
        )
        print("✅ FFmpeg process started. Waiting for frames...")
    except Exception as e:
        print(f"❌ Failed to start FFmpeg: {e}")
        return

    # Loop to read frames
    try:
        while True:
            # Read raw bytes
            raw_frame = process.stdout.read(FRAME_SIZE)

            if len(raw_frame) != FRAME_SIZE:
                print("⚠️ Incomplete frame or stream ended. Retrying...")
                # Optional: Read stderr to see why it failed
                # error_log = process.stderr.read(1000)
                # print(f"FFmpeg Error Log: {error_log}")
                time.sleep(0.1)
                continue

            # Convert to Image
            frame = np.frombuffer(raw_frame, dtype=np.uint8)
            frame = frame.reshape((FRAME_HEIGHT, FRAME_WIDTH, 3))

            # --- DEBUG DRAWING ---
            # Draw a circle so we know it's live
            cv2.circle(frame, (50, 50), 20, (0, 255, 0), -1)
            cv2.putText(frame, "LIVE TEST", (80, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # Show the window
            cv2.imshow("Debug Stream", frame)

            # Press 'q' to quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        process.terminate()
        cv2.destroyAllWindows()
        print("✅ Test finished.")

if __name__ == "__main__":
    run_test()