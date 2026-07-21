import os
import sys
import random
import string
from datetime import date, datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, abort
)
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, desc, or_

try:
    from .models import (
        db, Client, Courier, Shipment, ShipmentEvent,
        SHIPMENT_STATUS_LABELS, SHIPMENT_STATUS_COLORS, SHIPMENT_STATUS_FLOW,
    )
    from .forms import ClientForm, CourierForm, ShipmentForm
except ImportError:  # запуск как отдельный скрипт (python run.py)
    from models import (
        db, Client, Courier, Shipment, ShipmentEvent,
        SHIPMENT_STATUS_LABELS, SHIPMENT_STATUS_COLORS, SHIPMENT_STATUS_FLOW,
    )
    from forms import ClientForm, CourierForm, ShipmentForm


def generate_tracking_number():
    """VEH-YYYY-XXXXXX (уникальный)."""
    year = datetime.utcnow().year
    while True:
        suffix = ''.join(random.choices(string.digits, k=6))
        tn = f'VEH-{year}-{suffix}'
        exists = db.session.execute(
            db.select(Shipment).where(Shipment.tracking_number == tn)
        ).scalars().first()
        if not exists:
            return tn


def create_app(config=None):
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, 'templates'),
        static_folder=os.path.join(base_dir, 'static'),
    )
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'veho-delivery-secret-key-2026')

    if getattr(sys, 'frozen', False):
        db_dir = os.environ.get('VEHO_DB_DIR', os.path.dirname(sys.executable))
    else:
        db_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(db_dir, 'veho.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_ENABLED'] = True

    if config:
        app.config.update(config)

    db.init_app(app)
    CSRFProtect(app)

    # ── template helpers ──────────────────────────────────────────────────────
    @app.context_processor
    def inject_globals():
        return {
            'now': datetime.utcnow(),
            'STATUS_LABELS': SHIPMENT_STATUS_LABELS,
            'STATUS_COLORS': SHIPMENT_STATUS_COLORS,
        }

    def _add_event(shipment, status, location=None, comment=None):
        db.session.add(ShipmentEvent(
            shipment_id=shipment.id,
            status=status,
            location=location,
            comment=comment,
        ))

    def _populate_shipment_choices(form):
        clients = db.session.execute(
            db.select(Client).order_by(Client.name)
        ).scalars().all()
        couriers = db.session.execute(
            db.select(Courier).where(Courier.status != 'inactive').order_by(Courier.last_name)
        ).scalars().all()
        form.client_id.choices = [(0, '— без клиента —')] + [
            (c.id, c.name) for c in clients
        ]
        form.courier_id.choices = [(0, '— не назначен —')] + [
            (c.id, c.full_name) for c in couriers
        ]

    # ── Dashboard ─────────────────────────────────────────────────────────────
    @app.route('/')
    def dashboard():
        total = db.session.scalar(db.select(func.count(Shipment.id))) or 0
        active = db.session.scalar(
            db.select(func.count(Shipment.id)).where(
                Shipment.status.in_(['created', 'picked_up', 'in_transit', 'out_for_delivery'])
            )
        ) or 0
        delivered = db.session.scalar(
            db.select(func.count(Shipment.id)).where(Shipment.status == 'delivered')
        ) or 0
        couriers_active = db.session.scalar(
            db.select(func.count(Courier.id)).where(Courier.status != 'inactive')
        ) or 0

        # разбивка по статусам
        status_rows = db.session.execute(
            db.select(Shipment.status, func.count(Shipment.id)).group_by(Shipment.status)
        ).all()
        status_counts = {s: c for s, c in status_rows}

        revenue = db.session.scalar(
            db.select(func.coalesce(func.sum(Shipment.price), 0.0)).where(
                Shipment.status == 'delivered'
            )
        ) or 0.0

        recent = db.session.execute(
            db.select(Shipment).order_by(desc(Shipment.created_at)).limit(8)
        ).scalars().all()

        couriers = db.session.execute(
            db.select(Courier).where(Courier.status != 'inactive').order_by(Courier.last_name)
        ).scalars().all()

        return render_template(
            'dashboard.html',
            total=total, active=active, delivered=delivered,
            couriers_active=couriers_active, revenue=revenue,
            status_counts=status_counts, recent=recent, couriers=couriers,
            status_flow=SHIPMENT_STATUS_FLOW,
        )

    # ── Shipments ─────────────────────────────────────────────────────────────
    @app.route('/shipments')
    def shipments_list():
        status = request.args.get('status', '')
        q = request.args.get('q', '').strip()
        query = db.select(Shipment)
        if status:
            query = query.where(Shipment.status == status)
        if q:
            like = f'%{q}%'
            query = query.where(or_(
                Shipment.tracking_number.ilike(like),
                Shipment.recipient_name.ilike(like),
                Shipment.sender_name.ilike(like),
                Shipment.recipient_phone.ilike(like),
            ))
        query = query.order_by(desc(Shipment.created_at))
        shipments = db.session.execute(query).scalars().all()
        return render_template('shipments/list.html', shipments=shipments,
                               status=status, q=q)

    @app.route('/shipments/new', methods=['GET', 'POST'])
    def shipment_new():
        form = ShipmentForm()
        _populate_shipment_choices(form)
        if form.validate_on_submit():
            s = Shipment(tracking_number=generate_tracking_number())
            _apply_shipment_form(form, s)
            db.session.add(s)
            db.session.flush()
            _add_event(s, s.status, comment='Отправление создано')
            db.session.commit()
            flash(f'Отправление {s.tracking_number} создано.', 'success')
            return redirect(url_for('shipment_detail', shipment_id=s.id))
        return render_template('shipments/form.html', form=form, shipment=None)

    @app.route('/shipments/<int:shipment_id>')
    def shipment_detail(shipment_id):
        s = db.session.get(Shipment, shipment_id) or abort(404)
        couriers = db.session.execute(
            db.select(Courier).where(Courier.status != 'inactive').order_by(Courier.last_name)
        ).scalars().all()
        return render_template('shipments/detail.html', shipment=s,
                               couriers=couriers, status_flow=SHIPMENT_STATUS_FLOW)

    @app.route('/shipments/<int:shipment_id>/edit', methods=['GET', 'POST'])
    def shipment_edit(shipment_id):
        s = db.session.get(Shipment, shipment_id) or abort(404)
        form = ShipmentForm(obj=s)
        _populate_shipment_choices(form)
        if request.method == 'GET':
            form.client_id.data = s.client_id or 0
            form.courier_id.data = s.courier_id or 0
        if form.validate_on_submit():
            old_status = s.status
            _apply_shipment_form(form, s)
            if s.status != old_status:
                _add_event(s, s.status, comment='Статус изменён вручную')
                if s.status == 'delivered' and not s.delivered_at:
                    s.delivered_at = datetime.utcnow()
            db.session.commit()
            flash('Изменения сохранены.', 'success')
            return redirect(url_for('shipment_detail', shipment_id=s.id))
        return render_template('shipments/form.html', form=form, shipment=s)

    @app.route('/shipments/<int:shipment_id>/advance', methods=['POST'])
    def shipment_advance(shipment_id):
        """Продвинуть посылку на следующий статус в потоке доставки."""
        s = db.session.get(Shipment, shipment_id) or abort(404)
        location = request.form.get('location', '').strip() or None
        if s.status in SHIPMENT_STATUS_FLOW:
            idx = SHIPMENT_STATUS_FLOW.index(s.status)
            if idx < len(SHIPMENT_STATUS_FLOW) - 1:
                s.status = SHIPMENT_STATUS_FLOW[idx + 1]
                _add_event(s, s.status, location=location)
                if s.status == 'delivered':
                    s.delivered_at = datetime.utcnow()
                    if s.courier and s.courier.status == 'on_delivery':
                        s.courier.status = 'active'
                db.session.commit()
                flash(f'Статус обновлён: {s.status_label}.', 'success')
            else:
                flash('Посылка уже доставлена.', 'info')
        else:
            flash('Невозможно продвинуть статус.', 'warning')
        return redirect(url_for('shipment_detail', shipment_id=s.id))

    @app.route('/shipments/<int:shipment_id>/status/<new_status>', methods=['POST'])
    def shipment_set_status(shipment_id, new_status):
        s = db.session.get(Shipment, shipment_id) or abort(404)
        if new_status not in SHIPMENT_STATUS_LABELS:
            abort(400)
        s.status = new_status
        if new_status == 'delivered':
            s.delivered_at = datetime.utcnow()
        _add_event(s, new_status, comment='Статус изменён')
        db.session.commit()
        flash(f'Статус: {s.status_label}.', 'success')
        return redirect(url_for('shipment_detail', shipment_id=s.id))

    @app.route('/shipments/<int:shipment_id>/assign', methods=['POST'])
    def shipment_assign(shipment_id):
        s = db.session.get(Shipment, shipment_id) or abort(404)
        courier_id = request.form.get('courier_id', type=int)
        courier = db.session.get(Courier, courier_id) if courier_id else None
        s.courier_id = courier.id if courier else None
        if courier:
            if courier.status == 'active':
                courier.status = 'on_delivery'
            _add_event(s, s.status, comment=f'Назначен курьер: {courier.full_name}')
        db.session.commit()
        flash('Курьер назначен.' if courier else 'Курьер снят.', 'success')
        return redirect(url_for('shipment_detail', shipment_id=s.id))

    @app.route('/shipments/<int:shipment_id>/delete', methods=['POST'])
    def shipment_delete(shipment_id):
        s = db.session.get(Shipment, shipment_id) or abort(404)
        tn = s.tracking_number
        db.session.delete(s)
        db.session.commit()
        flash(f'Отправление {tn} удалено.', 'success')
        return redirect(url_for('shipments_list'))

    def _apply_shipment_form(form, s):
        s.client_id = form.client_id.data or None
        s.courier_id = form.courier_id.data or None
        s.sender_name = form.sender_name.data
        s.sender_phone = form.sender_phone.data
        s.sender_address = form.sender_address.data
        s.recipient_name = form.recipient_name.data
        s.recipient_phone = form.recipient_phone.data
        s.recipient_address = form.recipient_address.data
        s.description = form.description.data
        s.weight_kg = form.weight_kg.data or 0.0
        s.dimensions = form.dimensions.data
        s.service_type = form.service_type.data
        s.price = form.price.data or 0.0
        s.cod_amount = form.cod_amount.data or 0.0
        s.status = form.status.data
        s.scheduled_date = form.scheduled_date.data
        s.notes = form.notes.data

    # ── Couriers ──────────────────────────────────────────────────────────────
    @app.route('/couriers')
    def couriers_list():
        couriers = db.session.execute(
            db.select(Courier).order_by(Courier.status, Courier.last_name)
        ).scalars().all()
        return render_template('couriers/list.html', couriers=couriers)

    @app.route('/couriers/new', methods=['GET', 'POST'])
    def courier_new():
        form = CourierForm()
        if form.validate_on_submit():
            c = Courier()
            _apply_courier_form(form, c)
            db.session.add(c)
            db.session.commit()
            flash('Курьер добавлен.', 'success')
            return redirect(url_for('couriers_list'))
        return render_template('couriers/form.html', form=form, courier=None)

    @app.route('/couriers/<int:courier_id>')
    def courier_detail(courier_id):
        c = db.session.get(Courier, courier_id) or abort(404)
        shipments = db.session.execute(
            db.select(Shipment).where(Shipment.courier_id == c.id)
            .order_by(desc(Shipment.created_at))
        ).scalars().all()
        return render_template('couriers/detail.html', courier=c, shipments=shipments)

    @app.route('/couriers/<int:courier_id>/edit', methods=['GET', 'POST'])
    def courier_edit(courier_id):
        c = db.session.get(Courier, courier_id) or abort(404)
        form = CourierForm(obj=c)
        if form.validate_on_submit():
            _apply_courier_form(form, c)
            db.session.commit()
            flash('Изменения сохранены.', 'success')
            return redirect(url_for('courier_detail', courier_id=c.id))
        return render_template('couriers/form.html', form=form, courier=c)

    @app.route('/couriers/<int:courier_id>/delete', methods=['POST'])
    def courier_delete(courier_id):
        c = db.session.get(Courier, courier_id) or abort(404)
        if c.shipments:
            flash('Нельзя удалить курьера с привязанными отправлениями.', 'warning')
            return redirect(url_for('courier_detail', courier_id=c.id))
        db.session.delete(c)
        db.session.commit()
        flash('Курьер удалён.', 'success')
        return redirect(url_for('couriers_list'))

    def _apply_courier_form(form, c):
        c.first_name = form.first_name.data
        c.last_name = form.last_name.data
        c.phone = form.phone.data
        c.email = form.email.data
        c.status = form.status.data
        c.vehicle_type = form.vehicle_type.data
        c.vehicle_number = form.vehicle_number.data
        c.zone = form.zone.data
        c.notes = form.notes.data

    # ── Clients ───────────────────────────────────────────────────────────────
    @app.route('/clients')
    def clients_list():
        clients = db.session.execute(
            db.select(Client).order_by(Client.name)
        ).scalars().all()
        return render_template('clients/list.html', clients=clients)

    @app.route('/clients/new', methods=['GET', 'POST'])
    def client_new():
        form = ClientForm()
        if form.validate_on_submit():
            c = Client()
            _apply_client_form(form, c)
            db.session.add(c)
            db.session.commit()
            flash('Клиент добавлен.', 'success')
            return redirect(url_for('clients_list'))
        return render_template('clients/form.html', form=form, client=None)

    @app.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
    def client_edit(client_id):
        c = db.session.get(Client, client_id) or abort(404)
        form = ClientForm(obj=c)
        if form.validate_on_submit():
            _apply_client_form(form, c)
            db.session.commit()
            flash('Изменения сохранены.', 'success')
            return redirect(url_for('clients_list'))
        return render_template('clients/form.html', form=form, client=c)

    @app.route('/clients/<int:client_id>/delete', methods=['POST'])
    def client_delete(client_id):
        c = db.session.get(Client, client_id) or abort(404)
        if c.shipments:
            flash('Нельзя удалить клиента с привязанными отправлениями.', 'warning')
            return redirect(url_for('clients_list'))
        db.session.delete(c)
        db.session.commit()
        flash('Клиент удалён.', 'success')
        return redirect(url_for('clients_list'))

    def _apply_client_form(form, c):
        c.name = form.name.data
        c.client_type = form.client_type.data
        c.contact_person = form.contact_person.data
        c.phone = form.phone.data
        c.email = form.email.data
        c.address = form.address.data
        c.notes = form.notes.data

    # ── Public tracking ───────────────────────────────────────────────────────
    @app.route('/track', methods=['GET'])
    def track():
        tn = request.args.get('tracking', '').strip()
        shipment = None
        if tn:
            shipment = db.session.execute(
                db.select(Shipment).where(Shipment.tracking_number == tn)
            ).scalars().first()
        return render_template('track.html', shipment=shipment, tracking=tn,
                               searched=bool(tn))

    # ── API (JSON) ────────────────────────────────────────────────────────────
    @app.route('/api/shipments/<tracking>')
    def api_track(tracking):
        s = db.session.execute(
            db.select(Shipment).where(Shipment.tracking_number == tracking)
        ).scalars().first()
        if not s:
            return jsonify({'error': 'not_found'}), 404
        return jsonify({
            'tracking_number': s.tracking_number,
            'status': s.status,
            'status_label': s.status_label,
            'recipient': s.recipient_name,
            'service': s.service_label,
            'progress': s.progress_percent,
            'events': [
                {
                    'timestamp': e.timestamp.isoformat(),
                    'status': e.status,
                    'status_label': e.status_label,
                    'location': e.location,
                    'comment': e.comment,
                } for e in s.events
            ],
        })

    # ── errors ────────────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    with app.app_context():
        db.create_all()

    return app


app = create_app()
