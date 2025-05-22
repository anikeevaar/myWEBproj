from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, TextAreaField, SubmitField, EmailField
from wtforms.validators import DataRequired


class EditForm(FlaskForm):
    name = StringField('Имя пользователя', validators=[DataRequired()])
    surname = StringField('Фамилия пользователя', validators=[DataRequired()])
    email = EmailField('Почта', validators=[DataRequired()])
    about = TextAreaField("Немного о себе")
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Подтвердить')