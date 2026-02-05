from picamera2 import Picamera2
from importlib import import_module

# 1. Initialize Picamera2
picam2 = Picamera2()

# 2. Configure the camera for the IMX500
# The IMX500 usually operates at specific resolutions for its onboard ISP
config = picam2.create_preview_configuration(main={"format": "YUV420", "size": (1920, 1080)})
picam2.configure(config)

# 3. Start the camera hardware
picam2.start()

print("Camera preview started. Press Ctrl+C to stop.")

try:
    # 4. Open a preview window (Qt-based)
    picam2.start_preview(title="IMX500 Preview")
    
    # Keep the script running while the preview is open
    while True:
        pass

except KeyboardInterrupt:
    print("\nStopping camera...")
finally:
    picam2.stop_preview()
    picam2.stop()