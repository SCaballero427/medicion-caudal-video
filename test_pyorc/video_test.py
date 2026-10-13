import cv2
from pathlib import Path

ARCHIVO_VIDEO = Path(r"C:\Users\Sergio\Documents\test_pyorc\RIVeR_Example\GOPR3225_Trim.mp4")
cap = cv2.VideoCapture(str(ARCHIVO_VIDEO))

fps = cap.get(cv2.CAP_PROP_FPS)
nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

print(f"FPS: {fps}")
print(f"Number of frames: {nframes}")

cap.release()