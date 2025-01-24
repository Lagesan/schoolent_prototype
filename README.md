# Schoolent Prototype

This is a prototype of Schoolent Web edition based on Flask.

## Features

- User registration and login
- Dashboard with notifications
- AI chat integration using Spark API
- Real-time chat with file upload support
- Socket.IO for real-time communication
- Marked.js for markdown rendering
- Bilibili video download
- User profile management with avatar upload
- Backend management for admin users
- Video conversion using FFmpeg

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/lagesan/schoolent_prototype.git
    cd schoolent_prototype
    ```

2. Create a virtual environment and activate it:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. Install the required packages:
    ```bash
    pip install -r requirements.txt
    ```

4. Initialize the database:
    ```bash
    python server.py
    ```

## Usage

1. Run the Flask application:
    ```bash
    python server.py
    ```
2. Edit settings in [server.set](http://_vscodecontentref_/1) (it will be created after you first run [server.py](http://_vscodecontentref_/2)).
    Setting example (meaningless API key): 
    [authorization=Bearer AEOuoKKfZsasdNQ:kDmSDCDBsfcd](http://_vscodecontentref_/3)

3. Open your web browser and navigate to `http://localhost:1002`.

## Project Structure

- [server.py](http://_vscodecontentref_/4): Main application file containing routes and logic.
- [templates](http://_vscodecontentref_/5): Directory containing HTML templates.
- [uploads](http://_vscodecontentref_/6): Directory for uploaded files.
- [app.db](http://_vscodecontentref_/7): SQLite database file (generated automatically).
- [server.set](http://_vscodecontentref_/8): Server settings, used to set Spark Lite LLM API (generated automatically).
- [chat](http://_vscodecontentref_/9): Directory for private chat files.
- [users](http://_vscodecontentref_/10): Directory for user settings, including avatars.
- [gv](http://_vscodecontentref_/11): Directory for Bilibili video downloads.

## Dependencies

- Flask
- Flask-SocketIO
- SQLite
- Requests
- Marked.js
- Python （above 3.6）
- FFmpeg 4.2.2

## Others
**Fonts**:
- [Pacifico](https://fonts.google.com/specimen/Pacifico)
- [iconfont](https://www.iconfont.cn/) (We use several iconfonts from it)

## License

We are thinking about it.

## Acknowledgements

- [Flask](https://flask.palletsprojects.com/)
- [Socket.IO](https://socket.io/)
- [Marked.js](https://marked.js.org/)
- [Spark API](https://spark-api-open.xf-yun.com/)

## Reference
- Bilibili API: [click here](https://www.bilibili.com/opus/552172175376927649)