from flask import Flask, render_template, redirect, request, abort, flash
from data import db_session
from data.subscribes import Subscribes
from data.users import User
from forms.add_sub import SubscribesForm
from forms.login import LoginForm
from forms.register import RegisterForm
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from flask_login import LoginManager, login_user, current_user, login_required, logout_user

app = Flask(__name__)
scheduler = BackgroundScheduler()
app.config['SECRET_KEY'] = 'yandexlyceum_secret_key'
login_manager = LoginManager()
login_manager.init_app(app)
#app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=365)


@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    return db_sess.query(User).get(user_id)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect("/")


def main():
    db_session.global_init("db/subscribes.db")
    app.run()


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
def add_news():
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

@app.route('/subscribes/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_news(id):
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
def news_delete(id):
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


# Запускаем проверку каждый день в 00:01
scheduler.add_job(
    check_payment_dates,
    'cron',
    hour=0,
    minute=1,
    id='daily_payment_check'
)
scheduler.start()


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


if __name__ == '__main__':
    main()