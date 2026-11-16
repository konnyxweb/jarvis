import os
import sqlite3
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Configuración de base de datos
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jarvis.db')
API_SECRET_KEY = os.environ.get('JARVIS_API_KEY', 'jarvis-voice-2026')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
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
    
    # Comprobar si la tabla existente tiene la restricción antigua sin 'health' y migrarla
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
    table_def = cursor.fetchone()
    if table_def and table_def['sql'] and "health" not in table_def['sql']:
        cursor.execute("PRAGMA foreign_keys=off")
        cursor.execute('''
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
        cursor.execute('''
            INSERT INTO tasks_new (id, title, category, date, priority, completed, completed_at, created_at)
            SELECT id, title, category, date, priority, completed, completed_at, created_at FROM tasks
        ''')
        cursor.execute("DROP TABLE tasks")
        cursor.execute("ALTER TABLE tasks_new RENAME TO tasks")
        conn.commit()
        cursor.execute("PRAGMA foreign_keys=on")
    
    # Sembrar datos iniciales si la tabla está vacía
    cursor.execute('SELECT COUNT(*) as count FROM tasks')
    if cursor.fetchone()['count'] == 0:
        today_str = date.today().isoformat()
        yesterday_str = (date.today() - timedelta(days=1)).isoformat()
        
        initial_tasks = [
            # Tareas de Trabajo (con Top 3 Prioridades)
            ("Arquitectura de microservicios Jarvis", "work", today_str, 1, 0, None),
            ("Revisión de pull requests del equipo", "work", today_str, 2, 0, None),
            ("Planificación de sprint semanal", "work", today_str, 3, 1, f"{today_str} 09:30:00"),
            ("Actualizar documentación de API", "work", today_str, 0, 0, None),
            
            # Tareas del Hogar
            ("Mantenimiento y orden del espacio de trabajo", "home", today_str, 0, 0, None),
            ("Planificar logística y compras del hogar", "home", today_str, 0, 0, None),
            
            # Tareas de Salud & Bienestar
            ("30 minutos de entrenamiento físico o cardio", "health", today_str, 0, 1, f"{today_str} 07:15:00"),
            ("Tomar 2L de agua y suplementos vitamínicos", "health", today_str, 0, 0, None),
            ("Chequeo médico o control de bienestar", "health", today_str, 0, 0, None),
            
            # Diligencias y Calle
            ("Retirar paquete en oficina de envíos", "errands", today_str, 0, 0, None),
            ("Comprar café tostado en grano", "errands", today_str, 0, 1, f"{today_str} 11:20:00"),
            
            # Tarea completada ayer para ilustrar racha
            ("Configuración del servidor base", "work", yesterday_str, 1, 1, f"{yesterday_str} 18:00:00")
        ]
        
        cursor.executemany('''
            INSERT INTO tasks (title, category, date, priority, completed, completed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', initial_tasks)
        
    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# Helper de Cálculo de Métricas y Racha
# ==============================================================================

def calculate_productivity_stats():
    conn = get_db()
    cursor = conn.cursor()
    today_str = date.today().isoformat()
    
    # Tareas de hoy
    cursor.execute('SELECT COUNT(*) as total FROM tasks WHERE date = ?', (today_str,))
    total_today = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as completed FROM tasks WHERE date = ? AND completed = 1', (today_str,))
    completed_today = cursor.fetchone()['completed']
    
    today_percentage = round((completed_today / total_today * 100), 1) if total_today > 0 else 0
    
    # Desglose por categoría para hoy (Trabajo, Casa, Diligencias, Salud)
    categories = ['work', 'home', 'errands', 'health']
    cat_stats = {}
    for cat in categories:
        cursor.execute('SELECT COUNT(*) as total FROM tasks WHERE date = ? AND category = ?', (today_str, cat))
        t_count = cursor.fetchone()['total']
        cursor.execute('SELECT COUNT(*) as comp FROM tasks WHERE date = ? AND category = ? AND completed = 1', (today_str, cat))
        c_count = cursor.fetchone()['comp']
        cat_stats[cat] = {
            'total': t_count,
            'completed': c_count,
            'percentage': round((c_count / t_count * 100), 1) if t_count > 0 else 0
        }
        
    # Cálculo de Racha de Cumplimiento (días consecutivos con tareas completadas)
    cursor.execute('''
        SELECT DISTINCT date(completed_at) as comp_date
        FROM tasks 
        WHERE completed = 1 AND completed_at IS NOT NULL
        ORDER BY comp_date DESC
    ''')
    completed_dates = {row['comp_date'] for row in cursor.fetchall()}
    
    streak = 0
    check_date = date.today()
    
    # Si hoy aún no completa nada, revisamos si completó ayer para mantener la racha viva
    if check_date.isoformat() not in completed_dates:
        check_date = check_date - timedelta(days=1)
        
    while check_date.isoformat() in completed_dates:
        streak += 1
        check_date -= timedelta(days=1)
        
    # Prioridades Top 3 de hoy
    cursor.execute('''
        SELECT id, title, category, completed, priority 
        FROM tasks 
        WHERE date = ? AND priority > 0
        ORDER BY priority ASC
        LIMIT 3
    ''', (today_str,))
    top_priorities = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
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
    stats = calculate_productivity_stats()
    return jsonify({'success': True, 'stats': stats})

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    category = request.args.get('category', 'all')
    date_filter = request.args.get('date', 'today')
    
    conn = get_db()
    cursor = conn.cursor()
    
    query = 'SELECT * FROM tasks WHERE 1=1'
    params = []
    
    if date_filter == 'today':
        query += ' AND date = ?'
        params.append(date.today().isoformat())
    elif date_filter != 'all' and date_filter:
        query += ' AND date = ?'
        params.append(date_filter)
        
    if category in ['work', 'home', 'errands', 'health']:
        query += ' AND category = ?'
        params.append(category)
        
    # Ordenar: primero no completadas, luego prioridad (1, 2, 3), luego id descendente
    query += '''
        ORDER BY 
            completed ASC,
            CASE WHEN priority > 0 THEN 0 ELSE 1 END ASC,
            priority ASC,
            id DESC
    '''
    
    cursor.execute(query, params)
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    stats = calculate_productivity_stats()
    
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
    
    if not title:
        return jsonify({'success': False, 'error': 'El título de la tarea es requerido'}), 400
        
    if category not in ['work', 'home', 'errands', 'health']:
        category = 'work'
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO tasks (title, category, date, priority, completed)
        VALUES (?, ?, ?, ?, 0)
    ''', (title, category, task_date, priority))
    conn.commit()
    new_id = cursor.lastrowid
    
    cursor.execute('SELECT * FROM tasks WHERE id = ?', (new_id,))
    new_task = dict(cursor.fetchone())
    conn.close()
    
    return jsonify({
        'success': True,
        'task': new_task,
        'stats': calculate_productivity_stats()
    }), 201

@app.route('/api/tasks/<int:task_id>/toggle', methods=['PATCH'])
def toggle_task(task_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()
    
    if not task:
        conn.close()
        return jsonify({'success': False, 'error': 'Tarea no encontrada'}), 404
        
    new_completed = 0 if task['completed'] else 1
    completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S') if new_completed else None
    
    cursor.execute('''
        UPDATE tasks 
        SET completed = ?, completed_at = ? 
        WHERE id = ?
    ''', (new_completed, completed_at, task_id))
    conn.commit()
    
    cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
    updated_task = dict(cursor.fetchone())
    conn.close()
    
    return jsonify({
        'success': True,
        'task': updated_task,
        'stats': calculate_productivity_stats()
    })

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    if not deleted:
        return jsonify({'success': False, 'error': 'Tarea no encontrada'}), 404
        
    return jsonify({
        'success': True,
        'message': 'Tarea eliminada exitosamente',
        'stats': calculate_productivity_stats()
    })

# ==============================================================================
# Endpoint de Voz y Captura Rápida (Webhook para n8n / Asistente / Atajos)
# ==============================================================================

@app.route('/api/quick-add', methods=['POST'])
def quick_add_voice_webhook():
    # Verificación de Token / Clave secreta
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
            
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO tasks (title, category, date, priority, completed)
        VALUES (?, ?, ?, ?, 0)
    ''', (raw_text, category, task_date, priority))
    conn.commit()
    new_id = cursor.lastrowid
    
    cursor.execute('SELECT * FROM tasks WHERE id = ?', (new_id,))
    task = dict(cursor.fetchone())
    conn.close()
    
    return jsonify({
        'success': True,
        'message': f'Tarea capturada por Jarvis en [{category.upper()}]: "{raw_text}"',
        'task': task,
        'stats': calculate_productivity_stats()
    }), 201

# ==============================================================================
# Servidor de Producción / Local
# ==============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Jarvis Online en http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
