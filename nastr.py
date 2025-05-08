from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import random
import pandas as pd
import io
from sqlalchemy import func

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///calendar.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'
db = SQLAlchemy(app)

# Список вопросов дня
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


# Модели базы данных
class DayEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    mood = db.Column(db.String(20))
    note = db.Column(db.Text)
    answer = db.Column(db.Text)


class DailyQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    question = db.Column(db.String(255), nullable=False)





def get_daily_question(for_date=None):
    """Получает вопрос дня для указанной даты (по умолчанию - сегодня)"""
    target_date = for_date if for_date else date.today()
    question = DailyQuestion.query.filter_by(date=target_date).first()

    if not question:
        # Выбираем вопрос на основе дня года для одинакового вопроса у всех
        day_of_year = target_date.timetuple().tm_yday
        selected_question = DAILY_QUESTIONS[day_of_year % len(DAILY_QUESTIONS)]

        new_question = DailyQuestion(date=target_date, question=selected_question)
        db.session.add(new_question)
        db.session.commit()
        return selected_question

    return question.question


def get_mood_name(mood_code):
    moods = {
        'happy': '😊 Радостное',
        'neutral': '😐 Нейтральное',
        'sad': '😞 Грустное',
        'angry': '😠 Злое'
    }
    return moods.get(mood_code, 'Не указано')


# Создаем базу данных при первом запуске
with app.app_context():
    db.create_all()
    # Инициализируем вопрос на сегодня
    get_daily_question()


@app.route('/', methods=['GET', 'POST'])
def calendar():
    today = date.today()

    # Получаем месяц и год из параметров или используем текущие
    year = request.args.get('year', type=int, default=today.year)
    month = request.args.get('month', type=int, default=today.month)

    # Корректируем если вышли за пределы
    if month > 12:
        month = 1
        year += 1
    elif month < 1:
        month = 12
        year -= 1

    selected_date_str = request.args.get('date')
    selected_date = today
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today

    edit_mode = False

    if request.method == 'POST':
        if 'date' in request.form:
            selected_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        elif 'save' in request.form:
            selected_date = datetime.strptime(request.form['selected_date'], '%Y-%m-%d').date()
            mood = request.form.get('mood')
            note = request.form.get('note')
            answer = request.form.get('answer')

            # Проверяем что дата не в будущем
            if selected_date <= today:
                entry = DayEntry.query.filter_by(date=selected_date).first()
                if entry:
                    entry.mood = mood
                    entry.note = note
                    entry.answer = answer
                else:
                    entry = DayEntry(date=selected_date, mood=mood, note=note, answer=answer)
                    db.session.add(entry)
                db.session.commit()
        elif 'edit' in request.form:
            selected_date = datetime.strptime(request.form['selected_date'], '%Y-%m-%d').date()
            edit_mode = True

    # Получаем вопрос дня для выбранной даты
    daily_question = get_daily_question(selected_date)

    # Генерируем календарь
    first_day = date(year, month, 1)
    last_day = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
    days_in_month = (last_day - first_day).days

    calendar_matrix = []
    week = []

    # Заполняем пустые дни в начале месяца
    for i in range(first_day.weekday()):
        week.append(None)

    for day in range(1, days_in_month + 1):
        current_date = date(year, month, day)
        week.append(current_date)
        if len(week) == 7:
            calendar_matrix.append(week)
            week = []

    if week:
        calendar_matrix.append(week)

    # Предыдущий и следующий месяц
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    # Получаем запись для выбранной даты
    entry = DayEntry.query.filter_by(date=selected_date).first()

    return render_template('calendar.html',
                           today=today,
                           selected_date=selected_date,
                           calendar_matrix=calendar_matrix,
                           current_year=year,
                           prev_month=prev_month,
                           prev_year=prev_year,
                           next_month=next_month,
                           next_year=next_year,
                           entry=entry,
                           daily_question=daily_question,
                           edit_mode=edit_mode)


@app.route('/stats')
def stats():
    # Полная статистика по настроениям
    mood_stats = db.session.query(
        DayEntry.mood,
        func.count(DayEntry.mood).label('count')
    ).group_by(DayEntry.mood).all()

    # Преобразуем в удобный формат для Chart.js
    mood_data = {
        'happy': 0,
        'neutral': 0,
        'sad': 0,
        'angry': 0
    }

    for mood, count in mood_stats:
        if mood in mood_data:
            mood_data[mood] = count

    # Последние записи
    last_entries = DayEntry.query.order_by(DayEntry.date.desc()).limit(5).all()

    return render_template('stats.html',
                           mood_data=mood_data,
                           last_entries=last_entries)


@app.route('/settings')
def settings():
    return render_template('settings.html')


@app.route('/export/excel')
def export_excel():
    entries = DayEntry.query.order_by(DayEntry.date).all()

    data = {
        'Дата': [entry.date.strftime('%d.%m.%Y') for entry in entries],
        'Настроение': [get_mood_name(entry.mood) for entry in entries],
        'Запись': [entry.note for entry in entries],
        'Ответ на вопрос': [entry.answer for entry in entries]
    }

    df = pd.DataFrame(data)
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Дневник', index=False)
    writer.close()
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='дневник_настроения.xlsx'
    )


@app.route('/export/csv')
def export_csv():
    entries = DayEntry.query.order_by(DayEntry.date).all()

    data = {
        'Дата': [entry.date.strftime('%d.%m.%Y') for entry in entries],
        'Настроение': [get_mood_name(entry.mood) for entry in entries],
        'Запись': [entry.note for entry in entries],
        'Ответ на вопрос': [entry.answer for entry in entries]
    }

    df = pd.DataFrame(data)
    output = io.StringIO()
    df.to_csv(output, index=False, encoding='utf-8-sig', sep=';')
    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='дневник_настроения.csv'
    )


if __name__ == '__main__':
    app.run(debug=True)
