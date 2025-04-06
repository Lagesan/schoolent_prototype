from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify, Response, make_response, abort
import sqlite3, json
import os, time, requests,urllib.parse
import shutil, random
from flask_socketio import SocketIO, emit
from banalysis import *
import subprocess, threading
from markdown.extensions.fenced_code import FencedCodeExtension
from bs4 import BeautifulSoup
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone, timedelta
import uuid, signal
from markdown import markdown as md
import feedparser, re

app = Flask(__name__, static_folder='templates/static')
app.secret_key = os.urandom(24)


# 配置数据库连接
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = None
app.config['SESSION_TYPE'] = 'sqlalchemy'
app.config["PRIVATE_CHAT"] = 'chat/'
app.config["USERS_SETTING"] = 'users/'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['BILIBILI_FOLDER'] = 'gv/'
app.config['COMMUNITY_FOLDER'] = 'community/'

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
        
headers = ''
# config the bilibili request headers from local file:header.set, if not exist create one
if not os.path.exists("header.set"):
    with open("header.set", "w") as f:
        f.write("headers=")

with open('header.set', 'r') as f:
    # read headers from header.set (info after "=")
    info = f.read().strip()
    if info == 'headers=':
        print("Please input the headers of the bilibili api")
    elif info:
        try:
            headers = eval(info.split("=", 1)[1])  # Use eval to parse the dictionary string
            if not isinstance(headers, dict):
                raise ValueError("Parsed headers are not a dictionary.")
        except (SyntaxError, ValueError):
            print("Invalid headers format in header.set. Please check the file content.")
            headers = {}
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

    if not os.path.exists(app.config['COMMUNITY_FOLDER']):
        os.makedirs(app.config['COMMUNITY_FOLDER'])

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
        # notes
        cursor.execute('''CREATE TABLE IF NOT EXISTS notes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            title TEXT NOT NULL,
                            content TEXT NOT NULL,
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME NOT NULL,
                            FOREIGN KEY(user_id) REFERENCES users(id))''')
        # 目标表
        cursor.execute('''CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            due_time TEXT,
            created_at DATETIME NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id))
        ''')
        conn.commit()


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

# 临时存储文章数据
articles = []

# 修改rss_feeds结构（放在全局变量区域）
newspapers = {
    'ppd': {
        'name': '人民日报',
        'feeds': ['http://www.people.com.cn/rss/world.xml'],
        'icon': 'http://www.people.com.cn/favicon.ico'
    },
    'gmb': {
        'name': '光明日报',
        'feeds': ['https://plink.anyfeeder.com/guangmingribao'],
        'icon': 'https://www.gmw.cn/favicon.ico'
    },
    'zxw': {
        'name': '中新网',
        'feeds': ['https://www.chinanews.com.cn/rss/society.xml'],
        'icon': 'https://www.chinanews.com.cn/favicon.ico'
    },
    'k-tech': {
        'name': '快科技',
        'feeds': ['https://plink.anyfeeder.com/mydrivers'],
        'icon': 'https://www.mydrivers.com/favicon.ico'
    },
    'huxiu': {
        'name': '虎嗅网',
        'feeds': ['https://www.huxiu.com/rss/0.xml'],
        'icon': '/avatar/noface.png'
    },
    'bbc':{
        'name': 'BBC',
        'feeds': ['https://plink.anyfeeder.com/bbc/business'],
        'icon': '/avatar/noface.png'
    }
}

def fetch_feeds():
    global articles
    new_articles = []
    article_id = 0  # Initialize article ID
    
    for paper_id, paper_info in newspapers.items():
        for feed_url in paper_info['feeds']:
            retries = 3
            for attempt in range(retries):
                try:
                    feed = feedparser.parse(feed_url)
                    break
                except Exception as e:
                    if attempt == retries - 1:
                        print(f"Failed to fetch {feed_url}: {e}")
                        continue
                    time.sleep(2)
            
            for entry in feed.entries:
                soup = BeautifulSoup(entry.description, 'html.parser')
                for img in soup.find_all('img'):
                    if img.get('src'):
                        # 清理图片URL，去掉可能的查询参数
                        img_url = img['src'].split('?')[0]  # 只取URL路径部分
                        img['src'] = f"/proxy_image?url={img_url}"  # 代理图片请求
                
                new_articles.append({
                    'id': article_id,  # Assign unique ID
                    'paper': paper_id,
                    'title': entry.title,
                    'description': str(soup),
                    'link': entry.link,
                    'published': time.strftime('%Y-%m-%d %H:%M:%S', entry.published_parsed),
                    'content': soup.get_text()
                })
                article_id += 1  # Increment article ID
    
    articles = sorted(new_articles, key=lambda x: x['published'], reverse=True)


# 判断是否登录
def login_required():
    if 'user_id' not in session:
        return redirect(url_for('login'))


# 初始化 SocketIO
socketio = SocketIO(app, async_mode='threading')
online_users = 0
online_user_ids = set()
online_users_lock = threading.Lock()

@socketio.on('connect')
def handle_connect():
    global online_users
    user_id = session.get('user_id')
    
    if user_id:
        with online_users_lock:
            if user_id not in online_user_ids:
                online_users += 1
                online_user_ids.add(user_id)
                print(f"User {user_id} connected. Total online users: {online_users}")
    else:
        print("Anonymous user connected. Not counted in online users.")
    
    # 广播在线人数更新
    emit('update_online_users', {'count': online_users}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    global online_users
    user_id = session.get('user_id')
    
    if user_id:
        with online_users_lock:
            if user_id in online_user_ids:
                online_users -= 1
                online_user_ids.remove(user_id)
                print(f"User {user_id} disconnected. Total online users: {online_users}")
    else:
        print("Anonymous user disconnected.")
    
    # 广播在线人数更新
    emit('update_online_users', {'count': online_users}, broadcast=True)

@app.route('/')    # main page
def home():
    if 'username' in session:   # if user is logged in
        return redirect(url_for('dashboard'))
    else:
        return render_template('index.html')

@app.route('/delete_gv_folder', methods=['POST'])
def delete_gv_folder():
    login_required()
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
    login_required()
    return render_template('aichat.html')

@app.route('/dashboard')
def dashboard():
    login_required()
    
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
    html_response = md(spark_response, extensions=[FencedCodeExtension()])
    return html_response


@app.route('/modify_schedule', methods=['POST'])
def modify_schedule():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    try:
        # 保留时区信息并转换为UTC时间
        start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00')).astimezone(timezone.utc)
        end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00')).astimezone(timezone.utc)
    except (KeyError, ValueError) as e:
        return jsonify({'success': False, 'message': f'Invalid time format: {str(e)}'}), 400

    try:
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO schedule (user_id, title, content, start_time, end_time, class)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                session['user_id'],
                data.get('title'),
                data.get('content'),
                start_time.strftime('%Y-%m-%d %H:%M:%S'),
                end_time.strftime('%Y-%m-%d %H:%M:%S'),
                data.get('class')
            ))
            conn.commit()
            return jsonify({
                'success': True,
                'message': 'Schedule added successfully',
                'schedule_id': cursor.lastrowid
            }), 200
    except sqlite3.Error as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/update_schedule', methods=['PUT'])
def update_schedule():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json()
    try:
        # 统一处理时区转换
        start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00')).astimezone(timezone.utc)
        end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00')).astimezone(timezone.utc)
    except (KeyError, ValueError) as e:
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
                data.get('title'),
                data.get('content'),
                start_time.strftime('%Y-%m-%d %H:%M:%S'),
                end_time.strftime('%Y-%m-%d %H:%M:%S'),
                data.get('class'),
                data.get('id'),
                session['user_id']
            ))
            conn.commit()

            # 返回UTC时间并带Z后缀
            cursor.execute('SELECT * FROM schedule WHERE id = ?', (data.get('id'),))
            updated_task = cursor.fetchone()
            if updated_task:
                return jsonify({
                    'success': True,
                    'message': 'Schedule updated successfully',
                    'task': {
                        'id': updated_task[0],
                        'title': updated_task[2],
                        'content': updated_task[3],
                        'start_time': f"{updated_task[4]}Z",  # 添加UTC标识
                        'end_time': f"{updated_task[5]}Z",
                        'class': updated_task[6]
                    }
                }), 200
            else:
                return jsonify({'success': False, 'message': 'Task not found'}), 404
    except sqlite3.Error as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/get_schedule', methods=['GET'])
def get_schedule():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        # 将查询参数转换为UTC时间
        start_utc = datetime.fromisoformat(request.args['start'].replace('Z', '+00:00')).astimezone(timezone.utc)
        end_utc = datetime.fromisoformat(request.args['end'].replace('Z', '+00:00')).astimezone(timezone.utc)
    except (KeyError, ValueError) as e:
        return jsonify({'error': f'Invalid time format: {str(e)}'}), 400

    try:
        with sqlite3.connect('app.db') as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT *, 
                strftime('%Y-%m-%dT%H:%M:%SZ', start_time) as iso_start,
                strftime('%Y-%m-%dT%H:%M:%SZ', end_time) as iso_end
                FROM schedule 
                WHERE user_id = ? AND start_time >= ? AND end_time <= ?
            ''', (
                session['user_id'],
                start_utc.strftime('%Y-%m-%d %H:%M:%S'),
                end_utc.strftime('%Y-%m-%d %H:%M:%S')
            ))
            schedule = [dict(row) for row in cursor.fetchall()]

            # 添加星期几信息（基于UTC时间）
            for task in schedule:
                date_obj = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                task['day_of_week'] = date_obj.strftime("%A")

            return jsonify({'schedule': schedule}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_schedule/<int:task_id>', methods=['GET'])
def get_single_schedule(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        with sqlite3.connect('app.db') as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT *, 
                strftime('%Y-%m-%dT%H:%M:%SZ', start_time) as iso_start,
                strftime('%Y-%m-%dT%H:%M:%SZ', end_time) as iso_end
                FROM schedule 
                WHERE id = ? AND user_id = ?
            ''', (task_id, session['user_id']))
            task = cursor.fetchone()

            if not task:
                return jsonify({'error': 'Schedule not found'}), 404

            return jsonify(dict(task)), 200
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


@app.route('/random_bv', methods=['GET'])
def random_bv():
    videos = get_random_bv()
    if videos:
        return jsonify({'videos': videos}), 200
    return jsonify({'error': 'Failed to fetch BV IDs,刷新试试'}), 500


@app.route('/shutdown', methods=['POST'])
def shutdown():
    if 'username' in session and session['username'] == "David Zhang":
        # 创建一个线程来关闭服务器
        def shutdown_server():
            print("Shutting down the server...")
            # 发送 SIGTERM 信号给当前进程以关闭服务器
            os.kill(os.getpid(), signal.SIGTERM)
            print("Server terminated.")

        # 创建一个线程来执行 poweroff 命令
        def poweroff_host():
            time.sleep(3)  # 等待3秒，确保服务器关闭逻辑完成
            print("Powering off the host...")
            os.system("poweroff")

        # 启动线程
        shutdown_thread = threading.Thread(target=shutdown_server)
        poweroff_thread = threading.Thread(target=poweroff_host)

        shutdown_thread.start()
        poweroff_thread.start()

        return jsonify({'status': 'success', 'message': 'Server shutting down and host powering off...'})
    else:
        return jsonify({'status': 'error', 'message': 'Unauthorized access'}), 403


@app.route('/restart', methods=['POST'])
def restart():
    if 'username' in session and session['username'] == "David Zhang":
        # 创建一个线程来重启服务器
        def restart_server():
            print("Restarting the server...")
            os.kill(os.getpid(), signal.SIGTERM)  # 发送 SIGTERM 信号关闭服务器
            print("Server terminated. Restarting...")

        # 创建一个线程来重启主机
        def reboot_host():
            time.sleep(3)  # 等待3秒，确保服务器关闭逻辑完成
            os.system("reboot")
        # 启动线程
        restart_thread = threading.Thread(target=restart_server)
        reboot_thread = threading.Thread(target=reboot_host)

        restart_thread.start()
        reboot_thread.start()

        return jsonify({'status': 'success', 'message': 'Server restarting and host rebooting...'})
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
                'pic': "/proxy_image?url=https:"+video['pic'],
                'description': video['description'],
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
    login_required()
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
    login_required()
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
    login_required()

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

#  chat settings
@app.route('/settings/chat')
def chat_settings():
    login_required()
    # 获取用户头像路径
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    cursor.execute('SELECT avatar_route FROM users WHERE id = ?', (session['user_id'],))
    result = cursor.fetchone()
    if result:
        avatar_route = result[0]
    cursor.close()
    conn.close()
    return render_template('chatsetting.html', avatar_route="/avatar/"+avatar_route)

@app.route('/chat', methods=['GET'])
def render_chat():
    login_required()
    
    with sqlite3.connect('app.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT messages.*, files.filename FROM messages LEFT JOIN files ON messages.file_id = files.id ORDER BY time DESC LIMIT 25')
        messages = cursor.fetchall()[::-1]
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
        # 获取用户头像路径
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT avatar_route FROM users WHERE id = ?', (session['user_id'],))
            result = cursor.fetchone()
            avatar_route = result[0] if result else 'noface.jpg'
        # 使用 SocketIO 广播消息
        socketio.emit('new_message', {
            'username': username,
            'message': message,
            'filename': filename,
            'filepath': url_for('uploaded_file', user=username, filename=filename) if filename else None,
            'avatar_route': url_for('avatar_file', avname=avatar_route)
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
    login_required()
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
        # 使用硬件加速编解码器 h264_v4l2m2m
    command = [
        'ffmpeg',
        '-y',  # 自动覆盖现有文件
        '-i', input_path,
        '-c:v', 'h264_v4l2m2m',  # 启用硬件加速的 H.264 编码器
        '-c:a', 'aac',          # 使用 AAC 音频编码
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

@app.template_filter('markdown')
def markdown_filter(content):
    return md(content, extensions=[FencedCodeExtension()])
# note part
@app.route('/notes')
def notes_index():
    login_required()
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
        # 只查询当前用户的笔记
        cursor.execute('''
            SELECT n.id, n.title, n.content, n.created_at, u.username, n.user_id
            FROM notes n
            JOIN users u ON n.user_id = u.id
            WHERE n.user_id = ?
        ''', (session['user_id'],))
        notes = cursor.fetchall()
        # print(notes)
    
    return render_template('notes.html', notes=notes,
                           notifications=notifications, 
                           avatar_route="/avatar/"+avatar_route,
                           total_notifications=total_notifications,
                           user_noti_num=user_noti_num)

# 查看单个笔记
@app.route('/notes/<int:id>')
def view_note(id):
    login_required()
    
    with sqlite3.connect('app.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT n.id, n.title, n.content, n.created_at, n.user_id
            FROM notes n
            WHERE n.id = ?
        ''', (id,))
        note = cursor.fetchone()
        if note:
            # 使用 markdown 将 content 转换为 HTML
            note_content = md(
                note[2],
                extensions=[FencedCodeExtension()]
            )
            cursor.execute('SELECT username FROM users WHERE id = ?', (note[4],))
            user = cursor.fetchone()
            return render_template(
                'view_note.html',
                note_id=note[0],
                title=note[1],
                content=note_content,
                user_id=note[4],
                created_at=note[3],
                user=user[0] if user else 'Unknown'
            )
    return "Note not found", 404

# 创建笔记
@app.route('/notes/create', methods=['GET', 'POST'])
def create_note():
    login_required()
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        user_id = session['user_id']
        created_at = datetime.now()
        updated_at = created_at
        
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO notes (user_id, title, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, title, content, created_at, updated_at))
            conn.commit()
        return redirect(url_for('notes_index'))
    
    return render_template('create_note.html')

@app.route('/notes/<int:id>/edit', methods=['GET', 'POST'])
def edit_note(id):
    login_required()
    
    with sqlite3.connect('app.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM notes WHERE id = ?', (id,))
        note = cursor.fetchone()
    
    if not note:
        flash('Note not found', 'danger')
        return redirect(url_for('notes_index'))
    
    # 检查用户是否有权限编辑
    if note[1] != session['user_id']:
        flash('Permission denied', 'danger')
        return redirect(url_for('view_note', id=id))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        updated_at = datetime.now()
        
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE notes
                SET title = ?, content = ?, updated_at = ?
                WHERE id = ?
            ''', (title, content, updated_at, id))
            conn.commit()
        
        flash('Note updated successfully', 'success')
        return redirect(url_for('view_note', id=id))
    # print(note[0],note[1],note[3])
    
    return render_template(
        'edit_note.html',
        note_id=note[0],
        title=note[2],
        content=note[3]
    )

# 删除笔记
@app.route('/notes/<int:id>/delete', methods=['GET'])
def delete_note(id):
    login_required()
    
    with sqlite3.connect('app.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM notes WHERE id = ?', (id,))
        note = cursor.fetchone()
        if not note:
            return "Note not found", 404
        
        # 检查用户是否有权限删除
        if note[0] != session['user_id']:
            return "Permission denied", 403
        
        cursor.execute('DELETE FROM notes WHERE id = ?', (id,))
        conn.commit()
    return redirect(url_for('notes_index'))

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
    login_required()
    
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
    login_required()

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
    login_required()
    
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
    login_required()
    
    db = get_qsdb()
    surveys = db.execute('''
        SELECT s.id, s.title, COUNT(r.id) as responses 
        FROM surveys s
        LEFT JOIN responses r ON s.id = r.survey_id
        WHERE s.creator_id = ?
        GROUP BY s.id
    ''', (session['user_id'],)).fetchall()
    
    return render_template('manage.html', surveys=surveys)

@app.route('/news')
def news():
    selected_paper = request.args.get('paper', 'all')
    filtered_articles = random.sample(articles, min(20, len(articles)))  # 随机显示20条
    
    if selected_paper != 'all':
        filtered_articles = [a for a in articles if a['paper'] == selected_paper][:20]
    
    return render_template('news.html',
                         articles=filtered_articles,
                         newspapers=newspapers,
                         selected_paper=selected_paper)


@app.route('/article/<int:article_id>')
def article_detail(article_id):
    article = next((a for a in articles if a['id'] == article_id), None)
    if article:
        return render_template('article.html', article=article)
    return "Article not found", 404

@app.route('/proxy_image')
def proxy_image():
    image_url = request.args.get('url')
    if not image_url:
        return "Invalid URL", 400
    
    try:
        response = requests.get(image_url, stream=True)
        if response.status_code == 200:
            headers = {
                'Content-Type': response.headers['Content-Type']
            }
            return make_response(
                response.content,
                response.status_code,
                headers
            )
        return "Failed to fetch image", 502
    except Exception as e:
        return str(e), 500
    
# 添加目标
@app.route('/add_goal', methods=['POST'])
def add_goal():
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    
    data = request.get_json()
    due_time = None
    if data.get('due_time'):
        try:
            local_time = datetime.fromisoformat(data['due_time'])
            due_time = local_time.astimezone(timezone.utc).isoformat()
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid time format'}), 400

    try:
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO goals 
                (user_id, title, due_time, created_at)
                VALUES (?, ?, ?, ?)''',
                (session['user_id'], data['title'], due_time, datetime.utcnow()))
            conn.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# 获取目标
@app.route('/get_goals', methods=['GET'])
def get_goals():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        with sqlite3.connect('app.db') as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''SELECT *, 
                strftime('%Y-%m-%dT%H:%M:%SZ', due_time) as iso_due 
                FROM goals 
                WHERE user_id = ?
                ORDER BY 
                    CASE WHEN due_time IS NULL THEN 1 ELSE 0 END,
                    due_time ASC''',
                (session['user_id'],))
            goals = [dict(row) for row in cursor.fetchall()]
            return jsonify(goals), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 删除目标
@app.route('/delete_goal/<int:goal_id>', methods=['DELETE'])
def delete_goal(goal_id):
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    
    try:
        with sqlite3.connect('app.db') as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM goals WHERE id = ? AND user_id = ?',
                         (goal_id, session['user_id']))
            conn.commit()
            return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# TODO:社区功能
    
if __name__ == '__main__':
    fetch_feeds()
    
    # 创建定时任务（每30分钟更新一次）
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=fetch_feeds, trigger="interval", minutes=30)
    scheduler.start()
    init_folders()
    init_db()
    socketio.run(app, host='0.0.0.0', debug=True, port=1002, allow_unsafe_werkzeug=True)