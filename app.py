import os
import sqlite3
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ==============================================================================
# Configuración y Adaptador de Base de Datos Híbrido (PostgreSQL / SQLite)
# ==============================================================================

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

USE_POSTGRES = bool(DATABASE_URL)
psycopg2 = None
if USE_POSTGRES:
    try:
        import psycopg2
        import psycopg2.extras
        print("🌐 Conexión de base de datos: PostgreSQL en la nube configurado.")
    except ImportError:
        USE_POSTGRES = False
        print("⚠️ Advertencia: psycopg2 no está instalado en este entorno. Usando SQLite local.")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jarvis.db')
API_SECRET_KEY = os.environ.get('JARVIS_API_KEY', 'jarvis-voice-2026')

def serialize_task(row):
    """Normaliza filas de PostgreSQL o SQLite a un diccionario JSON estándar."""
    if row is None:
        return None
    d = dict(row)
    if 'completed' in d:
        d['completed'] = 1 if d['completed'] else 0
    if 'date' in d and isinstance(d['date'], (date, datetime)):
        d['date'] = d['date'].isoformat()
    if 'created_at' in d and isinstance(d['created_at'], (date, datetime)):
        d['created_at'] = d['created_at'].isoformat()
    if 'completed_at' in d and isinstance(d['completed_at'], (date, datetime)):
        d['completed_at'] = d['completed_at'].isoformat()
    return d

class DB:
    """Wrapper contextual para gestionar conexiones y consultas transparentes."""
    def __init__(self):
        if USE_POSTGRES:
            self.conn = psycopg2.connect(DATABASE_URL)
            self.cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            self.conn = sqlite3.connect(DB_PATH)
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()

    def execute(self, sql, params=()):
        if USE_POSTGRES:
            sql = sql.replace('?', '%s')
        self.cursor.execute(sql, params)
        return self.cursor

    def executemany(self, sql, seq_of_params):
        if USE_POSTGRES:
            sql = sql.replace('?', '%s')
        self.cursor.executemany(sql, seq_of_params)
        return self.cursor

    def fetchone(self):
        row = self.cursor.fetchone()
        return serialize_task(row) if row else None

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [serialize_task(r) for r in rows]

    def commit(self):
        self.conn.commit()

    def close(self):
        try:
            self.cursor.close()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            try:
                self.conn.rollback()
            except Exception:
                pass
        self.close()

def get_db():
    return DB()

# ==============================================================================
# Inicialización y Migración Automática de Tablas
# ==============================================================================

def init_db():
    with get_db() as db:
        if USE_POSTGRES:
            db.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    category VARCHAR(50) NOT NULL CHECK(category IN ('work', 'home', 'errands', 'health')),
                    date DATE NOT NULL,
                    priority INTEGER DEFAULT 0,
                    completed BOOLEAN DEFAULT FALSE,
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            db.commit()
        else:
            db.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL CHECK(category IN ('work', 'home', 'errands', 'health')),
                    date DATE NOT NULL,
                    priority INTEGER DEFAULT 0,
                    completed BOOLEAN DEFAULT 0,
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            db.commit()
            
            # Comprobar si la tabla SQLite antigua no tenía 'health' y migrarla
            db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
            table_def = db.fetchone()
            if table_def and table_def.get('sql') and "health" not in table_def['sql']:
                db.execute("PRAGMA foreign_keys=off")
                db.execute('''
                    CREATE TABLE tasks_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        category TEXT NOT NULL CHECK(category IN ('work', 'home', 'errands', 'health')),
                        date DATE NOT NULL,
                        priority INTEGER DEFAULT 0,
                        completed BOOLEAN DEFAULT 0,
                        completed_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                db.execute('''
                    INSERT INTO tasks_new (id, title, category, date, priority, completed, completed_at, created_at)
                    SELECT id, title, category, date, priority, completed, completed_at, created_at FROM tasks
                ''')
                db.execute("DROP TABLE tasks")
                db.execute("ALTER TABLE tasks_new RENAME TO tasks")
                db.commit()
                db.execute("PRAGMA foreign_keys=on")
                
        # Verificar si la base de datos está vacía para sembrar datos
        db.execute('SELECT COUNT(*) as count FROM tasks')
        res = db.fetchone()
        count = res['count'] if res else 0

        # Si estamos en PostgreSQL y está vacía, intentar migrar datos existentes desde SQLite jarvis.db
        if USE_POSTGRES and count == 0 and os.path.exists(DB_PATH):
            try:
                local_conn = sqlite3.connect(DB_PATH)
                local_conn.row_factory = sqlite3.Row
                lc = local_conn.cursor()
                lc.execute('SELECT title, category, date, priority, completed, completed_at FROM tasks')
                local_tasks = lc.fetchall()
                if local_tasks:
                    formatted = [
                        (r['title'], r['category'], r['date'], r['priority'], bool(r['completed']), r['completed_at'])
                        for r in local_tasks
                    ]
                    db.executemany('''
                        INSERT INTO tasks (title, category, date, priority, completed, completed_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', formatted)
                    db.commit()
                    print(f"✅ Se importaron {len(formatted)} tareas de jarvis.db local a PostgreSQL.")
                    count = len(formatted)
                local_conn.close()
            except Exception as e:
                print(f"Información: inicio estándar sin importación de SQLite ({e})")

        # Si aún está vacía, insertar lote de bienvenida
        if count == 0:
            today_str = date.today().isoformat()
            yesterday_str = (date.today() - timedelta(days=1)).isoformat()
            
            initial_tasks = [
                # Trabajo (Prioridades Top 3)
                ("Arquitectura de microservicios Jarvis", "work", today_str, 1, False, None),
                ("Revisión de pull requests del equipo", "work", today_str, 2, False, None),
                ("Planificación de sprint semanal", "work", today_str, 3, True, f"{today_str} 09:30:00"),
                ("Actualizar documentación de API", "work", today_str, 0, False, None),
                
                # Hogar
                ("Mantenimiento y orden del espacio de trabajo", "home", today_str, 0, False, None),
                ("Planificar logística y compras del hogar", "home", today_str, 0, False, None),
                
                # Salud & Bienestar
                ("30 minutos de entrenamiento físico o cardio", "health", today_str, 0, True, f"{today_str} 07:15:00"),
                ("Tomar 2L de agua y suplementos vitamínicos", "health", today_str, 0, False, None),
                ("Chequeo médico o control de bienestar", "health", today_str, 0, False, None),
                
                # Diligencias
                ("Retirar paquete en oficina de envíos", "errands", today_str, 0, False, None),
                ("Comprar café tostado en grano", "errands", today_str, 0, True, f"{today_str} 11:20:00"),
                
                # Tarea previa para ilustrar racha
                ("Configuración del servidor base", "work", yesterday_str, 1, True, f"{yesterday_str} 18:00:00")
            ]
            
            db.executemany('''
                INSERT INTO tasks (title, category, date, priority, completed, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', initial_tasks)
            db.commit()

init_db()

# ==============================================================================
# Helper de Cálculo de Métricas y Racha
# ==============================================================================

def calculate_productivity_stats(today_str=None):
    if not today_str:
        today_str = date.today().isoformat()
        
    with get_db() as db:
        # Tareas activas a gestionar (pendientes + completadas hoy)
        db.execute('''
            SELECT COUNT(*) as total 
            FROM tasks 
            WHERE completed = ? OR (completed = ? AND (date = ? OR date(completed_at) = ?))
        ''', (False, True, today_str, today_str))
        r = db.fetchone()
        total_today = r['total'] if r else 0
        
        # Completadas hoy
        db.execute('''
            SELECT COUNT(*) as completed 
            FROM tasks 
            WHERE completed = ? AND (date = ? OR date(completed_at) = ?)
        ''', (True, today_str, today_str))
        r = db.fetchone()
        completed_today = r['completed'] if r else 0
        
        today_percentage = round((completed_today / total_today * 100), 1) if total_today > 0 else 0
        
        # Desglose por categoría (Trabajo, Casa, Diligencias, Salud)
        categories = ['work', 'home', 'errands', 'health']
        cat_stats = {}
        for cat in categories:
            db.execute('''
                SELECT COUNT(*) as total 
                FROM tasks 
                WHERE category = ? AND (completed = ? OR (completed = ? AND (date = ? OR date(completed_at) = ?)))
            ''', (cat, False, True, today_str, today_str))
            r = db.fetchone()
            t_count = r['total'] if r else 0
            
            db.execute('''
                SELECT COUNT(*) as comp 
                FROM tasks 
                WHERE category = ? AND completed = ? AND (date = ? OR date(completed_at) = ?)
            ''', (cat, True, today_str, today_str))
            r = db.fetchone()
            c_count = r['comp'] if r else 0
            
            cat_stats[cat] = {
                'total': t_count,
                'completed': c_count,
                'percentage': round((c_count / t_count * 100), 1) if t_count > 0 else 0
            }
            
        # Cálculo de Racha de Cumplimiento (días consecutivos con tareas completadas)
        db.execute('''
            SELECT DISTINCT date(completed_at) as comp_date
            FROM tasks 
            WHERE completed = ? AND completed_at IS NOT NULL
            ORDER BY comp_date DESC
        ''', (True,))
        rows = db.fetchall()
        completed_dates = {str(row['comp_date']) for row in rows if row and row.get('comp_date')}
        
        streak = 0
        try:
            check_date = datetime.strptime(today_str, '%Y-%m-%d').date()
        except Exception:
            check_date = date.today()
            
        # Si hoy aún no completa nada, revisamos si completó ayer para mantener la racha viva
        if check_date.isoformat() not in completed_dates:
            check_date = check_date - timedelta(days=1)
            
        while check_date.isoformat() in completed_dates:
            streak += 1
            check_date -= timedelta(days=1)
            
        # Prioridades Top 3 activas (pendientes o del día)
        db.execute('''
            SELECT id, title, category, completed, priority 
            FROM tasks 
            WHERE priority > 0 AND (completed = ? OR (completed = ? AND (date = ? OR date(completed_at) = ?)))
            ORDER BY completed ASC, priority ASC
            LIMIT 3
        ''', (False, True, today_str, today_str))
        top_priorities = db.fetchall()
        
    return {
        'today': {
            'date': today_str,
            'total': total_today,
            'completed': completed_today,
            'percentage': today_percentage
        },
        'categories': cat_stats,
        'streak_days': streak,
        'top_priorities': top_priorities
    }

# ==============================================================================
# Rutas Principales
# ==============================================================================

@app.route('/')
def index():
    return render_template('index.html', api_token=API_SECRET_KEY)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    client_date = request.args.get('client_date') or date.today().isoformat()
    stats = calculate_productivity_stats(today_str=client_date)
    return jsonify({'success': True, 'stats': stats})

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    category = request.args.get('category', 'all')
    date_filter = request.args.get('date', 'active')  # 'active' por defecto: no oculta pendientes
    client_date = request.args.get('client_date') or date.today().isoformat()
    
    with get_db() as db:
        query = 'SELECT * FROM tasks WHERE 1=1'
        params = []
        
        if date_filter == 'active':
            # Vista principal: todas las tareas pendientes + las tareas completadas el día de hoy
            query += ' AND (completed = ? OR (completed = ? AND (date = ? OR date(completed_at) = ?)))'
            params.extend([False, True, client_date, client_date])
        elif date_filter == 'today':
            query += ' AND date = ?'
            params.append(client_date)
        elif date_filter != 'all' and date_filter:
            query += ' AND date = ?'
            params.append(date_filter)
            
        if category in ['work', 'home', 'errands', 'health']:
            query += ' AND category = ?'
            params.append(category)
            
        # Ordenar: primero pendientes, luego prioridad (1, 2, 3), luego id descendente
        query += '''
            ORDER BY 
                completed ASC,
                CASE WHEN priority > 0 THEN 0 ELSE 1 END ASC,
                priority ASC,
                id DESC
        '''
        
        db.execute(query, params)
        tasks = db.fetchall()
        
    stats = calculate_productivity_stats(today_str=client_date)
    
    return jsonify({
        'success': True,
        'tasks': tasks,
        'stats': stats
    })

@app.route('/api/tasks', methods=['POST'])
def create_task():
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    category = data.get('category', 'work').lower()
    task_date = data.get('date', date.today().isoformat())
    priority = int(data.get('priority', 0))
    client_date = data.get('client_date') or task_date
    
    if not title:
        return jsonify({'success': False, 'error': 'El título de la tarea es requerido'}), 400
        
    if category not in ['work', 'home', 'errands', 'health']:
        category = 'work'
        
    with get_db() as db:
        db.execute('''
            INSERT INTO tasks (title, category, date, priority, completed)
            VALUES (?, ?, ?, ?, ?)
            RETURNING *
        ''', (title, category, task_date, priority, False))
        new_task = db.fetchone()
        db.commit()
        
    return jsonify({
        'success': True,
        'task': new_task,
        'stats': calculate_productivity_stats(today_str=client_date)
    }), 201

@app.route('/api/tasks/<int:task_id>/toggle', methods=['PATCH'])
def toggle_task(task_id):
    client_date = request.args.get('client_date') or date.today().isoformat()
    
    with get_db() as db:
        db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        task = db.fetchone()
        
        if not task:
            return jsonify({'success': False, 'error': 'Tarea no encontrada'}), 404
            
        new_completed = False if task['completed'] else True
        completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S') if new_completed else None
        
        db.execute('''
            UPDATE tasks 
            SET completed = ?, completed_at = ? 
            WHERE id = ?
            RETURNING *
        ''', (new_completed, completed_at, task_id))
        updated_task = db.fetchone()
        db.commit()
        
    return jsonify({
        'success': True,
        'task': updated_task,
        'stats': calculate_productivity_stats(today_str=client_date)
    })

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    client_date = request.args.get('client_date') or date.today().isoformat()
    
    with get_db() as db:
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        deleted = db.cursor.rowcount > 0
        db.commit()
        
    if not deleted:
        return jsonify({'success': False, 'error': 'Tarea no encontrada'}), 404
        
    return jsonify({
        'success': True,
        'message': 'Tarea eliminada exitosamente',
        'stats': calculate_productivity_stats(today_str=client_date)
    })

# ==============================================================================
# Endpoint de Voz y Captura Rápida (Webhook para n8n / Asistente / Atajos)
# ==============================================================================

@app.route('/api/quick-add', methods=['POST'])
def quick_add_voice_webhook():
    token = request.headers.get('X-API-Key') or request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
        
    body_data = request.get_json(silent=True) or {}
    query_token = request.args.get('token') or body_data.get('token')
    effective_token = token or query_token
    
    if effective_token != API_SECRET_KEY:
        return jsonify({
            'success': False,
            'error': 'No autorizado. Proporciona un header X-API-Key válido o token.'
        }), 401
        
    raw_text = body_data.get('text') or body_data.get('title') or ''
    raw_text = raw_text.strip()
    
    if not raw_text:
        return jsonify({'success': False, 'error': 'Campo "text" o "title" vacío'}), 400
        
    category = body_data.get('category', '').lower().strip()
    priority = int(body_data.get('priority', 0))
    task_date = body_data.get('date', date.today().isoformat())
    
    # Auto-categorización inteligente si no se especifica categoría
    if category not in ['work', 'home', 'errands', 'health']:
        lower_text = raw_text.lower()
        if any(w in lower_text for w in [
            'salud', 'médico', 'medico', 'medicina', 'pastilla', 'pastillas', 
            'cita médica', 'dentista', 'doctor', 'doctora', 'vitaminas', 
            'terapia', 'farmacia', 'entrenar', 'ejercicio', 'gym', 'gimnasio', 
            'cardio', 'correr', 'caminar', 'agua', 'dormir', 'peso', 'presión', 
            'dieta', 'estiramiento', 'bienestar', 'psicólogo', 'nutricionista'
        ]):
            category = 'health'
        elif any(w in lower_text for w in ['comprar', 'supermercado', 'banco', 'recoger', 'calle', 'envío', 'tienda', 'pagar', 'trámite', 'mensajería']):
            category = 'errands'
        elif any(w in lower_text for w in ['casa', 'limpiar', 'lavar', 'cocinar', 'comida', 'ordenar', 'reparar', 'planta']):
            category = 'home'
        else:
            category = 'work'
            
    with get_db() as db:
        db.execute('''
            INSERT INTO tasks (title, category, date, priority, completed)
            VALUES (?, ?, ?, ?, ?)
            RETURNING *
        ''', (raw_text, category, task_date, priority, False))
        task = db.fetchone()
        db.commit()
        
    return jsonify({
        'success': True,
        'message': f'Tarea capturada por Jarvis en [{category.upper()}]: "{raw_text}"',
        'task': task,
        'stats': calculate_productivity_stats(today_str=task_date)
    }), 201

# ==============================================================================
# Servidor de Producción / Local
# ==============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    db_mode = "PostgreSQL en la nube" if USE_POSTGRES else f"SQLite ({DB_PATH})"
    print(f"🚀 Jarvis Online en http://127.0.0.1:{port} | Base de datos: {db_mode}")
    app.run(host='0.0.0.0', port=port, debug=False)
