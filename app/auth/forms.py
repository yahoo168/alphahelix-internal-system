# app/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectMultipleField
from wtforms.validators import DataRequired, Length, Email, EqualTo

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    roles = SelectMultipleField('Roles', choices=[
        ('general_manager', 'General Manager'),
        ('investment_manager', 'Investment Manager'),
        ('investment_consultant', 'Investment Consultant'),
        ('investment_researcher', 'Investment Researcher'),
        ('quant_researcher', 'Quant Researcher'),
        ('administration_assistant', 'Administration Assistant'),
        ('investment_intern', 'Investment Intern'),
        ('remote_investment_intern', 'Remote Investment Intern'),
        ('tw_data_subscriber', 'TW Data Subscriber'),
        ('admin', 'Admin')
    ], validators=[DataRequired()])
    submit = SubmitField('Sign Up')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')