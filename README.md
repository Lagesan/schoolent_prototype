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
- ......

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
2. Edit settings in `server.set`(it will be created after you first run server.py)
    Setting example(meaningless API key): 
    `authorization=Bearer AEOuoKKfZsasdNQ:kDmSDCDBsfcd`

2. Open your web browser and navigate to `http://localhost:1002`.

## Project Structure

- `server.py`: Main application file containing routes and logic.
- `templates/`: Directory containing HTML templates.
- `uploads/`: Directory for uploaded files.
- `app.db`: SQLite database file.(generated automatically)
- `server.set`: server settings, it is only used to set Spark Lite LLM api(generated automatically)
## Dependencies

- Flask
- Flask-SocketIO
- SQLite
- Requests
- Marked.js
- working stably on Python 3.6.5
- work well on ffmpeg 4.2.2

## License

We are thinking about it.

## Acknowledgements

- [Flask](https://flask.palletsprojects.com/)
- [Socket.IO](https://socket.io/)
- [Marked.js](https://marked.js.org/)
- [Spark API](https://spark-api-open.xf-yun.com/)



## Reference
- Bilibili API: [click here](https://www.bilibili.com/opus/552172175376927649)