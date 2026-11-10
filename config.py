# -*- coding: utf-8 -*-
"""Configuración central de ASÍ TE GUSTA (prototipo académico).

TODOS los parámetros económicos y del experimento viven aquí. Ningún otro
archivo debe repetir estos valores. Los parámetros económicos también pueden
sobrescribirse desde el Modo investigador (se guardan en la tabla `settings`);
estos valores son los *predeterminados* de fábrica.
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Rutas (todo queda dentro de la carpeta del proyecto)
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("ATG_DB_PATH", BASE_DIR / "database" / "app.db"))
EXPORT_DIR = Path(os.environ.get("ATG_EXPORT_DIR", BASE_DIR / "data" / "exports"))
LOG_DIR = BASE_DIR / "data" / "logs"
MODELS_DIR = BASE_DIR / "models"
ASSETS_DIR = BASE_DIR / "assets"

# Versión web (Streamlit Community Cloud u otro servidor): la cámara es la del NAVEGADOR de quien la usa
# (st.camera_input), no la del servidor. Se activa sola en Streamlit Cloud o con ATG_WEB_MODE=1.
WEB_MODE = (os.environ.get("ATG_WEB_MODE", "").strip() == "1"
            or (BASE_DIR / ".web_mode").exists()                # lo crea tools/export_web.py
            or str(BASE_DIR).replace("\\", "/").startswith("/mount/src"))

# --------------------------------------------------------------------------
# Lanzador de Windows (acceso directo «ASÍ TE GUSTA»)
# --------------------------------------------------------------------------
APP_HOST = "127.0.0.1"
APP_PORT = 8501                          # si estuviera ocupado por OTRO programa, se usa el siguiente libre
WINDOW_TITLE = "Así te gusta"            # título de la ventana (para encontrarla/cerrarla)
AUTO_STOP_ON_WINDOW_CLOSE = True         # cerrar la ventana de la app = detener el servidor (tras la espera)
AUTO_STOP_GRACE_SECONDS = 10             # espera sin navegadores conectados antes de detenerlo

# --------------------------------------------------------------------------
# Identidad
# --------------------------------------------------------------------------
APP_NAME = "ASÍ TE GUSTA"
APP_NAME_TITLE = "Así te gusta"
TAGLINE = "Reconoce. Personaliza. Fideliza."
RESTAURANT_NAME = "Restaurante Demo"
ACADEMIC_NOTICE = ("Prototipo académico. Versión web de demostración: los datos se guardan temporalmente en el servidor "
                   "y pueden reiniciarse." if WEB_MODE else
                   "Prototipo académico. Los datos se almacenan únicamente de forma local.")

# --------------------------------------------------------------------------
# Modelo económico (valores DEMO, fáciles de cambiar)
# --------------------------------------------------------------------------
CURRENCY = "COP"
MONTHLY_PRICE = 250_000          # Plan A: mensualidad fija (COP / mes)
TOKEN_PRICE = 500                # Plan B: precio de 1 token (COP)
INITIAL_TOKEN_BALANCE = 500      # Saldo de tokens con el que arranca la demo
TOKEN_COOLDOWN_MINUTES = 30      # 1 token por cliente cada N minutos (visita)

# --------------------------------------------------------------------------
# Experimento
# --------------------------------------------------------------------------
# Contraseña DEMO del Modo investigador (se puede sobrescribir con la variable
# de entorno ATG_RESEARCHER_PASSWORD).
RESEARCHER_PASSWORD = os.environ.get("ATG_RESEARCHER_PASSWORD", "equipo5")
TARGET_PARTICIPANTS = 10
SUCCESS_TOKEN_MIN = 8            # >= 8 de 10 eligen tokens
SUCCESS_PILOT_MIN = 6            # >= 6 de 10 solicitan piloto
SESSION_PREFIX = "EXP"           # EXP-0001 ...
TEST_SESSION_PREFIX = "PRB"      # sesiones de ensayo: PRB-0001 ...
RANDOMIZE_CHOICE_ORDER = False   # True = alterna el orden de los botones de decisión
# True = cada participante nuevo empieza igual (saldo inicial, clientes demo restaurados, sin
# cooldown). Evita que el recorrido del participante anterior altere lo que ve el siguiente.
AUTO_RESET_ON_NEW_SESSION = True

# Simulador
PRESET_VOLUMES = [100, 300, 500, 800, 1000]
SIMULATOR_MAX_CUSTOMERS = 1_000_000
SIMULATOR_MAX_VISITS_PER_CUSTOMER = 60

CONCERN_OPTIONS = [
    "Privacidad",
    "Reconocimiento facial",
    "Instalación de cámaras",
    "Costo",
    "Consumo de tokens",
    "Integración con POS",
    "Internet",
    "Soporte",
    "Capacitación",
    "Otro",
]

# --------------------------------------------------------------------------
# Clientes / panel
# --------------------------------------------------------------------------
FREQUENT_MIN_VISITS = 5          # >= N visitas = "Cliente frecuente"
BIRTHDAY_WINDOW_DAYS = 30        # ventana de "próximos cumpleaños"

# Datos SIMULADOS del panel (se muestran siempre etiquetados como SIMULADO)
DEMO_MONTH_RECOGNITIONS = 346
DEMO_MONTH_RECURRING = 121
DEMO_MONTH_SALES = 4_200_000

# --------------------------------------------------------------------------
# Reconocimiento facial (OpenCV YuNet + SFace, 100 % local y en CPU)
# --------------------------------------------------------------------------
YUNET_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODELS_DIR / "face_recognition_sface_2021dec.onnx"
# Umbral de coincidencia: similitud coseno >= 0.363. Es el valor OFICIAL de OpenCV para SFace
# (tutorial «DNN-based Face Detection And Recognition», calibrado en LFW: 99,60 % de exactitud).
# Revisado en este equipo (ver tools/calibrate_threshold.py y FINAL_REPORT.md): la misma persona bajo
# luz/desenfoque/compresión/rotación distintos queda MUY por encima y una persona distinta MUY por
# debajo, así que se conserva. La documentación de OpenCV da 0.340 (CALFW) y 0.275 (CPLFW) para
# conjuntos más difíciles: si con su webcam hay falsos rechazos, bajar a ~0.30; si hubiera falsos
# positivos, subirlo gradualmente.
FACE_MATCH_THRESHOLD = 0.363
FACE_DETECT_SCORE = 0.80
FACE_ENROLL_MIN_SCORE = 0.90
FACE_MIN_SIZE_PX = 70            # tamaño mínimo de rostro (px, tras reescalar)
FACE_MAX_ENROLL_SAMPLES = 3      # muestras que se capturan automáticamente al registrar
ENROLL_CAPTURE_SECONDS = 25      # tiempo máximo de la captura de registro
ENROLL_SAMPLE_SPACING = 0.8      # segundos mínimos entre muestras (para variar pose/expresión)
CAMERA_INDEX = int(os.environ.get("ATG_CAMERA_INDEX", "0"))   # cámara preferida; si no entrega imagen se prueban 0..3
LIVE_SCAN_SECONDS = 20           # duración máxima del escaneo en vivo
LIVE_CONFIRM_FRAMES = 2          # coincidencias consecutivas para confirmar
