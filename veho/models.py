from datetime import datetime, date

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# ── Status catalogues ────────────────────────────────────────────────────────

SHIPMENT_STATUS_FLOW = [
    'created',        # Создано
    'picked_up',      # Забрано у отправителя
    'in_transit',     # В пути / на сортировке
    'out_for_delivery',  # Передано курьеру на доставку
    'delivered',      # Доставлено
]

SHIPMENT_STATUS_LABELS = {
    'created': 'Создано',
    'picked_up': 'Забрано',
    'in_transit': 'В пути',
    'out_for_delivery': 'На доставке',
    'delivered': 'Доставлено',
    'returned': 'Возврат',
    'cancelled': 'Отменено',
}

SHIPMENT_STATUS_COLORS = {
    'created': 'secondary',
    'picked_up': 'info',
    'in_transit': 'primary',
    'out_for_delivery': 'warning',
    'delivered': 'success',
    'returned': 'dark',
    'cancelled': 'danger',
}

COURIER_STATUS_LABELS = {
    'active': 'Активен',
    'on_delivery': 'На доставке',
    'inactive': 'Не работает',
}


class Client(db.Model):
    """Отправитель — частное лицо или бизнес, который отправляет посылки."""
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    name = db.Column(db.String(200), nullable=False)          # ФИО или название компании
    client_type = db.Column(db.String(20), default='individual')  # individual/business
    contact_person = db.Column(db.String(200))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(150))
    address = db.Column(db.Text)
    notes = db.Column(db.Text)

    shipments = db.relationship('Shipment', backref='client', lazy=True)

    @property
    def type_label(self):
        return 'Бизнес' if self.client_type == 'business' else 'Частное лицо'


class Courier(db.Model):
    """Курьер, выполняющий доставку."""
    __tablename__ = 'couriers'

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active')  # active/on_delivery/inactive

    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30))
    email = db.Column(db.String(150))

    vehicle_type = db.Column(db.String(20), default='car')  # car/van/scooter/bike/foot
    vehicle_number = db.Column(db.String(30))
    zone = db.Column(db.String(120))  # район/зона обслуживания
    notes = db.Column(db.Text)

    shipments = db.relationship('Shipment', backref='courier', lazy=True)

    @property
    def full_name(self):
        return f'{self.last_name} {self.first_name}'.strip()

    @property
    def status_label(self):
        return COURIER_STATUS_LABELS.get(self.status, self.status)

    @property
    def vehicle_label(self):
        return {
            'car': 'Автомобиль',
            'van': 'Фургон',
            'scooter': 'Скутер',
            'bike': 'Велосипед',
            'foot': 'Пешком',
        }.get(self.vehicle_type, self.vehicle_type)

    @property
    def active_shipments(self):
        return [s for s in self.shipments
                if s.status in ('picked_up', 'in_transit', 'out_for_delivery')]

    @property
    def delivered_count(self):
        return sum(1 for s in self.shipments if s.status == 'delivered')


class Shipment(db.Model):
    """Отправление (посылка) — центральная сущность сервиса доставки."""
    __tablename__ = 'shipments'

    id = db.Column(db.Integer, primary_key=True)
    tracking_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    status = db.Column(db.String(20), default='created')

    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'))
    courier_id = db.Column(db.Integer, db.ForeignKey('couriers.id'))

    # Отправитель
    sender_name = db.Column(db.String(200), nullable=False)
    sender_phone = db.Column(db.String(30))
    sender_address = db.Column(db.Text, nullable=False)

    # Получатель
    recipient_name = db.Column(db.String(200), nullable=False)
    recipient_phone = db.Column(db.String(30))
    recipient_address = db.Column(db.Text, nullable=False)

    # Параметры груза
    description = db.Column(db.String(300))
    weight_kg = db.Column(db.Float, default=0.0)
    dimensions = db.Column(db.String(60))  # ДxШxВ
    service_type = db.Column(db.String(20), default='standard')  # standard/express/same_day

    price = db.Column(db.Float, default=0.0)
    cod_amount = db.Column(db.Float, default=0.0)  # наложенный платёж

    scheduled_date = db.Column(db.Date)
    delivered_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)

    events = db.relationship(
        'ShipmentEvent', backref='shipment', lazy=True,
        cascade='all, delete-orphan', order_by='ShipmentEvent.timestamp.desc()'
    )

    @property
    def status_label(self):
        return SHIPMENT_STATUS_LABELS.get(self.status, self.status)

    @property
    def status_color(self):
        return SHIPMENT_STATUS_COLORS.get(self.status, 'secondary')

    @property
    def service_label(self):
        return {
            'standard': 'Стандарт',
            'express': 'Экспресс',
            'same_day': 'В день заказа',
        }.get(self.service_type, self.service_type)

    @property
    def is_active(self):
        return self.status not in ('delivered', 'returned', 'cancelled')

    @property
    def progress_percent(self):
        if self.status in ('returned', 'cancelled'):
            return 0
        if self.status not in SHIPMENT_STATUS_FLOW:
            return 0
        idx = SHIPMENT_STATUS_FLOW.index(self.status)
        return int((idx / (len(SHIPMENT_STATUS_FLOW) - 1)) * 100)


class ShipmentEvent(db.Model):
    """Событие в истории отслеживания посылки."""
    __tablename__ = 'shipment_events'

    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipments.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20))
    location = db.Column(db.String(200))
    comment = db.Column(db.String(300))

    @property
    def status_label(self):
        return SHIPMENT_STATUS_LABELS.get(self.status, self.status)

    @property
    def status_color(self):
        return SHIPMENT_STATUS_COLORS.get(self.status, 'secondary')
