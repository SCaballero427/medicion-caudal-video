import cv2
import tkinter as tk
from tkinter import filedialog
import csv
import os

# -----------------------------
# Variables globales
# -----------------------------
points = []

frame_original = None
frame_annotated = None

window_name = "Primer frame del video"

# Parámetros de mapeo entre imagen mostrada y original
scale = 1.0
offset_x = 0
offset_y = 0
disp_w = 0
disp_h = 0


def fit_image_to_window(img, win_w, win_h):
    """
    Redimensiona la imagen para ajustarla a la ventana manteniendo aspecto.
    Devuelve:
      - imagen redimensionada con bordes negros
      - factor de escala
      - offset x/y dentro de la ventana
      - ancho/alto de la imagen mostrada
    """
    h, w = img.shape[:2]

    if win_w <= 1 or win_h <= 1:
        # Si la ventana aún no reporta tamaño válido, usar tamaño original
        return img.copy(), 1.0, 0, 0, w, h

    scale = min(win_w / w, win_h / h)
    new_w = int(w * scale)
    new_h = int(h * scale)

    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # Centrar con bordes negros
    top = (win_h - new_h) // 2
    bottom = win_h - new_h - top
    left = (win_w - new_w) // 2
    right = win_w - new_w - left

    bordered = cv2.copyMakeBorder(
        resized, top, bottom, left, right,
        borderType=cv2.BORDER_CONSTANT,
        value=(0, 0, 0)
    )

    return bordered, scale, left, top, new_w, new_h


def redraw_points():
    """
    Redibuja todos los puntos sobre el frame original.
    """
    global frame_annotated
    frame_annotated = frame_original.copy()

    for i, (x, y) in enumerate(points, start=1):
        cv2.circle(frame_annotated, (x, y), 5, (0, 0, 255), -1)
        text = f"{i}: ({x}, {y})"
        cv2.putText(
            frame_annotated,
            text,
            (x + 8, y - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 0, 0),
            2
        )


def mouse_callback(event, x, y, flags, param):
    global points, scale, offset_x, offset_y, disp_w, disp_h

    if event != cv2.EVENT_LBUTTONDOWN:
        return

    # Convertir coordenadas de la ventana (mostradas) a coordenadas de la imagen original
    img_x = x - offset_x
    img_y = y - offset_y

    # Ignorar clics sobre bordes negros o fuera de la imagen mostrada
    if img_x < 0 or img_y < 0 or img_x >= disp_w or img_y >= disp_h:
        return

    orig_x = int(img_x / scale)
    orig_y = int(img_y / scale)

    # Limitar por seguridad al tamaño real del frame
    h, w = frame_original.shape[:2]
    orig_x = max(0, min(orig_x, w - 1))
    orig_y = max(0, min(orig_y, h - 1))

    points.append((orig_x, orig_y))

    redraw_points()

    print(f"Punto {len(points)}: ({orig_x}, {orig_y})")


# -----------------------------
# Seleccionar video
# -----------------------------
root = tk.Tk()
root.withdraw()

video_path = filedialog.askopenfilename(
    title="Selecciona un video",
    filetypes=[
        ("Videos", "*.mp4 *.avi *.mov *.mkv *.wmv *.m4v"),
        ("Todos los archivos", "*.*")
    ]
)

if not video_path:
    print("No se seleccionó ningún video.")
    raise SystemExit

cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print("No se pudo abrir el video.")
    raise SystemExit

ret, frame_original = cap.read()
cap.release()

if not ret or frame_original is None:
    print("No se pudo leer el primer frame del video.")
    raise SystemExit

frame_annotated = frame_original.copy()

# -----------------------------
# Ventana redimensionable
# -----------------------------
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.resizeWindow(window_name, 1000, 700)
cv2.setMouseCallback(window_name, mouse_callback)

print("Instrucciones:")
print(" - Haz clic izquierdo para seleccionar puntos.")
print(" - Presiona 'z' para borrar el último punto.")
print(" - Presiona 'q' para terminar.")

while True:
    # Leer tamaño actual de la ventana
    try:
        _, _, win_w, win_h = cv2.getWindowImageRect(window_name)
    except:
        # Fallback si la función no está disponible
        win_w, win_h = frame_annotated.shape[1], frame_annotated.shape[0]

    # Ajustar imagen al tamaño actual de la ventana
    display_img, scale, offset_x, offset_y, disp_w, disp_h = fit_image_to_window(
        frame_annotated, win_w, win_h
    )

    cv2.imshow(window_name, display_img)

    key = cv2.waitKey(20) & 0xFF

    if key == ord('q'):
        break

    if key == ord('z') and len(points) > 0:
        points.pop()
        redraw_points()

cv2.destroyAllWindows()

# -----------------------------
# Guardar CSV con coordenadas originales
# -----------------------------
base_name = os.path.splitext(os.path.basename(video_path))[0]
csv_name = f"{base_name}_points.csv"

with open(csv_name, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Point", "X_px", "Y_px"])
    for i, (x, y) in enumerate(points, start=1):
        writer.writerow([i, x, y])

print(f"\nCoordenadas guardadas en: {csv_name}")

# -----------------------------
# Guardar imagen anotada del frame original
# -----------------------------
annotated_name = f"{base_name}_first_frame_annotated.png"
cv2.imwrite(annotated_name, frame_annotated)

print(f"Imagen anotada guardada en: {annotated_name}")
print("Listo.")