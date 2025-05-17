# Импорт необходимых библиотек
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import random
import re
import io
import pandas as pd
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

# Инициализация Flask-приложения
app = Flask(__name__)
# Конфигурация базы данных (SQLite)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mood_diary.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'
db = SQLAlchemy(app)  # Инициализация SQLAlchemy


# МОДЕЛИ БАЗЫ ДАННЫХ

class User(db.Model):
    """Модель пользователя"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)  # Логин
    password = db.Column(db.String(120), nullable=False)  # Пароль
    subscription = db.relationship('Subscription', backref='user', uselist=False,
                                   cascade='all, delete-orphan')  # Подписка (1 к 1)
    entries = db.relationship('DayEntry', backref='author', lazy=True)  # Записи пользователя


class DayEntry(db.Model):
    """Модель записи в дневнике"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=False, nullable=False)  # Дата записи
    mood = db.Column(db.String(20))  # Настроение (happy, neutral, sad, angry)
    note = db.Column(db.Text)  # Текстовая запись
    answer = db.Column(db.Text)  # Ответ на ежедневный вопрос
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Ссылка на пользователя


class DailyQuestion(db.Model):
    """Модель ежедневного вопроса"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)  # Дата вопроса
    question = db.Column(db.String(255), nullable=False)  # Текст вопроса


class Subscription(db.Model):
    """Модель подписки пользователя"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)  # Ссылка на пользователя
    start_date = db.Column(db.Date)  # Дата начала подписки
    end_date = db.Column(db.Date)  # Дата окончания подписки
    auto_renew = db.Column(db.Boolean, default=True)  # Автопродление


### КОНСТАНТЫ ###

# Список ежедневных вопросов
DAILY_QUESTIONS = [
    "Что хорошего сегодня произошло?",
    "Что нового вы узнали сегодня?",
    "Какая ваша главная цель на сегодня?",
    "За что вы благодарны сегодня?",
    "Что вы сделали сегодня для своего здоровья?",
    "Какой момент дня был самым запоминающимся?",
    "Что вы могли бы сделать сегодня лучше?",
    "Кому вы сегодня помогли?",
    "Что вдохновило вас сегодня?"
]

# Названия месяцев для отображения
MONTH_NAMES = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}


# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ

def validate_password(password):
    """Валидация пароля по сложности"""
    if len(password) < 8:
        return "Пароль должен содержать минимум 8 символов"
    if not re.search(r"[A-ZА-Я]", password):
        return "Пароль должен содержать хотя бы одну заглавную букву"
    if not re.search(r"[a-zа-я]", password):
        return "Пароль должен содержать хотя бы одну строчную букву"
    if not re.search(r"\d", password):
        return "Пароль должен содержать хотя бы одну цифру"
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return "Пароль должен содержать хотя бы один специальный символ"
    return None


def get_daily_question(for_date=None):
    """Получение ежедневного вопроса (создает новый если не существует)"""
    target_date = for_date if for_date else date.today()
    question = DailyQuestion.query.filter_by(date=target_date).first()

    if not question:
        # Если вопроса нет - выбираем из списка по дате
        day_of_year = target_date.timetuple().tm_yday
        selected_question = DAILY_QUESTIONS[day_of_year % len(DAILY_QUESTIONS)]
        new_question = DailyQuestion(date=target_date, question=selected_question)
        db.session.add(new_question)
        db.session.commit()
        return selected_question
    return question.question


def get_mood_name(mood_code):
    """Преобразование кода настроения в читаемый текст"""
    moods = {
        'happy': '😊 Радостное',
        'neutral': '😐 Нейтральное',
        'sad': '😞 Грустное',
        'angry': '😠 Злое'
    }
    return moods.get(mood_code, 'Не указано')


def check_subscription(user_id):
    """Проверка активной подписки пользователя"""
    subscription = Subscription.query.filter_by(user_id=user_id).first()
    return subscription and subscription.end_date >= date.today()


# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
with app.app_context():
    db.create_all()  # Создание таблиц если их нет
    get_daily_question()  # Инициализация первого вопроса


## Аутентификация ##

@app.route('/')
def login_page():
    """Главная страница (вход)"""
    if 'user_id' in session:
        return redirect(url_for('calendar'))
    error = request.args.get('error')  # Получение сообщения об ошибке
    return render_template('login.html', error=error)


@app.route('/login', methods=['POST'])
def login():
    """Обработка входа"""
    username = request.form['username']
    password = request.form['password']

    if not username or not password:
        return redirect(url_for('login_page', error='Пожалуйста, заполните все поля'))

    # Проверка пользователя
    user = User.query.filter_by(username=username, password=password).first()
    if user:
        session['user_id'] = user.id  # Сохраняем в сессии
        return redirect(url_for('calendar'))
    else:
        return redirect(url_for('login_page', error='Неверные данные для входа'))


@app.route('/logout')
def logout():
    """Выход из системы"""
    session.pop('user_id', None)
    return redirect(url_for('login_page'))


@app.route('/register')
def register_page():
    """Страница регистрации"""
    error = request.args.get('error')
    return render_template('register.html', error=error)


@app.route('/register', methods=['POST'])
def register():
    """Обработка регистрации"""
    username = request.form['username']
    password = request.form['password']
    confirm_password = request.form.get('confirm_password', '')

    # Валидация данных
    if not username or not password or not confirm_password:
        return redirect(url_for('register_page', error='Пожалуйста, заполните все поля'))

    if password != confirm_password:
        return redirect(url_for('register_page', error='Пароли не совпадают'))

    password_error = validate_password(password)
    if password_error:
        return redirect(url_for('register_page', error=password_error))

    # Проверка уникальности имени
    if User.query.filter_by(username=username).first():
        return redirect(url_for('register_page', error='Пользователь с таким именем уже существует'))

    try:
        # Создание нового пользователя
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login_page', error='Регистрация прошла успешно! Теперь вы можете войти'))
    except Exception as e:
        db.session.rollback()
        return redirect(url_for('register_page', error='Произошла ошибка при регистрации'))


## Календарь и записи ##

@app.route('/calendar', methods=['GET', 'POST'])
def calendar():
    """Главный календарь с записями"""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_id = session['user_id']
    today = date.today()

    # Получение параметров года и месяца
    year = request.args.get('year', type=int, default=today.year)
    month = request.args.get('month', type=int, default=today.month)

    # Корректировка месяца/года при переходе через границы
    if month > 12:
        month = 1
        year += 1
    elif month < 1:
        month = 12
        year -= 1

    # Обработка выбранной даты
    selected_date_str = request.args.get('date')
    selected_date = today
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today

    edit_mode = False

    # Обработка POST-запросов (сохранение/редактирование)
    if request.method == 'POST':
        if 'date' in request.form:
            selected_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()

        elif 'save' in request.form:
            # Сохранение записи
            selected_date = datetime.strptime(request.form['selected_date'], '%Y-%m-%d').date()
            mood = request.form.get('mood')
            note = request.form.get('note')
            answer = request.form.get('answer')

            if selected_date <= today:  # Можно сохранять только за прошедшие даты
                try:
                    entry = DayEntry.query.filter_by(date=selected_date, user_id=user_id).first()
                    if entry:  # Обновление существующей записи
                        entry.mood = mood
                        entry.note = note
                        entry.answer = answer
                        flash('Запись обновлена', 'success')
                    else:  # Создание новой записи
                        new_entry = DayEntry(
                            date=selected_date,
                            mood=mood,
                            note=note,
                            answer=answer,
                            user_id=user_id
                        )
                        db.session.add(new_entry)
                        flash('Запись создана', 'success')
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash('Ошибка: невозможно сохранить запись', 'danger')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Ошибка: {str(e)}', 'danger')

        elif 'edit' in request.form:
            # Режим редактирования
            selected_date = datetime.strptime(request.form['selected_date'], '%Y-%m-%d').date()
            edit_mode = True

    # Генерация календаря
    first_day = date(year, month, 1)
    last_day = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
    days_in_month = (last_day - first_day).days

    # Создание матрицы календаря
    calendar_matrix = []
    week = []

    # Пустые дни в начале месяца
    for i in range(first_day.weekday()):
        week.append(None)

    # Заполнение дней месяца
    for day in range(1, days_in_month + 1):
        current_date = date(year, month, day)
        week.append(current_date)
        if len(week) == 7:  # Завершение недели
            calendar_matrix.append(week)
            week = []

    if week:  # Добавление последней недели
        calendar_matrix.append(week)

    # Получение записей за месяц
    month_entries = DayEntry.query.filter(
        DayEntry.user_id == user_id,
        DayEntry.date >= first_day,
        DayEntry.date < last_day
    ).all()

    # Словарь для быстрого доступа к записям по дате
    entries_dict = {entry.date: entry for entry in month_entries}

    # Навигация по месяцам
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    # Получение записи и вопроса для выбранной даты
    entry = entries_dict.get(selected_date)
    daily_question = get_daily_question(selected_date)

    return render_template('calendar.html',
                           today=today,
                           selected_date=selected_date,
                           calendar_matrix=calendar_matrix,
                           current_month=MONTH_NAMES[month],
                           current_year=year,
                           prev_month=prev_month,
                           prev_year=prev_year,
                           next_month=next_month,
                           next_year=next_year,
                           entry=entry,
                           daily_question=daily_question,
                           edit_mode=edit_mode,
                           MONTH_NAMES=MONTH_NAMES,
                           entries_dict=entries_dict)


## Статистика и экспорт ##

@app.route('/stats')
def stats():
    """Страница статистики"""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_id = session['user_id']

    # Статистика по настроениям
    mood_stats = db.session.query(
        DayEntry.mood,
        func.count(DayEntry.mood).label('count')
    ).filter_by(user_id=user_id).group_by(DayEntry.mood).all()

    # Инициализация данных
    mood_data = {
        'happy': 0,
        'neutral': 0,
        'sad': 0,
        'angry': 0
    }

    # Заполнение статистики
    for mood, count in mood_stats:
        if mood in mood_data:
            mood_data[mood] = count

    # Последние записи
    last_entries = DayEntry.query.filter_by(user_id=user_id).order_by(DayEntry.date.desc()).limit(5).all()

    return render_template('stats.html',
                           mood_data=mood_data,
                           last_entries=last_entries)


@app.route('/diary')
def diary():
    """Страница со всеми записями (дневник)"""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_id = session['user_id']
    entries = DayEntry.query.filter_by(user_id=user_id).order_by(DayEntry.date.desc()).all()

    return render_template('diary.html', entries=entries)


@app.route('/export/csv')
def export_csv():
    """Экспорт данных в CSV"""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_id = session['user_id']

    # Проверка подписки
    if not check_subscription(user_id):
        flash('Для экспорта данных требуется активная подписка', 'danger')
        return redirect(url_for('subscription'))

    try:
        # Получение всех записей
        entries = DayEntry.query.filter_by(user_id=user_id).order_by(DayEntry.date).all()

        if not entries:
            flash('Нет данных для экспорта', 'warning')
            return redirect(url_for('diary'))

        # Подготовка данных
        data = {
            'Дата': [entry.date.strftime('%d.%m.%Y') for entry in entries],
            'Настроение': [get_mood_name(entry.mood) for entry in entries],
            'Запись': [entry.note if entry.note else '' for entry in entries],
            'Ответ на вопрос': [entry.answer if entry.answer else '' for entry in entries]
        }

        # Создание DataFrame и CSV
        df = pd.DataFrame(data)
        output = io.StringIO()
        df.to_csv(output, index=False, encoding='utf-8-sig', sep=';')
        output.seek(0)

        # Формирование имени файла
        today_str = date.today().strftime('%Y-%m-%d')
        filename = f'дневник_настроения_{today_str}.csv'

        # Отправка файла
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        app.logger.error(f'Ошибка при экспорте CSV: {str(e)}')
        flash('Произошла ошибка при создании файла экспорта', 'danger')
        return redirect(url_for('diary'))


## Подписка ##

@app.route('/subscription')
def subscription():
    """Страница подписки"""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_id = session['user_id']
    current_subscription = Subscription.query.filter_by(user_id=user_id).first()

    return render_template('subscription.html',
                           current_subscription=current_subscription)


@app.route('/subscribe', methods=['POST'])
def subscribe():
    """Оформление подписки"""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_id = session['user_id']
    today = date.today()
    end_date = today + timedelta(days=30)  # Подписка на 30 дней

    # Проверка существующей подписки
    subscription = Subscription.query.filter_by(user_id=user_id).first()

    if subscription:
        # Обновление существующей
        subscription.start_date = today
        subscription.end_date = end_date
        subscription.auto_renew = True
    else:
        # Создание новой
        subscription = Subscription(
            user_id=user_id,
            start_date=today,
            end_date=end_date,
            auto_renew=True
        )
        db.session.add(subscription)

    db.session.commit()
    return redirect(url_for('subscription'))


@app.route('/cancel_subscription', methods=['POST'])
def cancel_subscription():
    """Отмена автопродления подписки"""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_id = session['user_id']
    subscription = Subscription.query.filter_by(user_id=user_id).first()

    if subscription:
        subscription.auto_renew = False
        db.session.commit()

    return redirect(url_for('subscription'))


## Дополнительные страницы ##

@app.route('/settings')
def settings():
    """Страница настроек"""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('settings.html')


@app.route('/menu')
def menu():
    """Главное меню с приветствием"""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('login_page'))

    # Персональное приветствие по времени суток
    current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        greeting = f"{user.username}, доброе утро!"
    elif 12 <= current_hour < 18:
        greeting = f"{user.username}, добрый день!"
    elif 18 <= current_hour < 23:
        greeting = f"{user.username}, добрый вечер!"
    else:
        greeting = f"{user.username}, доброй ночи!"

    # Сообщение от разработчиков
    dev_message = """
    Дорогому пользователю от разработчиков:

    Спасибо, что используете нашем сайтом!
    Мы вложили в него много сил и души. 
    Надеемся, что оно поможет вам лучше понимать 
    свои эмоции и улучшить качество жизни.

    С любовью, команда разработчиков😘😘😘.
    """

    return render_template('menu.html',
                           greeting=greeting,
                           dev_message=dev_message)


# Запуск приложения
if __name__ == '__main__':
    app.run(debug=True)
