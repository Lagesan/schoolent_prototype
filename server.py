from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify, Response
import sqlite3
import os, time, requests
from flask_socketio import SocketIO, emit

app = Flask(__name__, static_folder='templates/static')
app.secret_key = 'g102'

# 配置数据库连接
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = None
app.config['SESSION_TYPE'] = 'sqlalchemy'
app.config['UPLOAD_FOLDER'] = 'uploads/'

# 确保上传文件夹存在
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# 初始化数据库
def init_db():
    with sqlite3.connect('app.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT NOT NULL UNIQUE,
                            password TEXT NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS notifications (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title TEXT NOT NULL,
                            content TEXT NOT NULL,
                            time TEXT NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            message TEXT NOT NULL,
                            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                            file_id INTEGER NULL,
                            username TEXT NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS files (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            message_id INTEGER,
                            filename TEXT NOT NULL,
                            filepath TEXT NOT NULL,
                            FOREIGN KEY (message_id) REFERENCES messages (id))''')
        conn.commit()



def get_spark_response(user_input):  # 获取讯飞API返回的流数据
    url = "https://spark-api-open.xf-yun.com/v1/chat/completions"
    data = {
            "model": "general",
            "messages": [
                {
                    "role": 'user',
                    "content": user_input
                }
            ],
                "stream": False
        }
    header = {
        "Authorization": "replaced by your own token",
    }
    response = requests.post(url, headers=header, json=data)
    response.encoding = "utf-8"
    try:
        response_data = response.json()
        content = response_data['choices'][0]['message']['content']
        print(content)
        return Response(content, content_type="text/plain; charset=utf-8")
    except:
        print("request failed")




# 初始化 SocketIO
socketio = SocketIO(app)

@app.route('/')    # main page
def home():
    if 'username' in session:   # if user is logged in
        return redirect(url_for('dashboard'))
    else:
        return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])     # register page
def register():       # TODO:error message return to the page to alert user
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
                conn.commit()
                flash('Registration successful. Please log in.', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Username already exists. Please choose another.', 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    else:
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            with sqlite3.connect('app.db') as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
                user = cursor.fetchone()
                if user:
                    session['user_id'] = user[0]
                    session['username'] = username
                    flash('Login successful.', 'success')
                    return redirect(url_for('dashboard'))
                flash('Invalid credentials. Please try again.', 'danger')
        return render_template('login.html')
    
@app.route("/sparkai")   # ai chat page
def aipage():
    if 'user_id' not in session:
        flash('You need to log in to access the dashboard.', 'warning')
        return redirect(url_for('login'))
    return render_template('aichat.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('You need to log in to access the dashboard.', 'warning')
        return redirect(url_for('login'))
    with sqlite3.connect('app.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM notifications ORDER BY time DESC')
        notifications = cursor.fetchall()
    return render_template('dashboard.html', notifications=notifications)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/hit')   #TODO: 制导导弹打击模拟特效页面，需要添加特效 -> 点击长按特效 -> 长安5s后确定打击位置特效 -> 消失
def hit():
    return render_template('hit.html')
    

@app.route("/aichat", methods=["POST"])
def AiChat():
    user_input = request.json.get("message")
    if not user_input:
        return jsonify({"error": "Message is required"}), 400 # error messages printed in the console
    
    # 获取讯飞API返回的流数据
    return get_spark_response(user_input)




@app.route('/notification/new', methods=['GET', 'POST'])
def new_notification():
    if 'user_id' not in session:
        flash('You need to log in to post a notification.', 'warning')
        return redirect(url_for('login'))
    if 'username' in session and session['username'] == "David Zhang":
        if request.method == 'POST':
            title = request.form['title']
            content = request.form['content']
            with sqlite3.connect('app.db') as conn:
                noti_timestamp = time.time()
                noti_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(noti_timestamp))
                cursor = conn.cursor()
                cursor.execute('INSERT INTO notifications (title, content, time) VALUES (?, ?, ?)', (title, content, noti_time))
                conn.commit()
            flash('Notification posted successfully.', 'success')
            return redirect(url_for('dashboard'))
        return render_template('new_notification.html')
    else:
        return "访问无效"

@app.route('/chat', methods=['GET'])
def render_chat():
    if 'user_id' not in session:
        flash('You need to log in to access the chat.', 'warning')
        return redirect(url_for('login'))
    
    with sqlite3.connect('app.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT messages.*, files.filename FROM messages LEFT JOIN files ON messages.file_id = files.id ORDER BY timestamp ASC')
        messages = cursor.fetchall()
    return render_template('chat.html', messages=messages)


@app.route('/chat', methods=['POST'])
def handle_message():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    message = request.form.get('message', '')
    file = request.files.get('file', None)
    username = session.get('username')

    filename = None
    file_path = None

    try:
        if file:
            filename = file.filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            with sqlite3.connect('app.db') as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO files (filename, filepath) VALUES (?, ?)', (filename, file_path))
                file_id = cursor.lastrowid
                
                cursor.execute(
                    'INSERT INTO messages (user_id, username, message, file_id) VALUES (?, ?, ?, ?)',
                    (session['user_id'], username, message, file_id)
                )
                conn.commit()
        else:
            with sqlite3.connect('app.db') as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO messages (user_id, username, message) VALUES (?, ?, ?)',
                    (session['user_id'], username, message)
                )
                conn.commit()

        # 使用 SocketIO 广播消息
        socketio.emit('new_message', {
            'username': username,
            'message': message,
            'filename': filename,
            'filepath': url_for('uploaded_file', filename=filename) if filename else None
        })

        return jsonify({
            'status': 'success',
            'message': message,
            'filename': filename,
            'filepath': url_for('uploaded_file', filename=filename) if filename else None
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)



# SocketIO 事件处理
@socketio.on('connect')
def handle_connect():
    print("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', debug=True, port=1002)
