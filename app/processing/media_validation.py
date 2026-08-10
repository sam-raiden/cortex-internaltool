import os
import av

class MediaValidator:
    @staticmethod
    def validate_video(file_path: str) -> bool:
        if not os.path.exists(file_path):
            print(f"Validation failed: File missing -> {file_path}")
            return False
            
        size = os.path.getsize(file_path)
        if size < 1024:
            print(f"Validation failed: Size too small ({size} bytes) -> {file_path}")
            return False
            
        try:
            # PyAV container detection natively simulating ffprobe constraints
            with av.open(file_path) as container:
                # Check Duration mapped in PyAV microsecond scale mapping logically > 0
                if container.duration is None or container.duration <= 0:
                    print(f"Validation failed: Invalid duration -> {file_path}")
                    return False
                    
                # Check stream boundaries mapping actual Audio / Video limits securely
                has_audio = False
                for stream in container.streams:
                    if stream.type == 'audio':
                        has_audio = True
                        break
                        
                if not has_audio:
                    print(f"Validation failed: No audio stream found -> {file_path}")
                    return False
                    
            return True
        except Exception as e:
            print(f"Validation failed: PyAV structural rejection -> {file_path} - {e}")
            return False
