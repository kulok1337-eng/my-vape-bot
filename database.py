import sqlite3

def init_db():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.0,
            is_courier INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    
    # Таблица категорий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    ''')
    
    # Таблица товаров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name TEXT,
            description TEXT,
            price REAL,
            photo_id TEXT,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')

    # Таблица системных настроек (например, тех. работы)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Начальные категории
    categories = [
        'Подики', 'Одноразки', 'Никотиновые пластинки (вата)',
        'Испарители', 'Шайбы', 'SALE', 'Жижи', 'Картриджи'
    ]
    for cat in categories:
        cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))
            
    conn.commit()
    conn.close()

def get_categories():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    cats = cursor.fetchall()
    conn.close()
    return cats

def add_category(name):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()

def delete_category(cat_id):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    cursor.execute("DELETE FROM products WHERE category_id = ?", (cat_id,))
    conn.commit()
    conn.close()

def rename_category(cat_id, new_name):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE categories SET name = ? WHERE id = ?", (new_name, cat_id))
    conn.commit()
    conn.close()

def add_product_to_db(category_id, name, description, price, photo_id):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (category_id, name, description, price, photo_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (category_id, name, description, price, photo_id))
    conn.commit()
    conn.close()

def update_user_balance(user_id, amount):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def set_courier_status(user_id, status: int):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET is_courier = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()

def get_user_info(user_id):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, balance, is_courier, is_admin FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_all_users_ids():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

if __name__ == '__main__':
    init_db()
