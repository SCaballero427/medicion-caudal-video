import pyorc
print(f"pyorc version: {pyorc.__version__}")

import inspect
print(f"Signature of pyorc.CameraConfig.set_gcps: {inspect.signature(pyorc.CameraConfig.set_gcps)}")