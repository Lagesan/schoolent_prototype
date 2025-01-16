from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify, Response
import sqlite3
import os, time, requests,urllib.parse
import shutil
from flask_socketio import SocketIO, emit
from banalysis import download_bilibili_video
import subprocess, threading, time
import sys

app = Flask(__name__, static_folder='templates/static')
app.secret_key = 'g102'


# 配置数据库连接
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = None
app.config['SESSION_TYPE'] = 'sqlalchemy'
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
                            time TEXT NOT NULL,
                            file_id INTEGER NULL,
                            username TEXT NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS files (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            message_id INTEGER,
                            filename TEXT NOT NULL,
                            filepath TEXT NOT NULL,
                            FOREIGN KEY (message_id) REFERENCES messages (id))''')
        conn.commit()



# prefabricated dictionary prompt
dict_prompt = """
    你是一个专业的翻译器，要求释义准确、详细，请根据以下规则返回信息：
查询的是单词，返回查询单词的所有意思以及音标。
请注意：我可能会输入中文或英文单词来查询。请在返回信息中用 state_code 标识查询类型，其中 state_code 为 "1" 表示返回单词查询。
单词查询示例：
输入：act

{
  "state_code": "1",
  "words": {
    "word": "act",
    "释义": {
      "n.": "幕",
      "vt.": "演"
    },
    "音标": "/ækt/",
    "例句": {
      "英文": "He acted in The Man of La Mancha.",
      "中文": "他出演了《我，堂吉诃德》。"
    }
  }
}

现在我需要查询的是：
"""
sentence_prompt = """
你是一个专业的翻译器，要求释义准确、详细，请根据以下规则返回信息：
查询的是句子，返回句子的中英文翻译。
请注意：我可能会输入中英文句子来查询。请根据输入的内容在返回信息中用 state_code 标识查询类型,为 "2" 表示返回翻译查询。

翻译查询示例：
输入：我们是学生

{
  "state_code": "2",
  "sentence": {
    "cn": "我们是学生。",
    "en": "We are students."
  }
}
现在我需要查询的是：
"""


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




def get_spark_response(user_input):  # 获取讯飞API返回的流数据
    ai_in = ""
    if len(user_input.split()) == 1:
        if all('\u4e00' <= char <= '\u9fff' for char in user_input):
            ai_in = dict_prompt + user_input
        else:
            ai_in = dict_prompt + user_input
    else:
        ai_in = sentence_prompt + user_input
    url = "https://spark-api-open.xf-yun.com/v1/chat/completions"
    data = {
            "model": "general",
            "messages": [
                {
                    "role": 'user',
                    "content": ai_in
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
        print(content)
        return Response(content, content_type="text/plain; charset=utf-8")
    except:
        print("request failed")


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




# 初始化 SocketIO
socketio = SocketIO(app)
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
    return render_template('ai_dict.html')

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
    

@app.route("/searchaidict", methods=["GET", "POST"])
def AiChat():
    if request.method == "POST":
        user_input = request.json.get("word")
    else:
        user_input = request.args.get("word")
        
    if not user_input:
        return jsonify({"error": "Message is required"}), 400 # error messages printed in the console
    
    # 获取讯飞API返回的流数据
    return get_spark_response(user_input)


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
    page_size = request.args.get('page_size', 10)
    keyword = request.args.get('keyword', '')
    if not keyword:
        return jsonify({'error': 'Keyword is required'}), 400
    keyword_encoded = urllib.parse.quote(keyword)
    url = f"https://api.bilibili.com/x/web-interface/wbi/search/type?page_size={page_size}&keyword={keyword_encoded}&search_type=video"
    response = requests.get(url, headers=headers)
    try:
        if response.status_code == 200:
            data = response.json()
            if data['code'] == 0 and 'result' in data['data']:
                videos = [{'bv_id': video['bvid'], 'title': video['title'], 'duration':video['duration'], 'author': video['author']} for video in data['data']['result']]
                return jsonify({'videos': videos}), 200
            else:
                return jsonify({'error': 'No videos found'}), 404
        else:
            return jsonify({'error': 'Failed to fetch videos'}), 500
    except ValueError:
        return jsonify({'error': 'Error decoding JSON response'}), 500

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
    return render_template('dl_b.html')

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

@app.route('/bv/<bv_id>', methods=['GET'])
def download_bv(bv_id):
    refine = request.args.get('refine', 'false').lower() == 'true'
    output_path = os.path.join(app.config['BILIBILI_FOLDER'], f'{bv_id}.mp4')
    temp_output_path = os.path.join(app.config['BILIBILI_FOLDER'], f'{bv_id}_temp.mp4')
    
    with processing_lock:
        processing_videos.add(temp_output_path)
    
    try:
        # 下载视频到临时路径
        download_bilibili_video(bv_id, temp_output_path)
        
        if refine:
            # 转换视频编码
            if convert_video_to_mp4(temp_output_path, output_path):
                os.remove(temp_output_path)  # 删除临时文件
                return jsonify({'status': 'success', 'output_path': url_for('uploaded_bv', filename=f'{bv_id}.mp4')}), 200
            else:
                return jsonify({'status': 'error', 'message': 'Failed to convert video'}), 500
        else:
            # 不进行精校，直接返回下载的视频
            os.rename(temp_output_path, output_path)
            return jsonify({'status': 'success', 'output_path': url_for('uploaded_bv', filename=f'{bv_id}.mp4')}), 200
    finally:
        with processing_lock:
            processing_videos.remove(temp_output_path)

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

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', debug=True, port=1002)
