from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms import SubmitField
from wtforms.fields.numeric import IntegerField
from wtforms.validators import DataRequired


class SubscribesForm(FlaskForm):
    name_serv = StringField('Название сервиса', validators=[DataRequired()])
    price = IntegerField('Цена подписки', validators=[DataRequired()])
    payment_date = IntegerField('Дата ежемесячного платежа', validators=[DataRequired()])
    link = StringField('Ссылка на сервис', validators=[DataRequired()])
    submit = SubmitField('Применить')