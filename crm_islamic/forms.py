from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, DateField, FloatField, IntegerField,
    TextAreaField, BooleanField, HiddenField, SubmitField
)
from wtforms.validators import (
    DataRequired, Optional, Email, Length, NumberRange, ValidationError
)


EMPLOYMENT_CHOICES = [
    ('', '--- Выберите ---'),
    ('employed', 'Наёмный работник'),
    ('self_employed', 'Самозанятый'),
    ('business_owner', 'Владелец бизнеса'),
    ('unemployed', 'Безработный'),
]

MARITAL_CHOICES = [
    ('', '--- Выберите ---'),
    ('single', 'Холост/Не замужем'),
    ('married', 'Женат/Замужем'),
    ('divorced', 'Разведён/Разведена'),
    ('widowed', 'Вдовец/Вдова'),
]

EDUCATION_CHOICES = [
    ('', '--- Выберите ---'),
    ('school', 'Среднее'),
    ('college', 'Среднее специальное'),
    ('university', 'Высшее'),
    ('postgraduate', 'Аспирантура/Учёная степень'),
]

CREDIT_HISTORY_CHOICES = [
    ('none', 'Нет истории'),
    ('good', 'Хорошая'),
    ('satisfactory', 'Удовлетворительная'),
    ('bad', 'Плохая'),
]

STATUS_CHOICES = [
    ('active', 'Активный'),
    ('inactive', 'Неактивный'),
    ('blacklisted', 'Чёрный список'),
]

GENDER_CHOICES = [
    ('', '--- Выберите ---'),
    ('male', 'Мужской'),
    ('female', 'Женский'),
]

ITEM_CATEGORY_CHOICES = [
    ('', '--- Выберите ---'),
    ('appliances', 'Бытовая техника'),
    ('electronics', 'Электроника'),
    ('furniture', 'Мебель'),
    ('auto', 'Автомобиль'),
    ('real_estate', 'Недвижимость'),
    ('education', 'Образование'),
    ('medical', 'Медицина'),
    ('other', 'Другое'),
]

ITEM_CONDITION_CHOICES = [
    ('new', 'Новый'),
    ('used', 'Б/У'),
]

CONTRACT_STATUS_CHOICES = [
    ('draft', 'Черновик'),
    ('active', 'Активный'),
    ('overdue', 'Просрочен'),
    ('closed', 'Закрыт'),
    ('cancelled', 'Отменён'),
]

PAYMENT_METHOD_CHOICES = [
    ('cash', 'Наличные'),
    ('bank_transfer', 'Банковский перевод'),
    ('card', 'Карта'),
    ('online', 'Онлайн'),
]

RELATIONSHIP_CHOICES = [
    ('', '--- Выберите ---'),
    ('parent', 'Родитель'),
    ('spouse', 'Супруг/Супруга'),
    ('sibling', 'Брат/Сестра'),
    ('friend', 'Друг'),
    ('colleague', 'Коллега'),
    ('other', 'Другое'),
]

GUARANTOR_TYPE_CHOICES = [
    ('personal', 'Личное поручительство'),
    ('property', 'Имущественный залог'),
]


class ClientForm(FlaskForm):
    # Status
    status = SelectField('Статус', choices=STATUS_CHOICES, default='active')

    # Personal
    last_name = StringField('Фамилия', validators=[DataRequired(message='Обязательное поле'), Length(max=100)])
    first_name = StringField('Имя', validators=[DataRequired(message='Обязательное поле'), Length(max=100)])
    middle_name = StringField('Отчество', validators=[Optional(), Length(max=100)])
    birth_date = DateField('Дата рождения', validators=[Optional()])
    birth_place = StringField('Место рождения', validators=[Optional(), Length(max=200)])
    nationality = StringField('Национальность', validators=[Optional(), Length(max=100)])
    citizenship = StringField('Гражданство', validators=[Optional(), Length(max=100)])
    gender = SelectField('Пол', choices=GENDER_CHOICES, validators=[Optional()])

    # Passport
    passport_series = StringField('Серия паспорта', validators=[Optional(), Length(max=10)])
    passport_number = StringField('Номер паспорта', validators=[Optional(), Length(max=20)])
    passport_issued_by = StringField('Кем выдан', validators=[Optional(), Length(max=300)])
    passport_issued_date = DateField('Дата выдачи', validators=[Optional()])
    passport_expires_date = DateField('Срок действия', validators=[Optional()])

    # Tax
    inn = StringField('ИНН', validators=[Optional(), Length(max=20)])
    snils = StringField('СНИЛС', validators=[Optional(), Length(max=20)])

    # Contacts
    phone = StringField('Телефон', validators=[Optional(), Length(max=30)])
    phone2 = StringField('Телефон 2', validators=[Optional(), Length(max=30)])
    email = StringField('Email', validators=[Optional(), Email(message='Некорректный email'), Length(max=150)])

    # Addresses
    address_registration = TextAreaField('Адрес прописки', validators=[Optional()])
    address_actual = TextAreaField('Фактический адрес', validators=[Optional()])

    # Employment
    employer_name = StringField('Работодатель', validators=[Optional(), Length(max=200)])
    employer_address = StringField('Адрес работодателя', validators=[Optional(), Length(max=300)])
    employer_phone = StringField('Телефон работодателя', validators=[Optional(), Length(max=30)])
    position = StringField('Должность', validators=[Optional(), Length(max=150)])
    employment_type = SelectField('Тип занятости', choices=EMPLOYMENT_CHOICES, validators=[Optional()])
    work_experience_months = IntegerField('Стаж (мес.)', validators=[Optional(), NumberRange(min=0)])
    monthly_income = FloatField('Ежемесячный доход', validators=[Optional(), NumberRange(min=0)], default=0.0)
    additional_income = FloatField('Доп. доход', validators=[Optional(), NumberRange(min=0)], default=0.0)
    income_confirmed = BooleanField('Доход подтверждён')

    # Family
    marital_status = SelectField('Семейное положение', choices=MARITAL_CHOICES, validators=[Optional()])
    children_count = IntegerField('Кол-во детей', validators=[Optional(), NumberRange(min=0)], default=0)
    dependents_count = IntegerField('Кол-во иждивенцев', validators=[Optional(), NumberRange(min=0)], default=0)
    education = SelectField('Образование', choices=EDUCATION_CHOICES, validators=[Optional()])

    # Assets
    own_property = BooleanField('Есть собственность')
    own_car = BooleanField('Есть автомобиль')

    # Credit
    credit_history_status = SelectField('Кредитная история', choices=CREDIT_HISTORY_CHOICES, default='none')
    credit_score = IntegerField('Кредитный балл (0-999)', validators=[Optional(), NumberRange(min=0, max=999)], default=0)

    # Blacklist
    blacklisted = BooleanField('В чёрном списке')
    blacklist_reason = TextAreaField('Причина блокировки', validators=[Optional()])

    # Other
    notes = TextAreaField('Примечания', validators=[Optional()])

    submit = SubmitField('Сохранить')


class GuarantorForm(FlaskForm):
    contract_id = HiddenField('contract_id', validators=[Optional()])
    client_id = HiddenField('client_id', validators=[Optional()])

    # Personal
    last_name = StringField('Фамилия', validators=[DataRequired(message='Обязательное поле'), Length(max=100)])
    first_name = StringField('Имя', validators=[DataRequired(message='Обязательное поле'), Length(max=100)])
    middle_name = StringField('Отчество', validators=[Optional(), Length(max=100)])
    birth_date = DateField('Дата рождения', validators=[Optional()])
    gender = SelectField('Пол', choices=[('', '---'), ('male', 'Мужской'), ('female', 'Женский')], validators=[Optional()])
    phone = StringField('Телефон', validators=[Optional(), Length(max=30)])
    phone2 = StringField('Телефон 2', validators=[Optional(), Length(max=30)])
    email = StringField('Email', validators=[Optional(), Email(message='Некорректный email'), Length(max=150)])

    # Passport
    passport_series = StringField('Серия паспорта', validators=[Optional(), Length(max=10)])
    passport_number = StringField('Номер паспорта', validators=[Optional(), Length(max=20)])
    passport_issued_by = StringField('Кем выдан', validators=[Optional(), Length(max=300)])
    passport_issued_date = DateField('Дата выдачи', validators=[Optional()])

    # IDs
    inn = StringField('ИНН', validators=[Optional(), Length(max=20)])
    snils = StringField('СНИЛС', validators=[Optional(), Length(max=20)])

    # Addresses
    address_registration = TextAreaField('Адрес прописки', validators=[Optional()])
    address_actual = TextAreaField('Фактический адрес', validators=[Optional()])

    # Employment
    employer_name = StringField('Работодатель', validators=[Optional(), Length(max=200)])
    employer_phone = StringField('Тел. работодателя', validators=[Optional(), Length(max=30)])
    position = StringField('Должность', validators=[Optional(), Length(max=150)])
    employment_type = SelectField('Тип занятости', choices=EMPLOYMENT_CHOICES, validators=[Optional()])
    work_experience_months = IntegerField('Стаж (мес.)', validators=[Optional(), NumberRange(min=0)])
    monthly_income = FloatField('Ежемесячный доход', validators=[Optional(), NumberRange(min=0)], default=0.0)

    # Guarantor specific
    relationship = SelectField('Отношение к клиенту', choices=RELATIONSHIP_CHOICES, validators=[Optional()])
    guarantor_type = SelectField('Тип поручительства', choices=GUARANTOR_TYPE_CHOICES, default='personal')
    property_description = TextAreaField('Описание имущества', validators=[Optional()])
    notes = TextAreaField('Примечания', validators=[Optional()])

    submit = SubmitField('Сохранить поручителя')


class ContractForm(FlaskForm):
    client_id = HiddenField('client_id', validators=[DataRequired(message='Выберите клиента')])

    # Contract number (auto-generated, but editable)
    contract_number = StringField(
        'Номер договора',
        validators=[DataRequired(message='Обязательное поле'), Length(max=30)],
        description='Формат: МУР-2024-001. Генерируется автоматически, можно изменить вручную.'
    )

    # Item
    item_name = StringField('Наименование товара', validators=[DataRequired(message='Обязательное поле'), Length(max=200)])
    item_category = SelectField('Категория', choices=ITEM_CATEGORY_CHOICES, validators=[Optional()])
    item_description = TextAreaField('Описание товара', validators=[Optional()])
    item_serial_number = StringField('Серийный номер', validators=[Optional(), Length(max=100)])
    item_condition = SelectField('Состояние', choices=ITEM_CONDITION_CHOICES, default='new')

    # Supplier
    supplier_name = StringField('Поставщик', validators=[Optional(), Length(max=200)])
    supplier_inn = StringField('ИНН поставщика', validators=[Optional(), Length(max=20)])
    supplier_contract_number = StringField('Договор поставщика №', validators=[Optional(), Length(max=50)])

    # Financials
    cost_price = FloatField('Стоимость товара', validators=[DataRequired(message='Обязательное поле'), NumberRange(min=0.01)])
    markup_percent = FloatField('Наценка (%)', validators=[Optional(), NumberRange(min=0, max=1000)], default=0.0)
    total_price = FloatField('Итоговая цена', validators=[DataRequired(message='Обязательное поле'), NumberRange(min=0.01)])
    down_payment = FloatField('Первоначальный взнос', validators=[Optional(), NumberRange(min=0)], default=0.0)
    financed_amount = FloatField('Финансируемая сумма', validators=[DataRequired(message='Обязательное поле'), NumberRange(min=0.01)])
    months = IntegerField('Срок (месяцев)', validators=[DataRequired(message='Обязательное поле'), NumberRange(min=1, max=360)])
    monthly_payment = FloatField('Ежемесячный платёж', validators=[DataRequired(message='Обязательное поле'), NumberRange(min=0.01)])

    # Dates
    contract_date = DateField('Дата договора', validators=[DataRequired(message='Обязательное поле')])
    first_payment_date = DateField('Дата первого платежа', validators=[DataRequired(message='Обязательное поле')])
    payment_day_of_month = IntegerField('День платежа (число месяца)', validators=[Optional(), NumberRange(min=1, max=28)], default=5)
    payment_method = SelectField('Способ оплаты', choices=PAYMENT_METHOD_CHOICES, default='cash')

    # Sharia
    is_halal = BooleanField('Соответствует нормам Ислама', default=True)
    halal_certificate_number = StringField('Номер Halal-сертификата', validators=[Optional(), Length(max=50)])
    sharia_board_approval = BooleanField('Одобрено Шариатским советом')
    sharia_board_note = TextAreaField('Примечание Шариатского совета', validators=[Optional()])

    # Other
    status = SelectField('Статус', choices=CONTRACT_STATUS_CHOICES, default='active')
    notes = TextAreaField('Примечания', validators=[Optional()])

    submit = SubmitField('Сохранить договор')

    def validate_total_price(self, field):
        if self.cost_price.data and self.markup_percent.data is not None:
            expected = self.cost_price.data * (1 + self.markup_percent.data / 100)
            if abs(field.data - expected) > 1.0:
                raise ValidationError(
                    f'Итоговая цена должна быть равна себестоимости × (1 + наценка/100) = {expected:.2f}'
                )

    def validate_financed_amount(self, field):
        if self.total_price.data and self.down_payment.data is not None:
            expected = self.total_price.data - self.down_payment.data
            if abs(field.data - expected) > 1.0:
                raise ValidationError(
                    f'Финансируемая сумма = Итоговая цена − Взнос = {expected:.2f}'
                )


class PaymentForm(FlaskForm):
    contract_id = HiddenField('contract_id', validators=[DataRequired()])
    schedule_id = HiddenField('schedule_id', validators=[Optional()])

    amount = FloatField('Сумма', validators=[DataRequired(message='Укажите сумму'), NumberRange(min=0.01)])
    payment_date = DateField('Дата платежа', validators=[DataRequired(message='Укажите дату')])
    payment_method = SelectField('Способ оплаты', choices=PAYMENT_METHOD_CHOICES, default='cash')
    receipt_number = StringField('Номер квитанции', validators=[Optional(), Length(max=50)])
    received_by = StringField('Принял', validators=[Optional(), Length(max=100)])
    note = TextAreaField('Примечание', validators=[Optional()])

    submit = SubmitField('Зарегистрировать платёж')
