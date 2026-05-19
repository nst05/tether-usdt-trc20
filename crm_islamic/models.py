from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Client(db.Model):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = db.Column(db.String(20), default='active')  # active/inactive/blacklisted

    # Personal info
    last_name = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))
    birth_date = db.Column(db.Date)
    birth_place = db.Column(db.String(200))
    nationality = db.Column(db.String(100))
    citizenship = db.Column(db.String(100))
    gender = db.Column(db.String(10))  # male/female

    # Passport
    passport_series = db.Column(db.String(10))
    passport_number = db.Column(db.String(20))
    passport_issued_by = db.Column(db.String(300))
    passport_issued_date = db.Column(db.Date)
    passport_expires_date = db.Column(db.Date)

    # Tax/Social
    inn = db.Column(db.String(20))
    snils = db.Column(db.String(20))

    # Contacts
    phone = db.Column(db.String(30))
    phone2 = db.Column(db.String(30))
    email = db.Column(db.String(150))

    # Addresses
    address_registration = db.Column(db.Text)
    address_actual = db.Column(db.Text)

    # Employment
    employer_name = db.Column(db.String(200))
    employer_address = db.Column(db.String(300))
    employer_phone = db.Column(db.String(30))
    position = db.Column(db.String(150))
    employment_type = db.Column(db.String(30))  # employed/self_employed/business_owner/unemployed
    work_experience_months = db.Column(db.Integer)
    monthly_income = db.Column(db.Float, default=0.0)
    additional_income = db.Column(db.Float, default=0.0)
    income_confirmed = db.Column(db.Boolean, default=False)

    # Family
    marital_status = db.Column(db.String(20))  # single/married/divorced/widowed
    children_count = db.Column(db.Integer, default=0)
    dependents_count = db.Column(db.Integer, default=0)
    education = db.Column(db.String(30))  # school/college/university/postgraduate

    # Assets
    own_property = db.Column(db.Boolean, default=False)
    own_car = db.Column(db.Boolean, default=False)

    # Credit
    credit_history_status = db.Column(db.String(20), default='none')  # good/satisfactory/bad/none
    credit_score = db.Column(db.Integer, default=0)

    # Blacklist
    blacklisted = db.Column(db.Boolean, default=False)
    blacklist_reason = db.Column(db.Text)

    # Other
    notes = db.Column(db.Text)
    photo_path = db.Column(db.String(300))

    # Relationships
    contracts = db.relationship('Contract', backref='client', lazy='dynamic')
    guarantor_records = db.relationship('Guarantor', foreign_keys='Guarantor.client_id', backref='client', lazy='dynamic')

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return ' '.join(parts)

    @property
    def active_contracts_count(self):
        return self.contracts.filter_by(status='active').count()

    @property
    def total_balance(self):
        total = 0.0
        for c in self.contracts.filter(Contract.status.in_(['active', 'overdue'])):
            total += c.remaining_amount
        return total

    def __repr__(self):
        return f'<Client {self.full_name}>'


class Guarantor(db.Model):
    __tablename__ = 'guarantors'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'), nullable=False)

    relationship = db.Column(db.String(30))  # parent/spouse/sibling/friend/colleague/other
    guarantor_type = db.Column(db.String(20), default='personal')  # personal/property
    property_description = db.Column(db.Text)

    # Personal fields
    last_name = db.Column(db.String(100))
    first_name = db.Column(db.String(100))
    middle_name = db.Column(db.String(100))
    phone = db.Column(db.String(30))
    passport_series = db.Column(db.String(10))
    passport_number = db.Column(db.String(20))
    passport_issued_by = db.Column(db.String(300))
    passport_issued_date = db.Column(db.Date)
    address_registration = db.Column(db.Text)
    employer_name = db.Column(db.String(200))
    monthly_income = db.Column(db.Float, default=0.0)

    notes = db.Column(db.Text)

    @property
    def full_name(self):
        parts = [p for p in [self.last_name, self.first_name, self.middle_name] if p]
        return ' '.join(parts) if parts else 'Неизвестно'

    def __repr__(self):
        return f'<Guarantor {self.full_name}>'


class Contract(db.Model):
    __tablename__ = 'contracts'

    id = db.Column(db.Integer, primary_key=True)
    contract_number = db.Column(db.String(30), unique=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)

    # Item details
    item_name = db.Column(db.String(200), nullable=False)
    item_category = db.Column(db.String(30))  # appliances/electronics/furniture/auto/real_estate/education/medical/other
    item_description = db.Column(db.Text)
    item_serial_number = db.Column(db.String(100))
    item_condition = db.Column(db.String(10), default='new')  # new/used

    # Supplier
    supplier_name = db.Column(db.String(200))
    supplier_inn = db.Column(db.String(20))
    supplier_contract_number = db.Column(db.String(50))

    # Financials
    cost_price = db.Column(db.Float, nullable=False)
    markup_percent = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float, nullable=False)
    down_payment = db.Column(db.Float, default=0.0)
    financed_amount = db.Column(db.Float, nullable=False)
    months = db.Column(db.Integer, nullable=False)
    monthly_payment = db.Column(db.Float, nullable=False)

    # Dates
    contract_date = db.Column(db.Date, nullable=False, default=date.today)
    first_payment_date = db.Column(db.Date)
    last_payment_date = db.Column(db.Date)
    payment_day_of_month = db.Column(db.Integer, default=5)

    # Payment
    payment_method = db.Column(db.String(20), default='cash')  # cash/bank_transfer/card/online

    # Sharia
    is_halal = db.Column(db.Boolean, default=True)
    halal_certificate_number = db.Column(db.String(50))
    sharia_board_approval = db.Column(db.Boolean, default=False)
    sharia_board_note = db.Column(db.Text)

    # Status
    status = db.Column(db.String(20), default='draft')  # draft/active/overdue/closed/cancelled
    early_closure_date = db.Column(db.Date)
    early_closure_reason = db.Column(db.Text)

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    schedule = db.relationship('PaymentSchedule', backref='contract', lazy='dynamic', cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='contract', lazy='dynamic', cascade='all, delete-orphan')
    guarantors = db.relationship('Guarantor', backref='contract', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def paid_amount(self):
        from sqlalchemy import func
        result = db.session.execute(
            db.select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.contract_id == self.id)
        ).scalar()
        return float(result or 0)

    @property
    def remaining_amount(self):
        return max(0.0, self.financed_amount - self.paid_amount)

    @property
    def progress_percent(self):
        if self.financed_amount <= 0:
            return 0
        return min(100, int((self.paid_amount / self.financed_amount) * 100))

    @property
    def overdue_schedules(self):
        return self.schedule.filter(
            PaymentSchedule.status == 'overdue'
        ).all()

    @property
    def next_payment(self):
        from sqlalchemy import asc
        today = date.today()
        return self.schedule.filter(
            PaymentSchedule.status.in_(['pending', 'partial']),
            PaymentSchedule.due_date >= today
        ).order_by(asc(PaymentSchedule.due_date)).first()

    def __repr__(self):
        return f'<Contract {self.contract_number}>'


class PaymentSchedule(db.Model):
    __tablename__ = 'payment_schedules'

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'), nullable=False)
    installment_num = db.Column(db.Integer)
    due_date = db.Column(db.Date)
    amount = db.Column(db.Float)
    status = db.Column(db.String(20), default='pending')  # pending/paid/overdue/partial
    paid_amount = db.Column(db.Float, default=0.0)
    paid_date = db.Column(db.Date, nullable=True)

    payments = db.relationship('Payment', backref='schedule', lazy='dynamic')

    @property
    def remaining(self):
        return max(0.0, (self.amount or 0.0) - (self.paid_amount or 0.0))

    def __repr__(self):
        return f'<PaymentSchedule {self.contract_id}#{self.installment_num}>'


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('payment_schedules.id'), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False, default=date.today)
    payment_method = db.Column(db.String(20), default='cash')
    receipt_number = db.Column(db.String(50))
    received_by = db.Column(db.String(100))
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Payment {self.id} {self.amount}>'


class Backup(db.Model):
    __tablename__ = 'backups'

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    filename = db.Column(db.String(200))
    file_size_kb = db.Column(db.Float, default=0.0)
    backup_type = db.Column(db.String(20), default='manual')  # manual/auto
    notes = db.Column(db.Text)

    def __repr__(self):
        return f'<Backup {self.filename}>'


class Document(db.Model):
    __tablename__ = 'documents'

    id          = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(20), nullable=False)   # client / contract / guarantor
    entity_id   = db.Column(db.Integer, nullable=False)
    doc_type    = db.Column(db.String(50), default='other')  # passport_front / passport_back / contract / income / other
    filename    = db.Column(db.String(255), nullable=False)   # stored filename (uuid-based)
    original_name = db.Column(db.String(255))
    file_size_kb  = db.Column(db.Float, default=0.0)
    mime_type   = db.Column(db.String(100))
    notes       = db.Column(db.Text)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    TYPE_LABELS = {
        'passport_front': 'Паспорт (лицевая)',
        'passport_back':  'Паспорт (оборот)',
        'contract':       'Договор',
        'income':         'Справка о доходах',
        'other':          'Другое',
    }

    ICONS = {
        'passport_front': 'bi-person-vcard',
        'passport_back':  'bi-person-vcard-fill',
        'contract':       'bi-file-earmark-text',
        'income':         'bi-file-earmark-bar-graph',
        'other':          'bi-file-earmark',
    }

    @property
    def type_label(self):
        return self.TYPE_LABELS.get(self.doc_type, 'Другое')

    @property
    def icon(self):
        return self.ICONS.get(self.doc_type, 'bi-file-earmark')

    def __repr__(self):
        return f'<Document {self.filename}>'

