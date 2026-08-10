import sys
import subprocess
import imageio_ffmpeg

def run_diagnostic():
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        print(f"FFmpeg path: {ffmpeg_exe}")
        
        # Test ffmpeg execution explicitly mapping version limits natively
        subprocess.run([ffmpeg_exe, "-version"], check=True, capture_output=True)
        print("FFmpeg: PASS")
        
        # Determine ffprobe explicitly
        ffprobe_exe = ffmpeg_exe.replace("ffmpeg", "ffprobe")
        subprocess.run([ffprobe_exe, "-version"], check=True, capture_output=True)
        print("FFprobe: PASS")
    except Exception as e:
        print(f"Error accessing bindings: {e}")
        print("FFmpeg: FAIL")
        print("FFprobe: FAIL")

if __name__ == "__main__":
    run_diagnostic()
