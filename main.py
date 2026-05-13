import telebot
import logging
import time
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template, redirect, request, abort, flash
from data import db_session
from data.subscribes import Subscribes
from data.users import User
from forms.add_sub import SubscribesForm
from forms.login import LoginForm
from forms.profile import EditForm
from forms.register import RegisterForm
from flask_login import LoginManager, login_user, current_user, login_required, logout_user
from forms.add_sud import SubscridesForm
import requests

# Конфигурация логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'yandexlyceum_secret_key'
login_manager = LoginManager()
login_manager.init_app(app)

# ============================================
# КОНФИГУРАЦИЯ БОТОВ
# ============================================

TELEGRAM_BOT_TOKEN = "7431447438:AAF2tyceUxIBqQq7kYOXNaj8sxFG8_q7yYw"

VK_GROUP_ID = "230244690"
VK_ACCESS_TOKEN = "vk1.a.8jy1F-dOC5IJ2pAZPhEAKz39kYKiao0p769F1L9tnEROp5NcBDq5LqQZPlNUprWLsU-aM9PxLL8twBs6UcFgNXCxuMYXydLuSBpxS2RN9C8n2gFYeWChCbuSBqx_QBCpCLZ1CL9Aa6Rrxn6PY9FuLJ_mKGXgYd9-hS1fxAKLA_iG9ZfdeEMNCJA9DZJFhfZveyvWHM60e40COXS5PWzi3g"

ACTIVE_BOT = "vk"

user_states = {}

if ACTIVE_BOT == "vk":
    import json

    def vk_request(method, params):
        url = f"https://api.vk.com/method/{method}"
        params['access_token'] = VK_ACCESS_TOKEN
        params['v'] = '5.131'
        response = requests.get(url, params=params)
        data = response.json()
        if 'error' in data:
            logger.error(f"VK API error: {data['error']}")
            return None
        return data.get('response')

    def send_vk_message(user_id, text):
        vk_request('messages.send', {
            'user_id': user_id,
            'message': text,
            'random_id': 0
        })

elif ACTIVE_BOT == "telegram":
    import telebot
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)


if ACTIVE_BOT == "telegram":
    import telebot
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

    @bot.message_handler(commands=['start'])
    def cmd_start(message):
        bot.send_message(
            message.chat.id,
            "Привет! Я бот для уведомлений о подписках.\n"
            "Для получения уведомлений необходимо авторизоваться.\n"
            "Введите ваш email:"
        )
        user_states[message.chat.id] = {'state': 'waiting_email'}


    @bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'waiting_email')
    def process_email(message):
        email = message.text.strip()
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.email == email).first()

        if not user:
            bot.send_message(message.chat.id, "Пользователь с таким email не найден. Попробуйте еще раз.")
            return

        user_states[message.chat.id] = {
            'state': 'waiting_password',
            'email': email,
            'user_id': user.id
        }
        bot.send_message(message.chat.id, "Введите ваш пароль:")


    @bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'waiting_password')
    def process_password(message):
        user_data = user_states[message.chat.id]
        email = user_data['email']
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.email == email).first()

        if not user.check_password(message.text):
            bot.send_message(message.chat.id, "Неверный пароль. Попробуйте еще раз.")
            return

        user.tg_id = message.chat.id
        db_sess.commit()
        bot.send_message(
            message.chat.id,
            f"✅ Авторизация успешна!\n"
            f"Теперь вы будете получать уведомления о ваших подписках.\n"
            f"Уведомления приходят за день до даты оплаты в 17:00."
        )

        del user_states[message.chat.id]


def vk_request(method, params):
    url = f"https://api.vk.com/method/{method}"
    params['access_token'] = VK_ACCESS_TOKEN
    params['v'] = '5.131'
    response = requests.get(url, params=params)
    data = response.json()
    if 'error' in data:
        logger.error(f"VK API error: {data['error']}")
        return None
    return data.get('response')


def send_vk_message(user_id, text):
    vk_request('messages.send', {
        'user_id': user_id,
        'message': text,
        'random_id': 0
    })


def vk_process_event(msg):
    user_id = msg.get('from_id')
    text = msg.get('text', '').strip()

    state = user_states.get(user_id, {})

    if text.lower() in ['начало', 'start', '/start']:
        send_vk_message(user_id,
            "Привет! Я бот для уведомлений о подписках.\n"
            "Для получения уведомлений необходимо авторизоваться.\n"
            "Введите ваш email:"
        )
        user_states[user_id] = {'state': 'waiting_email'}

    elif state.get('state') == 'waiting_email':
        email = text.strip()
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.email == email).first()
        if not user:
            send_vk_message(user_id, "Пользователь с таким email не найден. Попробуйте еще раз.")
            return

        user_states[user_id] = {
            'state': 'waiting_password',
            'email': email,
            'user_id': user.id
        }
        send_vk_message(user_id, "Введите ваш пароль:")

    elif state.get('state') == 'waiting_password':
        user_data = user_states[user_id]
        email = user_data['email']
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.email == email).first()

        if not user.check_password(text):
            send_vk_message(user_id, "Неверный пароль. Попробуйте еще раз.")
            return

        user.vk_id = user_id
        db_sess.commit()
        send_vk_message(user_id,
            f"✅ Авторизация успешна!\n"
            f"Теперь вы будете получать уведомления о ваших подписках.\n"
            f"Уведомления приходят за день до даты оплаты в 17:00."
        )

        del user_states[user_id]


def vk_longpoll():
    while True:
        try:
            result = vk_request('groups.getLongPollServer', {'group_id': VK_GROUP_ID})
            if not result:
                time.sleep(5)
                continue

            ts = result['ts']
            key = result['key']
            server = result['server'].replace('https://', '').replace('http://', '')

            while True:
                try:
                    params = {'act': 'a_check', 'key': key, 'ts': ts, 'wait': 25}
                    lp_url = f"https://{server}"
                    response = requests.post(lp_url, data=params, timeout=30)
                    lp_data = response.json()

                    if 'failed' in lp_data:
                        logger.warning(f"VK LongPoll failed: {lp_data}")
                        break

                    ts = lp_data.get('ts')
                    updates = lp_data.get('updates', [])
                    for update in updates:
                        if update.get('type') == 'message_new':
                            msg_obj = update.get('object', {}).get('message', {})
                            msg = {
                                'from_id': msg_obj.get('from_id'),
                                'text': msg_obj.get('text', '')
                            }
                            logger.info(f"VK message received from {msg['from_id']}: {msg['text']}")
                            vk_process_event(msg)

                except Exception as e:
                    logger.error(f"VK loop error: {e}")
                    break

        except Exception as e:
            logger.error(f"VK LongPoll error: {e}")
            time.sleep(5)


def send_daily_notifications():
    logger.info("Проверка подписок для уведомлений...")

    db_sess = db_session.create_session()
    tomorrow_day = (datetime.now() + timedelta(days=1)).day

    if ACTIVE_BOT == "vk":
        subscriptions = db_sess.query(Subscribes).join(User).filter(
            Subscribes.payment_date == tomorrow_day,
            User.vk_id.isnot(None)
        ).all()
    else:
        subscriptions = db_sess.query(Subscribes).join(User).filter(
            Subscribes.payment_date == tomorrow_day,
            User.tg_id.isnot(None)
        ).all()

    if not subscriptions:
        logger.info("Нет подписок для уведомления сегодня")
        return

    current_month = datetime.now().strftime('%m')
    current_year = datetime.now().strftime('%Y')

    for sub in subscriptions:
        user = sub.user
        user_id = user.vk_id if ACTIVE_BOT == "vk" else user.tg_id

        try:
            payment_date = datetime.strptime(
                f"{current_year}-{current_month}-{sub.payment_date}",
                "%Y-%m-%d"
            ).strftime('%d.%m.%Y')
        except ValueError:
            payment_date = f"{sub.payment_date}-е число следующего месяца"

        message_text = (
            "🔔 Напоминание о подписке!\n\n"
            f"💳 Сервис: {sub.name_serv}\n"
            f"💰 Сумма: {sub.price} рублей\n"
            f"📅 Дата оплаты: {payment_date}\n"
            f"🔗 Ссылка: {sub.link}\n\n"
            f"Оплата требуется завтра!"
        )

        try:
            if ACTIVE_BOT == "vk":
                vk_request('messages.send', {
                    'user_id': user_id,
                    'message': message_text,
                    'random_id': 0
                })
                logger.info(f"VK уведомление отправлено для user_id {user_id}")
            else:
                bot.send_message(
                    chat_id=user_id,
                    text=message_text
                )
                logger.info(f"Telegram уведомление отправлено для tg_id {user_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления для user_id {user_id}: {e}")


# Функции для Flask приложения
# def auth(username, password):
#     data = {
#         "username": username,
#         "password": password
#     }
#     url_auth = 'https://elfin-circular-octagon.glitch.me/login'
#     url_subscribe = 'https://elfin-circular-octagon.glitch.me/subscription'
#     session = requests.Session()
#     session.post(url_auth, data=data)
#     response = session.get(url_subscribe).text
#     soup = BeautifulSoup(response, 'lxml')
#     block_main = soup.find('div', class_='container content')
#     block_data_1 = block_main.find('div', class_='alert alert-info mb-4')
#     block_data_2 = block_data_1.find_all('p')
#     block_costs_1 = block_main.find('div', class_='row justify-content-center')
#     block_costs_2 = block_costs_1.find('div', class_='card-body text-center')
#     block_costs_3 = block_costs_2.find('h4', class_='text-primary')
#     return [int(str(block_data_2[0]).split()[-1].split(".")[0]), int(str(block_costs_3)[25: -11])]


@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    return db_sess.query(User).get(user_id)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect("/")


@app.route("/profile", methods=['GET', 'POST'])
@login_required
def profile():
    form = EditForm()
    if request.method == "GET":
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.id == current_user.id).first()
        if user:
            form.name.data = user.name
            form.surname.data = user.surname
            form.email.data = user.email
            form.about.data = user.about
            # Пароль не заполняем для безопасности
        else:
            abort(404)

    if form.validate_on_submit():
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.id == current_user.id).first()
        if user:
            user.name = form.name.data
            user.surname = form.surname.data
            user.email = form.email.data
            if form.password.data:  # Обновляем пароль только если он был изменен
                user.set_password(form.password.data)
            user.about = form.about.data
            db_sess.commit()
            flash('Изменения сохранены', 'success')
            return redirect('/')
        else:
            abort(404)
    return render_template('edit_profile.html', title='Редактирование профиля', form=form)
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


@app.route('/subscribes', methods=['GET', 'POST'])
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
            # data_diary = auth(form.login.data, form.password.data)

            subscribes = Subscribes(
                name_serv="Harmony Diary",
                price=form.price.data,
                payment_date=form.day.data,
                link=form.link.data,
                user_id=current_user.id
            )

            db_sess.add(subscribes)

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


def run_all():
    # Инициализация базы данных
    db_session.global_init("db/subscribes.db")

    # Настройка планировщика
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        send_daily_notifications,
        'cron',
        hour=17,
        minute=00,
        id='daily_notifications'
    )
    scheduler.add_job(
        check_payment_dates,
        'cron',
        hour=0,
        minute=1,
        id='daily_payment_check'
    )
    scheduler.start()

    try:
        logger.info("Starting applications...")

        from threading import Thread
        flask_thread = Thread(target=lambda: app.run(debug=False))
        flask_thread.start()

        if ACTIVE_BOT == "vk":
            logger.info("Starting VK bot...")
            vk_longpoll()
        else:
            logger.info("Starting Telegram bot...")
            bot.infinity_polling()

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        scheduler.shutdown()


if __name__ == '__main__':
    run_all()
