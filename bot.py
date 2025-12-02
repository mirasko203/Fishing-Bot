import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3

TOKEN = "8274762616:AAEACranVlE_MWbd2wIwiJrkIUcdLGbcgf4"
CATS_PER_PAGE = 10
ADMIN_CODE = "1234"

bot = telebot.TeleBot(TOKEN)
DB_NAME = "shop.db"
admin_sessions = {}  # chat_id: True если админ вошёл

# -------------------------------
# Работа с базой
# -------------------------------
def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # Таблицы
    cur.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT, slot INTEGER UNIQUE)")
    cur.execute("CREATE TABLE IF NOT EXISTS subcats (id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT, slot INTEGER, FOREIGN KEY(category_id) REFERENCES categories(id))")
    cur.execute("CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, subcat_id INTEGER, name TEXT, amount INTEGER, FOREIGN KEY(subcat_id) REFERENCES subcats(id))")
    cur.execute("CREATE TABLE IF NOT EXISTS admin (id INTEGER PRIMARY KEY, code TEXT)")
    # 35 пустых категорий
    for i in range(1, 36):
        cur.execute("INSERT OR IGNORE INTO categories (slot, name) VALUES (?, ?)", (i, f"Пусто {i}"))
    # Код админа
    cur.execute("SELECT * FROM admin")
    if not cur.fetchone():
        cur.execute("INSERT INTO admin (code) VALUES (?)", (ADMIN_CODE,))
    conn.commit()
    conn.close()

init_db()

# -------------------------------
# Работа с данными
# -------------------------------
def get_categories_page(page):
    start = (page-1)*CATS_PER_PAGE
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id,name FROM categories ORDER BY slot LIMIT ? OFFSET ?", (CATS_PER_PAGE, start))
    cats = cur.fetchall()
    conn.close()
    return cats

def get_subcategories(cat_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id,name FROM subcats WHERE category_id=? ORDER BY slot", (cat_id,))
    subs = cur.fetchall()
    conn.close()
    return subs

def get_items(sub_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id,name,amount FROM items WHERE subcat_id=?", (sub_id,))
    items = cur.fetchall()
    conn.close()
    return items

def get_cat_by_sub(sub_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT category_id FROM subcats WHERE id=?", (sub_id,))
    cat_id = cur.fetchone()[0]
    conn.close()
    return cat_id

def check_admin_code(code):
    return code == ADMIN_CODE

# -------------------------------
# Функции админа
# -------------------------------
def rename_category(cat_id, new_name):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE categories SET name=? WHERE id=?", (new_name, cat_id))
    conn.commit()
    conn.close()

def rename_subcategory(sub_id, new_name):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE subcats SET name=? WHERE id=?", (new_name, sub_id))
    conn.commit()
    conn.close()

def add_subcategory(cat_id, name):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT MAX(slot) FROM subcats WHERE category_id=?", (cat_id,))
    max_slot = cur.fetchone()[0]
    if not max_slot:
        max_slot = 0
    cur.execute("INSERT INTO subcats (category_id,name,slot) VALUES (?,?,?)", (cat_id,name,max_slot+1))
    conn.commit()
    conn.close()

def add_item(subcat_id, name, amount):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO items (subcat_id,name,amount) VALUES (?,?,?)", (subcat_id,name,amount))
    conn.commit()
    conn.close()

def edit_item_amount(item_id, amount):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE items SET amount=? WHERE id=?", (amount,item_id))
    conn.commit()
    conn.close()

def delete_item(item_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

# -------------------------------
# Главное меню
# -------------------------------
@bot.message_handler(commands=['start'])
def start(msg):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📍 Местоположение", callback_data="loc"))
    kb.add(InlineKeyboardButton("🛒 Товары", callback_data="goods_page1"))
    kb.add(InlineKeyboardButton("🔐 Админ", callback_data="admin_enter"))
    bot.send_message(msg.chat.id,"Добро пожаловать в рыболовный магазин!", reply_markup=kb)

# -------------------------------
# Местоположение
# -------------------------------
@bot.callback_query_handler(func=lambda c:c.data=="loc")
def show_location(c):
    bot.answer_callback_query(c.id)
    bot.send_message(c.message.chat.id,"Наш адрес: г. ВашГород, ул. Рыболовная 10")

# -------------------------------
# Пагинация категорий
# -------------------------------
@bot.callback_query_handler(func=lambda c:c.data.startswith("goods_page"))
def show_goods_page(c):
    page=int(c.data.replace("goods_page",""))
    cats=get_categories_page(page)
    kb=InlineKeyboardMarkup()
    for cid,name in cats:
        kb.add(InlineKeyboardButton(name, callback_data=f"cat_{cid}"))
    nav=[]
    if page>1: nav.append(InlineKeyboardButton("⬅️ Назад",callback_data=f"goods_page{page-1}"))
    if len(cats)==CATS_PER_PAGE: nav.append(InlineKeyboardButton("➡️ Далее",callback_data=f"goods_page{page+1}"))
    if nav: kb.row(*nav)
    bot.edit_message_text("Выберите категорию:", c.message.chat.id, c.message.message_id, reply_markup=kb)

# -------------------------------
# Подкатегории
# -------------------------------
@bot.callback_query_handler(func=lambda c:c.data.startswith("cat_"))
def show_subcategories_handler(c):
    cat_id=int(c.data.split("_")[1])
    subs=get_subcategories(cat_id)
    kb=InlineKeyboardMarkup()
    for sid,sname in subs:
        kb.add(InlineKeyboardButton(sname, callback_data=f"sub_{sid}"))
    kb.add(InlineKeyboardButton("⬅️ Назад",callback_data="goods_page1"))
    if admin_sessions.get(c.from_user.id):
        kb.add(InlineKeyboardButton("➕ Добавить подкатегорию",callback_data=f"addsub_{cat_id}"))
        kb.add(InlineKeyboardButton("✏ Изменить название категории",callback_data=f"editcat_{cat_id}"))
    bot.edit_message_text("Выберите подкатегорию или действие:",c.message.chat.id,c.message.message_id,reply_markup=kb)

# -------------------------------
# Товары
# -------------------------------
@bot.callback_query_handler(func=lambda c:c.data.startswith("sub_"))
def show_items_handler(c):
    sub_id=int(c.data.split("_")[1])
    items=get_items(sub_id)
    kb=InlineKeyboardMarkup()
    for iid,name,amount in items:
        kb.add(InlineKeyboardButton(f"{name} — {amount} шт",callback_data=f"edit_item_{iid}"))
    kb.add(InlineKeyboardButton("⬅️ Назад",callback_data=f"cat_{get_cat_by_sub(sub_id)}"))
    if admin_sessions.get(c.from_user.id):
        kb.add(InlineKeyboardButton("➕ Добавить товар",callback_data=f"addprod_{sub_id}"))
        kb.add(InlineKeyboardButton("✏ Изменить название подкатегории",callback_data=f"editsub_{sub_id}"))
    bot.edit_message_text("Список товаров:",c.message.chat.id,c.message.message_id,reply_markup=kb)

# -------------------------------
# Вход админа
# -------------------------------
@bot.callback_query_handler(func=lambda c:c.data=="admin_enter")
def admin_enter(c):
    msg=bot.send_message(c.message.chat.id,"Введите код администратора:")
    bot.register_next_step_handler(msg,check_admin_step)

def check_admin_step(msg):
    if check_admin_code(msg.text):
        admin_sessions[msg.chat.id]=True
        bot.send_message(msg.chat.id,"Доступ разрешён! Теперь вы можете управлять магазином через кнопки.")
    else:
        bot.send_message(msg.chat.id,"❌ Неверный код")

# -------------------------------
# Добавление подкатегории
# -------------------------------
@bot.callback_query_handler(func=lambda c:c.data.startswith("addsub_"))
def add_subcategory_start(c):
    if not admin_sessions.get(c.from_user.id): return
    cat_id=int(c.data.split("_")[1])
    msg=bot.send_message(c.message.chat.id,"Введите название новой подкатегории:")
    bot.register_next_step_handler(msg, lambda m:add_subcat_step(m,cat_id))

def add_subcat_step(msg,cat_id):
    add_subcategory(cat_id,msg.text)
    bot.send_message(msg.chat.id,f"Подкатегория '{msg.text}' добавлена!")

# -------------------------------
# Изменить название категории
# -------------------------------
@bot.callback_query_handler(func=lambda c:c.data.startswith("editcat_"))
def edit_category_start(c):
    if not admin_sessions.get(c.from_user.id): return
    cat_id=int(c.data.split("_")[1])
    msg=bot.send_message(c.message.chat.id,"Введите новое название категории:")
    bot.register_next_step_handler(msg, lambda m:set_new_cat_name(m,cat_id))

def set_new_cat_name(msg,cat_id):
    rename_category(cat_id,msg.text)
    bot.send_message(msg.chat.id,f"Название категории обновлено на '{msg.text}'!")

# -------------------------------
# Изменить название подкатегории
# -------------------------------
@bot.callback_query_handler(func=lambda c:c.data.startswith("editsub_"))
def edit_subcategory_start(c):
    if not admin_sessions.get(c.from_user.id): return
    sub_id=int(c.data.split("_")[1])
    msg=bot.send_message(c.message.chat.id,"Введите новое название подкатегории:")
    bot.register_next_step_handler(msg, lambda m:set_new_sub_name(m,sub_id))

def set_new_sub_name(msg,sub_id):
    rename_subcategory(sub_id,msg.text)
    bot.send_message(msg.chat.id,f"Название подкатегории обновлено на '{msg.text}'!")

# -------------------------------
# Добавить товар
# -------------------------------
@bot.callback_query_handler(func=lambda c:c.data.startswith("addprod_"))
def add_product_start(c):
    if not admin_sessions.get(c.from_user.id): return
    subcat_id=int(c.data.split("_")[1])
    msg=bot.send_message(c.message.chat.id,"Введите название нового товара:")
    bot.register_next_step_handler(msg, lambda m:add_product_name_step(m,subcat_id))

def add_product_name_step(msg,subcat_id):
    name=msg.text
    msg2=bot.send_message(msg.chat.id,"Введите количество товара:")
    bot.register_next_step_handler(msg2, lambda m:add_product_amount_step(m,subcat_id,name))

def add_product_amount_step(msg,subcat_id,name):
    try: amount=int(msg.text)
    except: amount=0
    add_item(subcat_id,name,amount)
    bot.send_message(msg.chat.id,f"Товар '{name}' добавлен!")

# -------------------------------
# Редактирование товара
# -------------------------------
@bot.callback_query_handler(func=lambda c:c.data.startswith("edit_item_"))
def edit_item_menu(c):
    if not admin_sessions.get(c.from_user.id): return
    item_id=int(c.data.split("_")[2])
    kb=InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✏ Изменить количество", callback_data=f"change_amount_{item_id}"))
    kb.add(InlineKeyboardButton("🗑 Удалить товар", callback_data=f"delete_item_{item_id}"))
    bot.edit_message_text("Выберите действие для товара:",c.message.chat.id,c.message.message_id,reply_markup=kb)

@bot.callback_query_handler(func=lambda c:c.data.startswith("change_amount_"))
def change_item_amount(c):
    if not admin_sessions.get(c.from_user.id): return
    item_id=int(c.data.split("_")[2])
    msg=bot.send_message(c.message.chat.id,"Введите новое количество товара:")
    bot.register_next_step_handler(msg, lambda m:set_new_amount(m,item_id))

def set_new_amount(msg,item_id):
    try: new_amount=int(msg.text)
    except: new_amount=0
    edit_item_amount(item_id,new_amount)
    bot.send_message(msg.chat.id,"Количество товара обновлено!")

@bot.callback_query_handler(func=lambda c:c.data.startswith("delete_item_"))
def delete_item_callback(c):
    if not admin_sessions.get(c.from_user.id): return
    item_id=int(c.data.split("_")[2])
    delete_item(item_id)
    bot.answer_callback_query(c.id,"Товар удалён")

# -------------------------------
# Запуск
# -------------------------------
bot.polling(none_stop=True)
