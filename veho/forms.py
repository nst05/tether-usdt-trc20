from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SelectField, FloatField, DateField,
    SubmitField
)
from wtforms.validators import DataRequired, Optional, Email, Length


CLIENT_TYPE_CHOICES = [
    ('individual', 'Частное лицо'),
    ('business', 'Бизнес'),
]

COURIER_STATUS_CHOICES = [
    ('active', 'Активен'),
    ('on_delivery', 'На доставке'),
    ('inactive', 'Не работает'),
]

VEHICLE_CHOICES = [
    ('car', 'Автомобиль'),
    ('van', 'Фургон'),
    ('scooter', 'Скутер'),
    ('bike', 'Велосипед'),
    ('foot', 'Пешком'),
]

SERVICE_CHOICES = [
    ('standard', 'Стандарт'),
    ('express', 'Экспресс'),
    ('same_day', 'В день заказа'),
]

SHIPMENT_STATUS_CHOICES = [
    ('created', 'Создано'),
    ('picked_up', 'Забрано'),
    ('in_transit', 'В пути'),
    ('out_for_delivery', 'На доставке'),
    ('delivered', 'Доставлено'),
    ('returned', 'Возврат'),
    ('cancelled', 'Отменено'),
]


class ClientForm(FlaskForm):
    name = StringField('Название / ФИО', validators=[DataRequired(), Length(max=200)])
    client_type = SelectField('Тип', choices=CLIENT_TYPE_CHOICES, default='individual')
    contact_person = StringField('Контактное лицо', validators=[Optional(), Length(max=200)])
    phone = StringField('Телефон', validators=[Optional(), Length(max=30)])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=150)])
    address = TextAreaField('Адрес', validators=[Optional()])
    notes = TextAreaField('Примечания', validators=[Optional()])
    submit = SubmitField('Сохранить')


class CourierForm(FlaskForm):
    first_name = StringField('Имя', validators=[DataRequired(), Length(max=100)])
    last_name = StringField('Фамилия', validators=[DataRequired(), Length(max=100)])
    phone = StringField('Телефон', validators=[Optional(), Length(max=30)])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=150)])
    status = SelectField('Статус', choices=COURIER_STATUS_CHOICES, default='active')
    vehicle_type = SelectField('Транспорт', choices=VEHICLE_CHOICES, default='car')
    vehicle_number = StringField('Гос. номер', validators=[Optional(), Length(max=30)])
    zone = StringField('Зона обслуживания', validators=[Optional(), Length(max=120)])
    notes = TextAreaField('Примечания', validators=[Optional()])
    submit = SubmitField('Сохранить')


class ShipmentForm(FlaskForm):
    # Отправитель
    client_id = SelectField('Клиент (отправитель)', coerce=int, validators=[Optional()])
    sender_name = StringField('Имя отправителя', validators=[DataRequired(), Length(max=200)])
    sender_phone = StringField('Телефон отправителя', validators=[Optional(), Length(max=30)])
    sender_address = TextAreaField('Адрес отправителя', validators=[DataRequired()])

    # Получатель
    recipient_name = StringField('Имя получателя', validators=[DataRequired(), Length(max=200)])
    recipient_phone = StringField('Телефон получателя', validators=[Optional(), Length(max=30)])
    recipient_address = TextAreaField('Адрес получателя', validators=[DataRequired()])

    # Груз
    description = StringField('Описание груза', validators=[Optional(), Length(max=300)])
    weight_kg = FloatField('Вес, кг', validators=[Optional()], default=0.0)
    dimensions = StringField('Габариты (ДxШxВ)', validators=[Optional(), Length(max=60)])
    service_type = SelectField('Тип услуги', choices=SERVICE_CHOICES, default='standard')

    price = FloatField('Стоимость доставки, ₽', validators=[Optional()], default=0.0)
    cod_amount = FloatField('Наложенный платёж, ₽', validators=[Optional()], default=0.0)

    courier_id = SelectField('Курьер', coerce=int, validators=[Optional()])
    status = SelectField('Статус', choices=SHIPMENT_STATUS_CHOICES, default='created')
    scheduled_date = DateField('Плановая дата', validators=[Optional()])
    notes = TextAreaField('Примечания', validators=[Optional()])
    submit = SubmitField('Сохранить')
