# 🚀 Jarvis - Agenda & Productividad Personal

**Jarvis** es una aplicación web ligera, reactiva y táctica construida con **Python (Flask)** y **SQLite**, diseñada con una estética de primer nivel en **Dark Mode (Grises profundos, Glassmorphism y Neón)**. Está optimizada tanto para escritorio como para encapsulación en una **APK móvil**.

---

## 🌟 Características Principales

### 1. 💼 🏠 🩺 🏃‍♂️ 4 Áreas de Enfoque Centralizadas
- **💼 Trabajo y Proyectos:** Prioridades Top 3 del día y tareas operativas.
- **🏠 Casa:** Mantenimiento del hogar, logística doméstica y espacios.
- **🩺 Salud y Bienestar:** Hábitos saludables, entrenamientos, hidratación, chequeos médicos y suplementos.
- **🏃‍♂️ Diligencias y Calle:** Tareas rápidas fuera de casa (compras, gestiones, envíos).

### 2. 📊 Dashboard de Productividad y Gamificación
- **Contador y porcentaje en tiempo real** de tareas completadas por categoría.
- **Barra de progreso del día** con gradiente cian a esmeralda.
- **Racha de cumplimiento activa (🔥 Streak Counter):** Mide los días consecutivos completando metas clave.
- **Top 3 Prioridades del Día:** Módulo destacado para mantener el foco en lo no negociable.

### 3. 🎙️ Captura por Voz & Webhook Automatizado (`POST /api/quick-add`)
Permite conectar Jarvis directamente con **Google Assistant**, **Gemini**, **n8n**, **Tasker** o **Atajos de iOS/Android** para dictar tareas en movimiento con auto-categorización inteligente.

```bash
curl -X POST "http://127.0.0.1:5000/api/quick-add" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: jarvis-voice-2026" \
  -d '{
    "text": "Comprar café en la esquina",
    "category": "errands"
  }'
```

---

## 📱 Encapsulación en APK Móvil (PWA / WebView / Capacitor)
Jarvis incluye:
- `manifest.json` y meta-tags móviles (`viewport-fit=cover`, `mobile-web-app-capable`).
- Zonas táctiles amplias (mínimo 44px) y casillas de verificación táctiles ergonómicas.
- Web Audio API integrado para feedback sonoro al completar tareas y vibración háptica (`navigator.vibrate`).
- Se puede convertir en APK nativa en minutos mediante:
  1. [PWA Builder](https://www.pwabuilder.com/)
  2. [Capacitor / Cordova](https://capacitorjs.com/)
  3. WebView en Android Studio

---

## 🚀 Despliegue en Render

1. Sube este repositorio a tu GitHub.
2. En tu panel de **[Render](https://render.com/)**, selecciona **New +** ➔ **Web Service**.
3. Conecta el repositorio de Jarvis.
4. Parámetros de Render:
   - **Environment:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
5. (Opcional) En variables de entorno (*Environment Variables*), define:
   - `JARVIS_API_KEY`: Tu clave secreta para la captura por voz (ej. `mi-clave-super-secreta`).

---

## 💻 Ejecución Local

```bash
# 1. Crear entorno virtual (opcional)
python -m venv env
.\env\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Iniciar la aplicación
python app.py
```

Abre en tu navegador: **`http://127.0.0.1:5000`**
