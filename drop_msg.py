import sqlite3
with sqlite3.connect('app.db') as conn:
    cursor = conn.cursor()
    cursor.execute('''DROP TABLE IF EXISTS messages''')
    cursor.execute('''DROP TABLE IF EXISTS files''')
    conn.commit()
conn.close()