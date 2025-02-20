from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify, Response
import sqlite3, json
import os, time, requests,urllib.parse
import shutil
from flask_socketio import SocketIO, emit
from banalysis import *
import subprocess, threading, time
from markdown.extensions.fenced_code import FencedCodeExtension
from datetime import datetime
import markdown, uuid

app = Flask(__name__, static_folder='templates/static')
app.secret_key = os.urandom(24)


# 配置数据库连接
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = None
app.config['SESSION_TYPE'] = 'sqlalchemy'
app.config["PRIVATE_CHAT"] = 'chat/'
app.config["USERS_SETTING"] = 'users/'
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['BILIBILI_FOLDER'] = 'gv/'


# 用于记录正在处理的视频文件名
processing_videos = set()
processing_lock = threading.Lock()


# config the authorization of the spark api from local file:server.set, if not exist create one
authorization = ""
if not os.path.exists("server.set"):
    with open("server.set", "w") as f:
        f.write("authorization=")

with open("server.set", "r") as f:
    # read authorization from server.set (info after "=")
    info = f.read().strip()
    if info == 'authorization=':
        print("Please input the authorization of the spark api")
    elif info:
        authorization = info.split("=")[1]
    # close the file
    f.close()
        
        
# folder init
def init_folders():
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    if not os.path.exists(app.config['PRIVATE_CHAT']):
        os.makedirs(app.config['PRIVATE_CHAT'])

    if not os.path.exists(app.config['USERS_SETTING']):
        os.makedirs(app.config['USERS_SETTING'])

    avatar_folder = os.path.join(app.config['USERS_SETTING'], 'avatar')
    if not os.path.exists(avatar_folder):
        os.makedirs(avatar_folder)

    default_avatar_path = os.path.join('templates/static', 'noface.jpg')
    if os.path.exists(default_avatar_path):
        shutil.copy(default_avatar_path, avatar_folder)

# QS part 
def from_json(value):
    """将 JSON 字符串解析为 Python 对象"""
    return json.loads(value)
app.jinja_env.filters['from_json'] = from_json

# 初始化数据库
def init_db():
    with sqlite3.connect('app.db') as conn:
        cursor = conn.cursor()
        # create users table
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT NOT NULL UNIQUE,
                            password TEXT NOT NULL,
                            avatar_route TEXT DEFAULT 'noface.jpg',
                            bio TEXT DEFAULT 'What a lazy guy! This guy has not set a bio yet.',
                            email TEXT DEFAULT 'None',
                            sex TEXT DEFAULT 'None',
                            classroom TEXT DEFAULT 'None',
                            birthday TEXT DEFAULT 'None',
                            noti_num INTEGER DEFAULT 0)''')
        # create notifications table
        cursor.execute('''CREATE TABLE IF NOT EXISTS notifications (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title TEXT NOT NULL,
                            content TEXT NOT NULL,
                            time TEXT NOT NULL)''')
        #create schedule table
        # cursor.execute('''DROP TABLE IF EXISTS schedule''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS schedule (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            title TEXT NOT NULL,
                            content TEXT NOT NULL,
                            start_time TEXT NOT NULL,
                            end_time TEXT NOT NULL,
                            class TEXT NOT NULL)''')
        # create messages table
        # cursor.execute('''DROP TABLE IF EXISTS messages''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            message TEXT NOT NULL,
                            time TEXT NOT NULL,
                            file_id INTEGER NULL,
                            username TEXT NOT NULL)''')
        # cursor.execute('''DROP TABLE IF EXISTS files''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS files (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            message_id INTEGER,
                            filename TEXT NOT NULL,
                            filepath TEXT NOT NULL,
                            FOREIGN KEY (message_id) REFERENCES messages (id))''')
        # create surveys table
        # 问卷表
        cursor.execute('''CREATE TABLE IF NOT EXISTS surveys
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    creator_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(creator_id) REFERENCES users(id))''')
        
        # 问题表
        cursor.execute('''CREATE TABLE IF NOT EXISTS questions
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    survey_id INTEGER NOT NULL,
                    type TEXT NOT NULL,  -- title/text/radio/checkbox/input
                    content TEXT NOT NULL,
                    options TEXT,  -- JSON格式存储选项
                    required BOOLEAN NOT NULL DEFAULT 1,
                    FOREIGN KEY(survey_id) REFERENCES surveys(id))''')
        
        # 回答表
        cursor.execute('''CREATE TABLE IF NOT EXISTS responses
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    survey_id INTEGER NOT NULL,
                    question_id INTEGER NOT NULL,
                    user_id INTEGER,
                    answer TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(survey_id) REFERENCES surveys(id),
                    FOREIGN KEY(question_id) REFERENCES questions(id),
                    FOREIGN KEY(user_id) REFERENCES users(id))''')
        conn.commit()


# Bibili API headers
headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com/',
        'Origin': 'https://www.bilibili.com',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7,de;q=0.6',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Connection': 'keep-alive',
        'DNT': '1',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'cookie': 'CURRENT_FNVAL=4048; rpdid=|(umY)k)|kmJ0J\'u~|Rl)lJYk; buvid3=8640B8DE-98F8-3194-60BB-CA6DB6FFC0CA68669infoc; b_nut=1719641968; PVID=1; _uuid=6241082A2-CCE10-56610-9CC1-5AB115C9BEFE86135infoc; LIVE_BUVID=AUTO7017222538454308; CURRENT_BLACKGAP=0; home_feed_column=5; CURRENT_QUALITY=64; fingerprint=fd73a99ca8eee2230ce41153babb706d; buvid_fp=fd73a99ca8eee2230ce41153babb706d; b_lsid=9A5C7C53_19464359093; bili_ticket=eyJhbGciOiJIUzI1NiIsImtpZCI6InMwMyIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3MzcxMDcyMTksImlhdCI6MTczNjg0Nzk1OSwicGx0IjotMX0.3LOyrrHumo_WHI7E1y2EGNznqCW5QmQOxMU1nxjvEFU; bili_ticket_expires=1737107159; buvid4=5AA1AC0B-F4DA-26F2-02C5-2CF08B83CC9B20380-025011409-7XY6MkURWSTD74UlnZFOXg%3D%3D; sid=nvthhvah; header_theme_version=CLOSE; enable_web_push=DISABLE; browser_resolution=1528-712',
        'priority': 'u=0, i',
        'sec-ch-ua': '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
    }




def get_spark_response(user_input):
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
        "Authorization": authorization,
    }

    response = requests.post(url, headers=header, json=data)
    response.encoding = "utf-8"
    try:
        response_data = response.json()
        content = response_data['choices'][0]['message']['content']
        # print(content)
        return content  # 返回字符串
    except Exception as e:
        print("request failed", e)
        return "Error: Unable to get response from Spark API"
def get_series_info(bvid, headers):
    """
    获取视频是否为合集及分集信息
    """
    view_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    response = requests.get(view_url, headers=headers)
    try:
        data = response.json()
        if data['code'] != 0:
            print(f"Error: {data['message']}")
            return None
        
        video_count = data['data']['videos']
        duration = data['data']['duration']
        pages = data['data'].get('pages', [])
        sub_videos = []
        for page in pages:
            sub_videos.append({
                'cid': page['cid'],
                'page': page['page'],
                'part': page['part'],
                'duration': page['duration']
            })
        
        return {
            'is_series': video_count > 1,
            'duration': duration,
            'sub_videos': sub_videos
        }
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def get_random_bv():
    url = "https://api.bilibili.com/x/web-interface/index/top/rcmd?version=1"
    response = requests.get(url, headers=headers)
    try:
        if response.status_code == 200:
            data = response.json()
            if data['code'] == 0 and 'item' in data['data'] and len(data['data']['item']) > 0:
                videos = [{'bv_id': video['bvid'], 'title': video['title'], 'duration':str(round(int(video['duration'])/60, 2)), 'author': video['owner']['name']} for video in data['data']['item']]
                return videos
            else:
                print("No videos found in the response")
        else:
            print(f"Error: Received status code {response.status_code}")
            print(response.text)
    except ValueError:
        print("Error decoding JSON response")
        print(response.text)
    return []

# QS数据库辅助函数
def get_qsdb():
    conn = sqlite3.connect('app.db')
    conn.row_factory = sqlite3.Row  # 可选：设置行工厂
    return conn



# 初始化 SocketIO
socketio = SocketIO(app, async_mode='threading')
online_users = 0
online_user_ids = set()

@socketio.on('connect')
def handle_connect():
    global online_users
    user_id = session.get('user_id')
    if user_id and user_id not in online_user_ids:
        online_users += 1
        online_user_ids.add(user_id)
    emit('update_online_users', {'count': online_users}, broadcast=True)
    print("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    global online_users
    user_id = session.get('user_id')
    if user_id and user_id in online_user_ids:
        online_users -= 1
        online_user_ids.remove(user_id)
    emit('update_online_users', {'count': online_users}, broadcast=True)
    print("Client disconnected")

@app.route('/')    # main page
def home():
    if 'username' in session:   # if user is logged in
        return redirect(url_for('dashboard'))
    else:
        return render_template('index.html')

@app.route('/delete_gv_folder', methods=['POST'])
def delete_gv_folder():
    if 'user_id' not in session:
        flash('You need to log in to post a notification.', 'warning')
        return redirect(url_for('login'))
    if 'username' in session and session['username'] == "David Zhang":
        gv_folder = app.config['BILIBILI_FOLDER']
        try:
            if os.path.exists(gv_folder):
                for filename in os.listdir(gv_folder):
                    file_path = os.path.join(gv_folder, filename)
                    with processing_lock:
                        if file_path not in processing_videos:
                            try:
                                if os.path.isfile(file_path) or os.path.islink(file_path):
                                    os.unlink(file_path)
                                elif os.path.isdir(file_path):
                                    shutil.rmtree(file_path)
                            except Exception as e:
                                print(f"Failed to delete {file_path}. Reason: {e}")
            return jsonify({'status': 'success'}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        return "访问无效"

@app.route('/get_users', methods=['GET'])
def get_users():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if 'username' in session and session['username'] == "David Zhang":
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username, password FROM users')
            users = cursor.fetchall()
        
        return jsonify({'users': [{'username': user[0], 'password': user[1]} for user in users]}), 200

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
        
        # 获取用户头像路径
        cursor.execute('SELECT avatar_route FROM users WHERE id = ?', (session['user_id'],))
        result = cursor.fetchone()
        if result:
            avatar_route = result[0]
        
        # 获取通知总数
        cursor.execute('SELECT COUNT(*) FROM notifications')
        total_notifications = cursor.fetchone()[0]
        
        # 获取用户的未读通知数
        cursor.execute('SELECT noti_num FROM users WHERE id = ?', (session['user_id'],))
        user_noti_num = cursor.fetchone()[0]
    
    return render_template('dashboard.html', 
                           notifications=notifications, 
                           avatar_route="/avatar/"+avatar_route,
                           total_notifications=total_notifications,
                           user_noti_num=user_noti_num)
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/hit')   #TODO: 制导导弹打击模拟特效页面，需要添加特效 -> 点击长按特效 -> 长安5s后确定打击位置特效 -> 消失
def hit():
    return render_template('hit.html')
    

@app.route("/get_ai", methods=["GET", "POST"])
def AiChat():
    if request.method == "POST":
        user_input = request.json.get("q")
    else:
        user_input = request.args.get("q")
        
    if not user_input:
        return jsonify({"error": "Message is required"}), 400  # error messages printed in the console
    
    # 获取讯飞API返回的流数据
    spark_response = get_spark_response(user_input)
    html_response = markdown.markdown(spark_response, extensions=[FencedCodeExtension()])
    return html_response


@app.route('/modify_schedule', methods=['POST'])
def modify_schedule():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    data = request.get_json()
    title = data.get('title')
    content = data.get('content')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    class_level = data.get('class')
    print(data)

    # 转换时间格式
    try:
        start_time = datetime.fromisoformat(start_time.replace('Z', ''))
        end_time = datetime.fromisoformat(end_time.replace('Z', ''))
    except ValueError as e:
        return jsonify({'success': False, 'message': f'Invalid time format: {str(e)}'}), 400

    try:
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO schedule (user_id, title, content, start_time, end_time, class)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session['user_id'], title, content, start_time.strftime('%Y-%m-%d %H:%M:%S'), 
                 end_time.strftime('%Y-%m-%d %H:%M:%S'), class_level))
            conn.commit()
            return jsonify({
                'success': True,
                'message': 'Schedule added successfully',
                'schedule_id': cursor.lastrowid  # 返回新创建的日程ID
            }), 200
    except sqlite3.Error as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/update_schedule', methods=['PUT'])
def update_schedule():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json()
    task_id = data.get('id')
    title = data.get('title')
    content = data.get('content')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    class_level = data.get('class')

    try:
        start_time = datetime.fromisoformat(start_time.replace('Z', ''))
        end_time = datetime.fromisoformat(end_time.replace('Z', ''))
    except ValueError as e:
        return jsonify({'success': False, 'message': f'Invalid time format: {str(e)}'}), 400

    try:
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE schedule SET
                title = ?, content = ?, start_time = ?, end_time = ?,
                class = ?
                WHERE id = ? AND user_id = ?
            ''', (
                title, content, start_time.strftime('%Y-%m-%d %H:%M:%S'), 
                end_time.strftime('%Y-%m-%d %H:%M:%S'), class_level,
                task_id, session['user_id']
            ))
            conn.commit()

            # 返回更新后的日程数据
            cursor.execute('SELECT * FROM schedule WHERE id = ?', (task_id,))
            updated_task = cursor.fetchone()
            if updated_task:
                return jsonify({
                    'success': True,
                    'message': 'Schedule updated successfully',
                    'task': updated_task
                }), 200
            else:
                return jsonify({'success': False, 'message': 'Task not found'}), 404
    except sqlite3.Error as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/get_schedule', methods=['GET'])
def get_schedule():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    start_time = request.args.get('start')
    end_time = request.args.get('end')

    try:
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM schedule 
                WHERE user_id = ? AND start_time >= ? AND end_time <= ?
            ''', (session['user_id'], start_time, end_time))
            schedule = cursor.fetchall()

            if not schedule:
                return jsonify({'schedule': []}), 200

            # 添加星期几信息
            updated_schedule = []
            for task in schedule:
                date_str = task[4]  # start_time 是第5列
                date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                day_of_week = date_obj.strftime("%A")
                updated_task = task + (day_of_week,)
                updated_schedule.append(updated_task)

            return jsonify({'schedule': updated_schedule}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_schedule/<int:task_id>', methods=['GET'])
def get_single_schedule(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM schedule 
                WHERE id = ? AND user_id = ?
            ''', (task_id, session['user_id']))
            task = cursor.fetchone()

            if not task:
                return jsonify({'error': 'Schedule not found'}), 404

            return jsonify({
                'id': task[0],
                'title': task[2],
                'content': task[3],
                'start_time': task[4].replace(' ', 'T'),  # 转换为前端需要的格式
                'end_time': task[5].replace(' ', 'T'),
                'class': task[6]
            }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/delete_schedule/<int:task_id>', methods=['DELETE'])
def delete_schedule(task_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM schedule WHERE id = ? AND user_id = ?', 
                         (task_id, session['user_id']))
            conn.commit()
            return jsonify({
                'success': True,
                'message': 'Schedule deleted successfully'
            }), 200
    except sqlite3.Error as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/update_schedule', methods=['PUT'])
def update_schedule_put():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    task_id = request.form.get('id')
    title = request.form.get('title')
    content = request.form.get('content')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    class_level = request.form.get('class')

    try:
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''UPDATE schedule SET
                title = ?, content = ?, start_time = ?, end_time = ?,
                class = ? WHERE id = ? AND user_id = ?''',
                (title, content, start_time, end_time, class_level,
                 task_id, session['user_id']))
            conn.commit()
            return jsonify({'success': True})
    except sqlite3.Error as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/random_bv', methods=['GET'])
def random_bv():
    videos = get_random_bv()
    if videos:
        return jsonify({'videos': videos}), 200
    return jsonify({'error': 'Failed to fetch BV IDs,刷新试试'}), 500


@app.route('/shutdown', methods=['POST'])
def shutdown():
    if 'username' in session and session['username'] == "David Zhang":
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()
        return jsonify({'status': 'success', 'message': 'Server shutting down...'})
    else:
        return jsonify({'status': 'error', 'message': 'Unauthorized access'}), 403


@app.route('/restart', methods=['POST'])
def restart():
    if 'username' in session and session['username'] == "David Zhang":
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()
        # 启动新的进程来重新启动服务器
        subprocess.Popen(["python", "server.py"])
        return jsonify({'status': 'success', 'message': 'Server restarting...'})
    else:
        return jsonify({'status': 'error', 'message': 'Unauthorized access'}), 403


@app.route('/search_videos', methods=['GET'])
def search_videos():
    page_size = request.args.get('page_size', 10, type=int)
    keyword = request.args.get('keyword', '', type=str)
    if not keyword:
        return jsonify({'error': '关键词不能为空'}), 400
    
    # 请求 B 站搜索 API
    search_url = f"https://api.bilibili.com/x/web-interface/wbi/search/type?page_size={page_size}&keyword={urllib.parse.quote(keyword)}&search_type=video"
    try:
        response = requests.get(search_url, headers=headers)
        if response.status_code != 200:
            return jsonify({'error': '请求失败'}), 500
        
        data = response.json()
        if data['code'] != 0:
            return jsonify({'error': data['message']}), 500
        
        # 提取视频信息并添加合集信息
        videos = []
        for video in data['data']['result']:
            # 获取合集信息
            bvid = video['bvid']
            series_info = get_series_info(bvid, headers)
            
            video_data = {
                'bv_id': bvid,
                'title': video['title'],
                'duration': video['duration'],
                'author': video['author'],
                'is_series': False,
                'sub_videos': []
            }
            
            if series_info:
                video_data['is_series'] = series_info['is_series']
                video_data['sub_videos'] = series_info['sub_videos']
                video_data['duration'] = series_info['duration']
            
            videos.append(video_data)
        
        return jsonify({'videos': videos}), 200
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': '请求失败'}), 500

@app.route('/bkend', methods=['GET', 'POST'])
def bkend():
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
        return render_template('bkend.html')
    else:
        return "访问无效"


#profile page
@app.route('/settings/profile')
def profile():
    if 'user_id' not in session:
        flash('You need to log in to access the dashboard.', 'warning')
        return redirect(url_for('login'))
    with sqlite3.connect('app.db') as conn:
        cursor = conn.cursor()
        # 获取用户头像路径
        cursor.execute('''
        SELECT avatar_route, bio, sex, birthday, email, classroom
        FROM users
        WHERE id = ?
    ''', (session['user_id'],))
        result = cursor.fetchone()
        if result:
            avatar_route = result[0]
            bio = result[1]
            sex = result[2]
            birthday = result[3]
            email = result[4]
            classroom = result[5]
    return render_template('profile.html', avatar_route="/avatar/"+avatar_route, bio = bio, sex = sex, birthday = birthday, email = email, classroom = classroom)


@app.route('/settings/update_profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401  # 返回 JSON

    user_id = session['user_id']

    # 获取表单数据
    username = request.form.get('username')
    bio = request.form.get('bio')
    sex = request.form.get('sex')
    birthday = request.form.get('birthday')
    email = request.form.get('email')
    classroom = request.form.get('classroom')

    # 处理文件上传
    avatar = request.files.get('avatar')
    avatar_filename = None

    if avatar and avatar.filename != '':
        # 生成随机文件名
        random_filename = str(uuid.uuid4()) + os.path.splitext(avatar.filename)[1]
        avatar_path = os.path.join(app.config['USERS_SETTING'], 'avatar', random_filename)
        
        # 保存文件
        avatar.save(avatar_path)
        avatar_filename = random_filename

        # 删除旧的头像文件（除了 noface.jpg）
        conn = sqlite3.connect('app.db')
        cursor = conn.cursor()
        cursor.execute('SELECT avatar_route FROM users WHERE id = ?', (user_id,))
        old_avatar = cursor.fetchone()
        if old_avatar and old_avatar[0] != 'noface.jpg':
            old_avatar_path = os.path.join(app.config['USERS_SETTING'], 'avatar', old_avatar[0])
            if os.path.exists(old_avatar_path):
                os.remove(old_avatar_path)

    # 更新数据库
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()

    if avatar_filename:
        # 如果有新头像，更新头像路径
        cursor.execute('''
            UPDATE users
            SET username = ?, bio = ?, sex = ?, birthday = ?, email = ?, classroom = ?, avatar_route = ?
            WHERE id = ?
        ''', (username, bio, sex, birthday, email, classroom, avatar_filename, user_id))
    else:
        # 如果没有新头像，只更新其他信息
        cursor.execute('''
            UPDATE users
            SET username = ?, bio = ?, sex = ?, birthday = ?, email = ?, classroom = ?
            WHERE id = ?
        ''', (username, bio, sex, birthday, email, classroom, user_id))

    conn.commit()
    cursor.close()
    conn.close()

    # 更新 session 中的用户名和头像路径
    session['username'] = username
    if avatar_filename:
        session['avatar_route'] = avatar_filename

    # 返回成功响应
    return jsonify({'success': True, 'message': 'Profile updated successfully'})

@app.route('/user/<int:user_id>')
def view_profile(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))  # 如果用户未登录，重定向到登录页面

    # 连接数据库
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()

    # 查询目标用户的详细信息
    cursor.execute('''
        SELECT avatar_route, username, bio, sex, birthday, email, classroom
        FROM users
        WHERE id = ?
    ''', (user_id,))
    result = cursor.fetchone()  # 获取查询结果

    if result:
        # 解包查询结果
        avatar_route, username, bio, sex, birthday, email, classroom = result
    else:
        # 如果没有找到用户，返回 404 错误
        return "User not found", 404
    cursor.execute('SELECT avatar_route FROM users WHERE id = ?', (session['user_id'],))
    result = cursor.fetchone()
    if result:
        mavatar_route = result[0]
    # 关闭数据库连接
    cursor.close()
    conn.close()

    # 渲染模板并传递目标用户的信息
    return render_template(
        'users.html',
        uavatar_route="/avatar/"+avatar_route,
        username=username,
        bio=bio,
        sex=sex,
        birthday=birthday,
        email=email,
        classroom=classroom,
        mavatar_route="/avatar/"+mavatar_route
    )

@app.route('/chat', methods=['GET'])
def render_chat():
    if 'user_id' not in session:
        flash('You need to log in to access the chat.', 'warning')
        return redirect(url_for('login'))
    
    with sqlite3.connect('app.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT messages.*, files.filename FROM messages LEFT JOIN files ON messages.file_id = files.id ORDER BY time ASC')
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
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            if file:
                filename = file.filename
                user_folder = os.path.join(app.config['UPLOAD_FOLDER'], username)
                if not os.path.exists(user_folder):
                    os.makedirs(user_folder)
                file_path = os.path.join(user_folder, filename)
                file.save(file_path)
                
                cursor.execute('INSERT INTO files (filename, filepath) VALUES (?, ?)', (filename, file_path))
                file_id = cursor.lastrowid
            else:
                file_id = None

            chat_timestamp = time.time()
            chat_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(chat_timestamp))
            cursor.execute(
                'INSERT INTO messages (user_id, username, message, time, file_id) VALUES (?, ?, ?, ?, ?)',
                (session['user_id'], username, message, chat_time, file_id)
            )
            conn.commit()

        # 使用 SocketIO 广播消息
        socketio.emit('new_message', {
            'username': username,
            'message': message,
            'filename': filename,
            'filepath': url_for('uploaded_file', user=username, filename=filename) if filename else None
        })

        return jsonify({
            'status': 'success',
            'message': message,
            'filename': filename,
            'filepath': url_for('uploaded_file', user=username, filename=filename) if filename else None
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/b_dl')
def bilibili_dl():
    if 'user_id' not in session:
        flash('You need to log in to access the dashboard.', 'warning')
        return redirect(url_for('login'))
    with sqlite3.connect('app.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM notifications ORDER BY time DESC')
        notifications = cursor.fetchall()
        
        # 获取用户头像路径
        cursor.execute('SELECT avatar_route FROM users WHERE id = ?', (session['user_id'],))
        result = cursor.fetchone()
        if result:
            avatar_route = result[0]
        
        # 获取通知总数
        cursor.execute('SELECT COUNT(*) FROM notifications')
        total_notifications = cursor.fetchone()[0]
        
        # 获取用户的未读通知数
        cursor.execute('SELECT noti_num FROM users WHERE id = ?', (session['user_id'],))
        user_noti_num = cursor.fetchone()[0]
    
    return render_template('dl_b.html', 
                           notifications=notifications, 
                           avatar_route="/avatar/"+avatar_route,
                           total_notifications=total_notifications,
                           user_noti_num=user_noti_num)

def convert_video_to_mp4(input_path, output_path):
    command = [
        'ffmpeg',
        '-y',  # 自动覆盖现有文件
        '-i', input_path,
        '-c:v', 'libx264',  # 使用 H.264 编码
        '-c:a', 'aac',      # 使用 AAC 音频编码
        '-strict', 'experimental',
        output_path
    ]
    try:
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting video: {e}")
        return False

@app.route('/mark_notifications_as_read', methods=['POST'])
def mark_notifications_as_read():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM notifications')
            total_notifications = cursor.fetchone()[0]
            cursor.execute('UPDATE users SET noti_num = ? WHERE id = ?', (total_notifications, session['user_id']))
            conn.commit()
        return jsonify({'success': True, 'message': 'Notifications marked as read'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/bv/<bv_id>', methods=['GET'])
def download_bv(bv_id):
    # 是否进行精校
    refine = request.args.get('refine', 'false').lower() == 'true'

    # 是否指定分集
    p = request.args.get('p', None)

    # 构建输出路径
    if p:
        output_path = os.path.join(app.config['BILIBILI_FOLDER'], f'{bv_id}_p{p}.mp4')
        temp_output_path = os.path.join(app.config['BILIBILI_FOLDER'], f'{bv_id}_p{p}_temp.mp4')
    else:
        output_path = os.path.join(app.config['BILIBILI_FOLDER'], f'{bv_id}.mp4')
        temp_output_path = os.path.join(app.config['BILIBILI_FOLDER'], f'{bv_id}_temp.mp4')

    # 添加到正在处理的视频集合
    with processing_lock:
        processing_videos.add(temp_output_path)

    try:
        # 下载指定分集或整个视频
        if p:
            download_bilibili_video_p(bv_id, p, temp_output_path)
        else:
            download_bilibili_video(bv_id, temp_output_path)

        # 转换视频编码（如果需要）
        if refine:
            if convert_video_to_mp4(temp_output_path, output_path):
                os.remove(temp_output_path)  # 删除临时文件
            else:
                return jsonify({'status': 'error', 'message': 'Failed to convert video'}), 500
        else:
            # 不进行精校，直接返回下载的视频
            os.rename(temp_output_path, output_path)

        # 构建返回结果
        response_data = {
            'status': 'success',
            'output_path': url_for('uploaded_bv', filename=os.path.basename(output_path)),
            'series': get_series_info(bv_id, headers) if p is None else None  # 如果没有指定 p，返回合集信息
        }
        return jsonify(response_data), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

    finally:
        # 移除临时文件路径
        with processing_lock:
            processing_videos.discard(temp_output_path)

@app.route('/other_videos', methods=['GET'])
def other_videos():
    if not os.path.exists(app.config['BILIBILI_FOLDER']):
        return jsonify({'videos': []})
    videos = []
    for filename in os.listdir(app.config['BILIBILI_FOLDER']):
        if filename.endswith('.mp4'):
            videos.append({'path': url_for('uploaded_bv', filename=filename)})

    return jsonify({'videos': videos})

@app.route('/gv/<filename>')
def uploaded_bv(filename):
    return send_from_directory(app.config['BILIBILI_FOLDER'], filename)


@app.route('/uploads/<user>/<filename>')
def uploaded_file(user, filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], user), filename)

@app.route('/avatar/<avname>')
def avatar_file(avname):
    return send_from_directory(os.path.join(app.config['USERS_SETTING'], 'avatar'), avname)

# QS part
# QS主页面
@app.route('/qs')
def index():
    db = get_qsdb()
    surveys = db.execute('SELECT * FROM surveys').fetchall()
    return render_template('qshall.html', surveys=surveys)

# 创建问卷路由
@app.route('/create', methods=['GET'])
def create_survey():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # 处理问卷创建逻辑
        pass
    
    return render_template('create.html')

# 删除问卷路由
@app.route('/survey/<int:survey_id>', methods=['DELETE'])
def delete_survey(survey_id):
    if 'user_id' not in session:
        return 'Unauthorized', 401
    
    db = get_qsdb()
    try:
        # 验证问卷所有权
        survey = db.execute('SELECT * FROM surveys WHERE id = ? AND creator_id = ?', 
                          (survey_id, session['user_id'])).fetchone()
        if not survey:
            return '问卷不存在', 404
        
        # 删除相关数据
        db.execute('DELETE FROM responses WHERE survey_id = ?', (survey_id,))
        db.execute('DELETE FROM questions WHERE survey_id = ?', (survey_id,))
        db.execute('DELETE FROM surveys WHERE id = ?', (survey_id,))
        db.commit()
        return '', 204
    except Exception as e:
        db.rollback()
        return str(e), 500

@app.route('/survey/<int:survey_id>', methods=['GET', 'POST'])
def take_survey(survey_id):
    db = get_qsdb()
    
    if request.method == 'POST':
        user_id = session.get('user_id')
        
        # 获取所有问题（确保查询包含 options 字段）
        questions = db.execute('''
            SELECT id, type, options FROM questions WHERE survey_id = ?
        ''', (survey_id,)).fetchall()
        
        # 处理每个问题的答案
        for q in questions:
            q_id = q['id']
            q_type = q['type']
            
            if q_type == 'checkbox':
                # 处理多选答案
                answers = request.form.getlist(f'q_{q_id}[]')
                for answer in answers:
                    db.execute('''
                        INSERT INTO responses (survey_id, question_id, user_id, answer, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (survey_id, q_id, user_id, answer, datetime.now()))
            else:
                # 处理单选/文本/图片等答案
                answer = request.form.get(f'q_{q_id}')
                if answer:
                    db.execute('''
                        INSERT INTO responses (survey_id, question_id, user_id, answer, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (survey_id, q_id, user_id, answer, datetime.now()))
        
        db.commit()
        return redirect(url_for('index'))
    
    # GET 请求：渲染问卷页面
    survey = db.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,)).fetchone()
    # 修改后（确保包含options）
    questions = db.execute('''
        SELECT id, type, content, options
        FROM questions 
        WHERE survey_id = ? 
        ORDER BY id ASC
    ''', (survey_id,)).fetchall()
    
    return render_template('survey.html', survey=survey, questions=questions)

@app.route('/create', methods=['POST'])
def handle_create():
    print("进入handle_create路由")
    if 'user_id' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('login'))

    try:
        db = get_qsdb()
        cursor = db.cursor()

        # 1. 插入问卷
        survey_title = request.form.get('survey_title', '').strip()
        if not survey_title:
            flash('问卷标题不能为空', 'error')
            return redirect(url_for('create_survey'))

        cursor.execute('''
            INSERT INTO surveys (title, creator_id, created_at)
            VALUES (?, ?, ?)
        ''', (survey_title, session['user_id'], datetime.now()))
        survey_id = cursor.lastrowid

        # 2. 处理问题
        questions_dict = {}

        # 处理表单字段
        for key in request.form:
            if not key.startswith('q_'):
                continue
            parts = key.split('_')
            if len(parts) < 4:  # 字段名格式：q_type_index_subtype...
                continue
            q_type = parts[1]
            q_index = parts[2]
            field_subtype = parts[3]

            # 确保 q_index 是数字
            try:
                q_index = int(q_index)
            except ValueError:
                print(f"无效的问题索引: {q_index}")
                continue

            question_id = f"{q_type}_{q_index}"

            if question_id not in questions_dict:
                questions_dict[question_id] = {
                    'type': q_type,
                    'content': None,
                    'options': []
                }

            # 处理题干
            if field_subtype == 'question':
                content = request.form[key].strip()
                questions_dict[question_id]['content'] = content
            # 处理选项
            elif field_subtype == 'option':
                option_value = request.form[key].strip()
                if option_value:
                    questions_dict[question_id]['options'].append(option_value)

        # 3. 插入问题到数据库
        for question_id in questions_dict:
            question = questions_dict[question_id]
            q_type = question['type']
            content = question['content']
            options = question['options']

            if q_type in ['radio', 'checkbox']:
                if not content:
                    continue  # 题干为空则跳过
                # 对选项按字段索引排序
                try:
                    sorted_options = sorted(options, key=lambda x: int(x.split('_')[-1]))
                except (ValueError, IndexError):
                    sorted_options = options  # 如果无法排序，直接使用原始选项
                cursor.execute('''
                    INSERT INTO questions (survey_id, type, content, options)
                    VALUES (?, ?, ?, ?)
                ''', (survey_id, q_type, content, json.dumps(sorted_options)))
            elif q_type in ['text', 'input']:
                if not content:
                    continue
                cursor.execute('''
                    INSERT INTO questions (survey_id, type, content)
                    VALUES (?, ?, ?)
                ''', (survey_id, q_type, content))

        db.commit()
        flash('问卷创建成功', 'success')
        return redirect(url_for('manage'))

    except Exception as e:
        db.rollback()
        print(f"创建问卷失败: {str(e)}")
        flash('问卷创建失败，请稍后重试', 'error')
        return redirect(url_for('create_survey'))


@app.route('/manage/<int:survey_id>')
def manage_detail(survey_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_qsdb()
    
    # 验证问卷归属
    survey = db.execute('''
        SELECT * FROM surveys 
        WHERE id = ? AND creator_id = ?
    ''', (survey_id, session['user_id'])).fetchone()
    
    if not survey:
        return "问卷不存在或无权访问", 404
    
    # 获取总参与人数
    total_responses = db.execute('''
        SELECT COUNT(DISTINCT user_id) as total 
        FROM responses 
        WHERE survey_id = ?
    ''', (survey_id,)).fetchone()['total']
    
    # 获取所有问题
    questions = db.execute('''
        SELECT * FROM questions 
        WHERE survey_id = ?
    ''', (survey_id,)).fetchall()

    # 获取统计信息
    stats = {}
    for q in questions:
        if q['type'] in ['radio', 'checkbox']:
            res = db.execute('''
                SELECT answer, COUNT(*) as count 
                FROM responses 
                WHERE question_id = ?
                GROUP BY answer
            ''', (q['id'],)).fetchall()
            
            # 处理多选题的合并统计
            if q['type'] == 'checkbox':
                merged_data = {}
                for row in res:
                    # 分割多个选项（例如："A,B" -> ["A","B"]）
                    # print(row['answer'])
                    for opt in row['answer'].split("\n"):
                        merged_data[opt.strip()] = merged_data.get(opt.strip(), 0) + row['count']
                res = [{'answer': k, 'count': v} for k, v in merged_data.items()]
            
            # 生成选项数据
            options = json.loads(q['options'])
            data = [next((row['count'] for row in res if row['answer'] == opt), 0) for opt in options]
            
            stats[q['id']] = {
                'question': q['content'],
                'type': q['type'],
                'options': options,
                'data': {row['answer']: row['count'] for row in res},
                'chart_data': data  # 新增字段
            }
    
    # 获取原始回答数据
    raw_responses = db.execute('''
        SELECT r.*, u.username 
        FROM responses r
        LEFT JOIN users u ON r.user_id = u.id
        WHERE r.survey_id = ?
        ORDER BY r.created_at DESC
    ''', (survey_id,)).fetchall()

    # 按用户分组
    response_groups = {}
    for resp in raw_responses:
        key = resp['user_id'] or resp['created_at']  # 匿名用户用时间戳标识
        if key not in response_groups:
            response_groups[key] = {
                'user': resp['username'] or '匿名用户',
                'time': resp['created_at'],
                'answers': {}
            }
        if resp['question_id'] not in response_groups[key]['answers']:
            response_groups[key]['answers'][resp['question_id']] = resp['answer']
        else:
            response_groups[key]['answers'][resp['question_id']] += f", {resp['answer']}"

    return render_template('manage_detail.html', 
                        survey=survey, 
                        total_responses=total_responses,
                        stats=stats,
                        response_groups=response_groups,
                        questions=questions)

# 管理后台
@app.route('/manage')
def manage():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_qsdb()
    surveys = db.execute('''
        SELECT s.id, s.title, COUNT(r.id) as responses 
        FROM surveys s
        LEFT JOIN responses r ON s.id = r.survey_id
        WHERE s.creator_id = ?
        GROUP BY s.id
    ''', (session['user_id'],)).fetchall()
    
    return render_template('manage.html', surveys=surveys)

if __name__ == '__main__':
    init_folders()
    init_db()
    socketio.run(app, host='0.0.0.0', debug=True, port=1002)