import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
import hashlib

from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask, render_template, redirect, request, abort, flash, session
from data import db_session
from data.subscribes import Subscribes
from data.users import User
from forms.add_sub import SubscribesForm
from forms.login import LoginForm
from forms.register import RegisterForm
from apscheduler.schedulers.background import BackgroundScheduler
from flask_login import LoginManager, login_user, current_user, login_required, logout_user
from forms.add_sud import SubscridesForm
import requests
from bs4 import BeautifulSoup

# Конфигурация Flask приложения
app = Flask(__name__)
scheduler_flask = BackgroundScheduler()
app.config['SECRET_KEY'] = 'yandexlyceum_secret_key'
login_manager = LoginManager()
login_manager.init_app(app)

# Конфигурация Telegram бота
BOT_TOKEN = "7431447438:AAF2tyceUxIBqQq7kYOXNaj8sxFG8_q7yYw"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

router = Router()
dp = Dispatcher()
dp.include_router(router)

# Состояния для авторизации в боте
class AuthStates(StatesGroup):
    email = State()
    password = State()

# Класс для работы с базой данных
class Database:
    def __init__(self, db_name='db/subscribes.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()

    def verify_password(self, hashed_password, input_password):
        """Проверяем пароль с хешем"""
        return hashed_password == hashlib.sha256(input_password.encode()).hexdigest()

    def get_user_by_email(self, email):
        self.cursor.execute("SELECT id, email, hashed_password, tg_id FROM users WHERE email=?", (email,))
        return self.cursor.fetchone()

    def get_today_subscriptions(self):
        """Получаем подписки, у которых завтра день оплаты (1-31)"""
        today = datetime.now()
        tomorrow_day = (today + timedelta(days=1)).day

        self.cursor.execute("""
        SELECT u.tg_id, s.name_serv, s.price, s.payment_date, s.link 
        FROM subscribes s
        JOIN users u ON s.user_id = u.id
        WHERE s.payment_date = ? AND u.tg_id IS NOT NULL
        """, (tomorrow_day,))
        return self.cursor.fetchall()

    def update_telegram_id(self, email, telegram_id):
        """Обновляем tg_id в таблице users"""
        try:
            self.cursor.execute(
                "UPDATE users SET tg_id = ? WHERE email = ?",
                (telegram_id, email))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при обновлении tg_id: {e}")
            return False

    def close(self):
        self.conn.close()

db = Database()

# Функции для Telegram бота
@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Привет! Я бот для уведомлений о подписках.\n"
        "Для получения уведомлений необходимо авторизоваться.\n"
        "Введите ваш email:"
    )
    await state.set_state(AuthStates.email)

@router.message(AuthStates.email)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    user = db.get_user_by_email(email)

    if not user:
        await message.answer("Пользователь с таким email не найден. Попробуйте еще раз.")
        return

    await state.update_data(email=email, user_id=user[0])
    await message.answer("Введите ваш пароль:")
    await state.set_state(AuthStates.password)

@router.message(AuthStates.password)
async def process_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    email = data['email']
    user = db.get_user_by_email(email)

    if not user[2] == message.text:  # Проверяем хеш пароля
        await message.answer("Неверный пароль. Попробуйте еще раз.")
        return

    if db.update_telegram_id(email, message.from_user.id):
        await message.answer(
            f"✅ Авторизация успешна!\n"
            f"Теперь вы будете получать уведомления о ваших подписках.\n"
            f"Уведомления приходят за день до даты оплаты в 17:00."
        )
    else:
        await message.answer("⚠ Произошла ошибка при сохранении данных. Попробуйте позже.")

    await state.clear()

async def send_daily_notifications(bot: Bot):
    logger.info("Проверка подписок для уведомлений...")
    subscriptions = db.get_today_subscriptions()

    if not subscriptions:
        logger.info("Нет подписок для уведомления сегодня")
        return

    current_month = datetime.now().strftime('%m')
    current_year = datetime.now().strftime('%Y')

    for sub in subscriptions:
        tg_id, name_serv, price, payment_day, link = sub

        # Формируем полную дату следующего платежа
        try:
            payment_date = datetime.strptime(
                f"{current_year}-{current_month}-{payment_day}",
                "%Y-%m-%d"
            ).strftime('%d.%m.%Y')
        except ValueError:
            # Обработка случая, когда дня нет в текущем месяце (например, 31 февраля)
            payment_date = f"{payment_day}-е число следующего месяца"

        message_text = (
            "🔔 Напоминание о подписке!\n\n"
            f"💳 Сервис: {name_serv}\n"
            f"💰 Сумма: {price}\n"
            f"📅 Дата оплаты: {payment_date}\n"
            f"🔗 Ссылка: {link}\n\n"
            f"Оплата требуется завтра!"
        )

        try:
            await bot.send_message(
                chat_id=tg_id,
                text=message_text
            )
            logger.info(f"Уведомление отправлено для tg_id {tg_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления для tg_id {tg_id}: {e}")

async def telegram_bot():
    bot = Bot(token=BOT_TOKEN)

    # Настройка планировщика (каждый день в 19:30)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_daily_notifications,
        'cron',
        hour=18,
        minute=44,
        args=[bot]
    )
    scheduler.start()

    try:
        logger.info("Starting bot...")
        await dp.start_polling(bot)
    finally:
        db.close()
        await bot.session.close()
        scheduler.shutdown()

# Функции для веб-сайта
def auth(username, password):
    data = {
        "username": username,
        "password": password
    }
    url_auth = 'https://elfin-circular-octagon.glitch.me/login'
    url_subscribe = 'https://elfin-circular-octagon.glitch.me/subscription'
    session = requests.Session()
    session.post(url_auth, data=data)
    response = session.get(url_subscribe).text
    soup = BeautifulSoup(response, 'lxml')
    block_main = soup.find('div', class_='container content')
    block_data_1 = block_main.find('div', class_='alert alert-info mb-4')
    block_data_2 = block_data_1.find_all('p')
    block_costs_1 = block_main.find('div', class_='row justify-content-center')
    block_costs_2 = block_costs_1.find('div', class_='card-body text-center')
    block_costs_3 = block_costs_2.find('h4', class_='text-primary')
    return [int(str(block_data_2[0]).split()[-1].split(".")[0]), int(str(block_costs_3)[25: -11])]

@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    return db_sess.query(User).get(user_id)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect("/")

@app.route("/")
def index():
    db_sess = db_session.create_session()
    if current_user.is_authenticated:
        subscribes = db_sess.query(Subscribes).filter(
            (Subscribes.user == current_user) | (Subscribes.is_private != True))
    else:
        subscribes = db_sess.query(Subscribes).filter(Subscribes.is_private != True)
    return render_template("index.html", subscribes=subscribes)

@app.route('/register', methods=['GET', 'POST'])
def reqister():
    form = RegisterForm()
    if form.validate_on_submit():
        if form.password.data != form.password_again.data:
            return render_template('register.html', title='Регистрация',
                                   form=form,
                                   message="Пароли не совпадают")
        db_sess = db_session.create_session()
        if db_sess.query(User).filter(User.email == form.email.data).first():
            return render_template('register.html', title='Регистрация',
                                   form=form,
                                   message="Такой пользователь уже есть")
        user = User(
            name=form.name.data,
            surname=form.surname.data,
            email=form.email.data,
            about=form.about.data
        )
        user.set_password(form.password.data)
        db_sess.add(user)
        db_sess.commit()
        return redirect('/login')
    return render_template('register.html', title='Регистрация', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.email == form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            return redirect("/")
        return render_template('login.html',
                               message="Неправильный логин или пароль",
                               form=form)
    return render_template('login.html', title='Авторизация', form=form)

@app.route('/subscribes',  methods=['GET', 'POST'])
@login_required
def add_subs():
    form = SubscribesForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        subscribes = Subscribes()
        subscribes.name_serv = form.name_serv.data
        subscribes.price = form.price.data
        subscribes.payment_date = form.payment_date.data
        subscribes.link = form.link.data
        current_user.subscribes.append(subscribes)
        db_sess.merge(current_user)
        db_sess.commit()
        return redirect('/')
    return render_template('add_sub.html', title='Добавление подписки',
                           form=form)

@app.route('/subscriber', methods=['GET', 'POST'])
@login_required
def add_suds():
    form = SubscridesForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        try:
            # Получаем данные из формы
            data_diary = auth(form.login.data, form.password.data)

            # Создаем новую подписку
            subscribes = Subscribes(
                name_serv="Harmony Diary",
                price=data_diary[1],
                payment_date=data_diary[0],
                link="https://elfin-circular-octagon.glitch.me/",
                user_id=current_user.id  # Явно устанавливаем связь
            )

            # Добавляем подписку в сессию
            db_sess.add(subscribes)

            # Обновляем пользователя
            if current_user not in db_sess:
                db_sess.merge(current_user)

            db_sess.commit()
            return redirect('/')

        except Exception as e:
            db_sess.rollback()
            flash(f'Ошибка при добавлении подписки: {str(e)}', 'error')
            return render_template('add_sud.html', title='Добавление подписки', form=form)

        finally:
            db_sess.close()

    return render_template('add_sud.html', title='Добавление подписки', form=form)

@app.route('/subscribes/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_subs(id):
    form = SubscribesForm()
    if request.method == "GET":
        db_sess = db_session.create_session()
        subscribes = db_sess.query(Subscribes).filter(Subscribes.id == id).first()
        if subscribes:
            form.name_serv.data = subscribes.name_serv
            form.price.data = subscribes.price
            form.payment_date.data = subscribes.payment_date
            form.link.data = subscribes.link
        else:
            abort(404)
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        subscribes = db_sess.query(Subscribes).filter(Subscribes.id == id, Subscribes.user == current_user).first()
        if subscribes:
            subscribes.name_serv = form.name_serv.data
            subscribes.price = form.price.data
            subscribes.payment_date = form.payment_date.data
            subscribes.link = form.link.data
            db_sess.commit()
            return redirect('/')
        else:
            abort(404)
    return render_template('add_sub.html',
                           title='Редактирование подписки',
                           form=form
                           )

@app.route('/subscribes_delete/<int:id>', methods=['GET', 'POST'])
@login_required
def subs_delete(id):
    db_sess = db_session.create_session()
    subscribes = db_sess.query(Subscribes).filter(Subscribes.id == id).first()
    if subscribes:
        db_sess.delete(subscribes)
        db_sess.commit()
    else:
        abort(404)
    return redirect('/')

def check_payment_dates():
    with app.app_context():
        db_sess = db_session.create_session()
        today = datetime.now().day

        # Находим подписки, у которых сегодня payment_date и is_paid=True
        subscriptions = db_sess.query(Subscribes).filter(
            Subscribes.payment_date == today,
            Subscribes.is_paid == True
        ).all()

        for sub in subscriptions:
            sub.is_paid = False
            db_sess.commit()
            print(f"Сброшен статус оплаты для подписки {sub.id}")

@app.route('/mark_paid/<int:subscribe_id>', methods=['POST'])
def mark_paid(subscribe_id):
    if not current_user.is_authenticated:
        return redirect('/login')

    db_sess = db_session.create_session()
    subscription = db_sess.query(Subscribes).filter(
        Subscribes.id == subscribe_id,
        Subscribes.user == current_user
    ).first()

    if not subscription:
        abort(404)

    subscription.is_paid = True
    db_sess.commit()

    flash('Подписка отмечена как оплаченная!', 'success')
    return redirect('/')

def run_flask():
    db_session.global_init("db/subscribes.db")
    # Запускаем проверку каждый день в 00:01
    scheduler_flask.add_job(
        check_payment_dates,
        'cron',
        hour=0,
        minute=1,
        id='daily_payment_check'
    )
    scheduler_flask.start()
    app.run()

async def main():
    # Запускаем Flask в отдельном потоке
    import threading
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Запускаем Telegram бота
    await telegram_bot()

if __name__ == '__main__':
    asyncio.run(main())