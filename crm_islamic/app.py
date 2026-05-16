import os
import csv
import io
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, abort, Response
)
from flask_wtf.csrf import CSRFProtect, generate_csrf
from sqlalchemy import func, desc, asc, extract

from .models import db, Client, Contract, PaymentSchedule, Payment, Guarantor, Backup
from .forms import (
    ClientForm, ContractForm, PaymentForm, GuarantorForm,
    EMPLOYMENT_CHOICES, MARITAL_CHOICES, EDUCATION_CHOICES,
    CREDIT_HISTORY_CHOICES, STATUS_CHOICES, ITEM_CATEGORY_CHOICES,
    PAYMENT_METHOD_CHOICES
)
from . import backup as backup_module


def create_app(config=None):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'islamic-crm-secret-key-2024-murabaha')
    
    db_path = os.path.join(os.path.dirname(__file__), 'crm_islamic.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_ENABLED'] = True

    if config:
        app.config.update(config)

    db.init_app(app)
    csrf = CSRFProtect(app)

    # ── helpers ────────────────────────────────────────────────────────────────

    def generate_contract_number():
        year = datetime.utcnow().year
        last = db.session.execute(
            db.select(Contract).where(
                Contract.contract_number.like(f'МУР-{year}-%')
            ).order_by(desc(Contract.id))
        ).scalars().first()
        if last and last.contract_number:
            try:
                seq = int(last.contract_number.split('-')[-1]) + 1
            except Exception:
                seq = 1
        else:
            seq = 1
        return f'МУР-{year}-{seq:03d}'

    def generate_schedule(contract):
        """Delete existing schedule rows and create fresh ones."""
        db.session.execute(
            db.delete(PaymentSchedule).where(PaymentSchedule.contract_id == contract.id)
        )
        db.session.flush()

        if not contract.first_payment_date or not contract.months:
            return

        base = contract.first_payment_date
        for i in range(contract.months):
            due = base + relativedelta(months=i)
            ps = PaymentSchedule(
                contract_id=contract.id,
                installment_num=i + 1,
                due_date=due,
                amount=round(contract.monthly_payment, 2),
                status='pending',
                paid_amount=0.0,
            )
            db.session.add(ps)

        contract.last_payment_date = base + relativedelta(months=contract.months - 1)
        db.session.flush()

    def update_overdue_statuses():
        today = date.today()
        # Mark overdue schedule items
        db.session.execute(
            db.update(PaymentSchedule).where(
                PaymentSchedule.due_date < today,
                PaymentSchedule.status.in_(['pending', 'partial'])
            ).values(status='overdue')
        )
        # Mark contracts as overdue if they have overdue schedules
        overdue_contract_ids = db.session.execute(
            db.select(PaymentSchedule.contract_id).where(
                PaymentSchedule.status == 'overdue'
            ).distinct()
        ).scalars().all()

        if overdue_contract_ids:
            db.session.execute(
                db.update(Contract).where(
                    Contract.id.in_(overdue_contract_ids),
                    Contract.status == 'active'
                ).values(status='overdue')
            )
        db.session.commit()

    @app.before_request
    def before_each_request():
        update_overdue_statuses()

    # ── context processors ────────────────────────────────────────────────────

    @app.context_processor
    def inject_globals():
        today = date.today()
        overdue_count = db.session.execute(
            db.select(func.count(Contract.id)).where(Contract.status == 'overdue')
        ).scalar() or 0
        return dict(today=today, nav_overdue_count=overdue_count, csrf_token=generate_csrf)

    # ── error handlers ────────────────────────────────────────────────────────

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    # ══════════════════════════════════════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/')
    def dashboard():
        today = date.today()
        total_clients = db.session.execute(
            db.select(func.count(Client.id)).where(Client.status != 'blacklisted')
        ).scalar() or 0

        active_contracts = db.session.execute(
            db.select(func.count(Contract.id)).where(Contract.status.in_(['active', 'overdue']))
        ).scalar() or 0

        portfolio = db.session.execute(
            db.select(func.coalesce(func.sum(Contract.financed_amount), 0)).where(
                Contract.status.in_(['active', 'overdue'])
            )
        ).scalar() or 0

        overdue_contracts = db.session.execute(
            db.select(func.count(Contract.id)).where(Contract.status == 'overdue')
        ).scalar() or 0

        # Today's collections
        today_collected = db.session.execute(
            db.select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.payment_date == today
            )
        ).scalar() or 0

        # Upcoming payments next 7 days
        upcoming = db.session.execute(
            db.select(PaymentSchedule).where(
                PaymentSchedule.due_date >= today,
                PaymentSchedule.due_date <= today + timedelta(days=7),
                PaymentSchedule.status.in_(['pending', 'partial'])
            ).order_by(asc(PaymentSchedule.due_date)).limit(20)
        ).scalars().all()

        # Overdue contracts with days overdue
        overdue_list = db.session.execute(
            db.select(Contract).where(Contract.status == 'overdue').limit(10)
        ).scalars().all()

        return render_template('dashboard.html',
            total_clients=total_clients,
            active_contracts=active_contracts,
            portfolio=portfolio,
            overdue_contracts=overdue_contracts,
            today_collected=today_collected,
            upcoming=upcoming,
            overdue_list=overdue_list,
            today=today,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # CLIENTS
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/clients')
    def clients_list():
        q = request.args.get('q', '').strip()
        status_f = request.args.get('status', '')
        emp_f = request.args.get('employment_type', '')
        score_min = request.args.get('score_min', type=int)
        score_max = request.args.get('score_max', type=int)

        stmt = db.select(Client)
        if q:
            like = f'%{q}%'
            stmt = stmt.where(
                (Client.last_name.ilike(like)) |
                (Client.first_name.ilike(like)) |
                (Client.middle_name.ilike(like)) |
                (Client.phone.ilike(like)) |
                (Client.inn.ilike(like))
            )
        if status_f:
            stmt = stmt.where(Client.status == status_f)
        if emp_f:
            stmt = stmt.where(Client.employment_type == emp_f)
        if score_min is not None:
            stmt = stmt.where(Client.credit_score >= score_min)
        if score_max is not None:
            stmt = stmt.where(Client.credit_score <= score_max)

        stmt = stmt.order_by(desc(Client.created_at))
        clients = db.session.execute(stmt).scalars().all()

        # Export CSV
        if request.args.get('export') == 'csv':
            def generate():
                output = io.StringIO()
                w = csv.writer(output)
                w.writerow(['ID', 'Фамилия', 'Имя', 'Отчество', 'Телефон', 'Статус', 'Кредитный балл', 'Договоры'])
                for c in clients:
                    w.writerow([c.id, c.last_name, c.first_name, c.middle_name or '',
                                 c.phone or '', c.status, c.credit_score,
                                 c.contracts.count()])
                    output.seek(0)
                    yield output.read()
                    output.seek(0)
                    output.truncate()
            return Response(generate(), mimetype='text/csv',
                            headers={'Content-Disposition': 'attachment;filename=clients.csv'})

        return render_template('clients/list.html', clients=clients,
                               q=q, status_f=status_f, emp_f=emp_f,
                               score_min=score_min, score_max=score_max,
                               status_choices=STATUS_CHOICES,
                               employment_choices=EMPLOYMENT_CHOICES)

    @app.route('/clients/new', methods=['GET', 'POST'])
    def client_new():
        form = ClientForm()
        if form.validate_on_submit():
            client = Client()
            _populate_client(client, form)
            db.session.add(client)
            db.session.commit()
            flash(f'Клиент {client.full_name} добавлен', 'success')
            return redirect(url_for('client_detail', client_id=client.id))
        return render_template('clients/form.html', form=form, title='Новый клиент', client=None)

    @app.route('/clients/<int:client_id>')
    def client_detail(client_id):
        client = db.session.get(Client, client_id) or abort(404)
        contracts = db.session.execute(
            db.select(Contract).where(Contract.client_id == client_id).order_by(desc(Contract.created_at))
        ).scalars().all()
        guarantor_records = db.session.execute(
            db.select(Guarantor).where(Guarantor.client_id == client_id)
        ).scalars().all()
        return render_template('clients/detail.html', client=client,
                               contracts=contracts, guarantor_records=guarantor_records)

    @app.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
    def client_edit(client_id):
        client = db.session.get(Client, client_id) or abort(404)
        form = ClientForm(obj=client)
        if form.validate_on_submit():
            _populate_client(client, form)
            client.updated_at = datetime.utcnow()
            db.session.commit()
            flash('Данные клиента обновлены', 'success')
            return redirect(url_for('client_detail', client_id=client.id))
        return render_template('clients/form.html', form=form, title='Редактировать клиента', client=client)

    @app.route('/clients/<int:client_id>/delete', methods=['POST'])
    def client_delete(client_id):
        client = db.session.get(Client, client_id) or abort(404)
        client.status = 'inactive'
        db.session.commit()
        flash(f'Клиент {client.full_name} деактивирован', 'warning')
        return redirect(url_for('clients_list'))

    def _populate_client(client, form):
        for field in form:
            if field.name not in ('submit', 'csrf_token'):
                try:
                    setattr(client, field.name, field.data)
                except Exception:
                    pass

    # ══════════════════════════════════════════════════════════════════════════
    # GUARANTORS
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/guarantors/new', methods=['GET', 'POST'])
    def guarantor_new():
        contract_id = request.args.get('contract_id', type=int) or request.form.get('contract_id', type=int)
        contract = db.session.get(Contract, contract_id) or abort(404)
        form = GuarantorForm(contract_id=contract_id)
        if request.method == 'GET':
            form.contract_id.data = contract_id
        if form.validate_on_submit():
            g = Guarantor(
                contract_id=contract_id,
                client_id=form.client_id.data or None,
                relationship=form.relationship.data,
                last_name=form.last_name.data,
                first_name=form.first_name.data,
                middle_name=form.middle_name.data,
                phone=form.phone.data,
                passport_series=form.passport_series.data,
                passport_number=form.passport_number.data,
                passport_issued_by=form.passport_issued_by.data,
                passport_issued_date=form.passport_issued_date.data,
                address_registration=form.address_registration.data,
                employer_name=form.employer_name.data,
                monthly_income=form.monthly_income.data or 0,
                guarantor_type=form.guarantor_type.data,
                property_description=form.property_description.data,
                notes=form.notes.data,
            )
            db.session.add(g)
            db.session.commit()
            flash('Поручитель добавлен', 'success')
            return redirect(url_for('contract_detail', contract_id=contract_id))
        return render_template('guarantors/form.html', form=form, contract=contract, title='Новый поручитель')

    @app.route('/guarantors/<int:g_id>/edit', methods=['GET', 'POST'])
    def guarantor_edit(g_id):
        g = db.session.get(Guarantor, g_id) or abort(404)
        contract = db.session.get(Contract, g.contract_id)
        form = GuarantorForm(obj=g)
        if form.validate_on_submit():
            for field in form:
                if field.name not in ('submit', 'csrf_token'):
                    try:
                        setattr(g, field.name, field.data)
                    except Exception:
                        pass
            db.session.commit()
            flash('Данные поручителя обновлены', 'success')
            return redirect(url_for('contract_detail', contract_id=g.contract_id))
        return render_template('guarantors/form.html', form=form, contract=contract, title='Редактировать поручителя')

    @app.route('/guarantors/<int:g_id>/delete', methods=['POST'])
    def guarantor_delete(g_id):
        g = db.session.get(Guarantor, g_id) or abort(404)
        cid = g.contract_id
        db.session.delete(g)
        db.session.commit()
        flash('Поручитель удалён', 'warning')
        return redirect(url_for('contract_detail', contract_id=cid))

    # ══════════════════════════════════════════════════════════════════════════
    # CONTRACTS
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/contracts')
    def contracts_list():
        q = request.args.get('q', '').strip()
        status_f = request.args.get('status', '')
        cat_f = request.args.get('category', '')

        stmt = db.select(Contract)
        if q:
            like = f'%{q}%'
            stmt = stmt.where(
                (Contract.contract_number.ilike(like)) |
                (Contract.item_name.ilike(like))
            )
        if status_f:
            stmt = stmt.where(Contract.status == status_f)
        if cat_f:
            stmt = stmt.where(Contract.item_category == cat_f)
        stmt = stmt.order_by(desc(Contract.created_at))
        contracts = db.session.execute(stmt).scalars().all()
        return render_template('contracts/list.html', contracts=contracts,
                               q=q, status_f=status_f, cat_f=cat_f,
                               item_category_choices=ITEM_CATEGORY_CHOICES)

    @app.route('/contracts/new', methods=['GET', 'POST'])
    def contract_new():
        client_id = request.args.get('client_id', type=int)
        client = db.session.get(Client, client_id) if client_id else None
        form = ContractForm()
        if request.method == 'GET':
            form.contract_date.data = date.today()
            if client_id:
                form.client_id.data = str(client_id)
        if form.validate_on_submit():
            contract = Contract(
                contract_number=generate_contract_number(),
                client_id=int(form.client_id.data),
                item_name=form.item_name.data,
                item_category=form.item_category.data,
                item_description=form.item_description.data,
                item_serial_number=form.item_serial_number.data,
                item_condition=form.item_condition.data,
                supplier_name=form.supplier_name.data,
                supplier_inn=form.supplier_inn.data,
                supplier_contract_number=form.supplier_contract_number.data,
                cost_price=form.cost_price.data,
                markup_percent=form.markup_percent.data or 0,
                total_price=form.total_price.data,
                down_payment=form.down_payment.data or 0,
                financed_amount=form.financed_amount.data,
                months=form.months.data,
                monthly_payment=form.monthly_payment.data,
                contract_date=form.contract_date.data,
                first_payment_date=form.first_payment_date.data,
                payment_day_of_month=form.payment_day_of_month.data or 5,
                payment_method=form.payment_method.data,
                is_halal=form.is_halal.data,
                halal_certificate_number=form.halal_certificate_number.data,
                sharia_board_approval=form.sharia_board_approval.data,
                sharia_board_note=form.sharia_board_note.data,
                status=form.status.data,
                notes=form.notes.data,
            )
            db.session.add(contract)
            db.session.flush()
            generate_schedule(contract)
            db.session.commit()
            flash(f'Договор {contract.contract_number} создан', 'success')
            return redirect(url_for('contract_detail', contract_id=contract.id))

        clients_all = db.session.execute(
            db.select(Client).where(Client.status == 'active').order_by(Client.last_name)
        ).scalars().all()
        return render_template('contracts/form.html', form=form, title='Новый договор',
                               contract=None, client=client, clients_all=clients_all)

    @app.route('/contracts/<int:contract_id>')
    def contract_detail(contract_id):
        contract = db.session.get(Contract, contract_id) or abort(404)
        schedule = db.session.execute(
            db.select(PaymentSchedule).where(PaymentSchedule.contract_id == contract_id)
            .order_by(asc(PaymentSchedule.installment_num))
        ).scalars().all()
        payments = db.session.execute(
            db.select(Payment).where(Payment.contract_id == contract_id)
            .order_by(desc(Payment.payment_date))
        ).scalars().all()
        guarantors = db.session.execute(
            db.select(Guarantor).where(Guarantor.contract_id == contract_id)
        ).scalars().all()
        return render_template('contracts/detail.html',
                               contract=contract, schedule=schedule,
                               payments=payments, guarantors=guarantors,
                               today=date.today())

    @app.route('/contracts/<int:contract_id>/edit', methods=['GET', 'POST'])
    def contract_edit(contract_id):
        contract = db.session.get(Contract, contract_id) or abort(404)
        form = ContractForm(obj=contract)
        if request.method == 'GET':
            form.client_id.data = str(contract.client_id)
        if form.validate_on_submit():
            contract.item_name = form.item_name.data
            contract.item_category = form.item_category.data
            contract.item_description = form.item_description.data
            contract.item_serial_number = form.item_serial_number.data
            contract.item_condition = form.item_condition.data
            contract.supplier_name = form.supplier_name.data
            contract.supplier_inn = form.supplier_inn.data
            contract.supplier_contract_number = form.supplier_contract_number.data
            contract.cost_price = form.cost_price.data
            contract.markup_percent = form.markup_percent.data or 0
            contract.total_price = form.total_price.data
            contract.down_payment = form.down_payment.data or 0
            contract.financed_amount = form.financed_amount.data
            contract.months = form.months.data
            contract.monthly_payment = form.monthly_payment.data
            contract.contract_date = form.contract_date.data
            contract.first_payment_date = form.first_payment_date.data
            contract.payment_day_of_month = form.payment_day_of_month.data or 5
            contract.payment_method = form.payment_method.data
            contract.is_halal = form.is_halal.data
            contract.halal_certificate_number = form.halal_certificate_number.data
            contract.sharia_board_approval = form.sharia_board_approval.data
            contract.sharia_board_note = form.sharia_board_note.data
            contract.status = form.status.data
            contract.notes = form.notes.data
            contract.updated_at = datetime.utcnow()
            generate_schedule(contract)
            db.session.commit()
            flash('Договор обновлён', 'success')
            return redirect(url_for('contract_detail', contract_id=contract.id))

        clients_all = db.session.execute(
            db.select(Client).order_by(Client.last_name)
        ).scalars().all()
        return render_template('contracts/form.html', form=form, title='Редактировать договор',
                               contract=contract, client=contract.client, clients_all=clients_all)

    @app.route('/contracts/<int:contract_id>/close', methods=['POST'])
    def contract_close(contract_id):
        contract = db.session.get(Contract, contract_id) or abort(404)
        contract.status = 'closed'
        contract.early_closure_date = date.today()
        contract.early_closure_reason = request.form.get('reason', 'Досрочное закрытие')
        db.session.commit()
        flash('Договор закрыт', 'success')
        return redirect(url_for('contract_detail', contract_id=contract_id))

    @app.route('/contracts/<int:contract_id>/cancel', methods=['POST'])
    def contract_cancel(contract_id):
        contract = db.session.get(Contract, contract_id) or abort(404)
        contract.status = 'cancelled'
        db.session.commit()
        flash('Договор отменён', 'warning')
        return redirect(url_for('contract_detail', contract_id=contract_id))

    # ══════════════════════════════════════════════════════════════════════════
    # PAYMENTS
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/payments')
    def payments_list():
        q = request.args.get('q', '').strip()
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        stmt = db.select(Payment).order_by(desc(Payment.payment_date))
        if q:
            stmt = stmt.join(Contract).where(
                Contract.contract_number.ilike(f'%{q}%')
            )
        if date_from:
            try:
                stmt = stmt.where(Payment.payment_date >= date.fromisoformat(date_from))
            except Exception:
                pass
        if date_to:
            try:
                stmt = stmt.where(Payment.payment_date <= date.fromisoformat(date_to))
            except Exception:
                pass
        payments = db.session.execute(stmt).scalars().all()
        return render_template('payments/list.html', payments=payments, q=q,
                               date_from=date_from, date_to=date_to)

    @app.route('/payments/new', methods=['GET', 'POST'])
    def payment_new():
        contract_id = request.args.get('contract_id', type=int) or request.form.get('contract_id', type=int)
        schedule_id = request.args.get('schedule_id', type=int)
        contract = db.session.get(Contract, contract_id) if contract_id else None

        form = PaymentForm()
        if request.method == 'GET':
            form.payment_date.data = date.today()
            if contract_id:
                form.contract_id.data = str(contract_id)
            if schedule_id:
                form.schedule_id.data = str(schedule_id)
                sched = db.session.get(PaymentSchedule, schedule_id)
                if sched:
                    form.amount.data = sched.remaining

        if form.validate_on_submit():
            cid = int(form.contract_id.data)
            sid = int(form.schedule_id.data) if form.schedule_id.data else None
            payment = Payment(
                contract_id=cid,
                schedule_id=sid,
                amount=form.amount.data,
                payment_date=form.payment_date.data,
                payment_method=form.payment_method.data,
                receipt_number=form.receipt_number.data,
                received_by=form.received_by.data,
                note=form.note.data,
            )
            db.session.add(payment)

            if sid:
                sched = db.session.get(PaymentSchedule, sid)
                if sched:
                    sched.paid_amount += form.amount.data
                    sched.paid_amount = round(sched.paid_amount, 2)
                    if sched.paid_amount >= sched.amount - 0.01:
                        sched.status = 'paid'
                        sched.paid_date = form.payment_date.data
                    else:
                        sched.status = 'partial'

            # Check if contract fully paid
            c = db.session.get(Contract, cid)
            if c:
                total_paid = db.session.execute(
                    db.select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.contract_id == cid)
                ).scalar() or 0
                total_paid += form.amount.data
                if total_paid >= c.financed_amount - 0.01:
                    c.status = 'closed'
                    c.early_closure_date = form.payment_date.data

            db.session.commit()
            flash('Платёж зарегистрирован', 'success')
            return redirect(url_for('contract_detail', contract_id=cid))

        pending_schedules = []
        if contract:
            pending_schedules = db.session.execute(
                db.select(PaymentSchedule).where(
                    PaymentSchedule.contract_id == contract_id,
                    PaymentSchedule.status.in_(['pending', 'partial', 'overdue'])
                ).order_by(asc(PaymentSchedule.due_date))
            ).scalars().all()

        return render_template('payments/form.html', form=form,
                               contract=contract, pending_schedules=pending_schedules)

    @app.route('/payments/<int:payment_id>/delete', methods=['POST'])
    def payment_delete(payment_id):
        p = db.session.get(Payment, payment_id) or abort(404)
        cid = p.contract_id
        sid = p.schedule_id
        amount = p.amount

        if sid:
            sched = db.session.get(PaymentSchedule, sid)
            if sched:
                sched.paid_amount = max(0, sched.paid_amount - amount)
                if sched.paid_amount <= 0:
                    sched.status = 'pending' if sched.due_date >= date.today() else 'overdue'
                    sched.paid_date = None
                else:
                    sched.status = 'partial'

        db.session.delete(p)
        db.session.commit()
        flash('Платёж удалён', 'warning')
        return redirect(url_for('contract_detail', contract_id=cid))

    # ══════════════════════════════════════════════════════════════════════════
    # REPORTS
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/reports')
    def reports():
        return render_template('reports.html')

    @app.route('/api/reports/monthly')
    def api_reports_monthly():
        today = date.today()
        result = []
        for i in range(11, -1, -1):
            d = today - relativedelta(months=i)
            total = db.session.execute(
                db.select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    extract('year', Payment.payment_date) == d.year,
                    extract('month', Payment.payment_date) == d.month,
                )
            ).scalar() or 0
            result.append({'month': d.strftime('%b %Y'), 'amount': float(total)})
        return jsonify(result)

    @app.route('/api/reports/stats')
    def api_reports_stats():
        statuses = ['draft', 'active', 'overdue', 'closed', 'cancelled']
        by_status = {}
        for s in statuses:
            cnt = db.session.execute(
                db.select(func.count(Contract.id)).where(Contract.status == s)
            ).scalar() or 0
            by_status[s] = cnt

        categories = ['appliances', 'electronics', 'furniture', 'auto', 'real_estate', 'education', 'medical', 'other']
        by_category = {}
        for cat in categories:
            amount = db.session.execute(
                db.select(func.coalesce(func.sum(Contract.financed_amount), 0)).where(
                    Contract.item_category == cat
                )
            ).scalar() or 0
            by_category[cat] = float(amount)

        overdue_analysis = db.session.execute(
            db.select(Contract).where(Contract.status == 'overdue').order_by(desc(Contract.created_at))
        ).scalars().all()

        overdue_data = []
        today = date.today()
        for c in overdue_analysis:
            overdue_sched = c.overdue_schedules
            if overdue_sched:
                oldest = min(s.due_date for s in overdue_sched)
                days_overdue = (today - oldest).days
                overdue_amount = sum(s.amount - s.paid_amount for s in overdue_sched)
                overdue_data.append({
                    'id': c.id,
                    'contract_number': c.contract_number,
                    'client': c.client.full_name,
                    'days_overdue': days_overdue,
                    'overdue_amount': round(overdue_amount, 2),
                })

        total_portfolio = db.session.execute(
            db.select(func.coalesce(func.sum(Contract.financed_amount), 0)).where(
                Contract.status.in_(['active', 'overdue'])
            )
        ).scalar() or 0

        total_collected = db.session.execute(
            db.select(func.coalesce(func.sum(Payment.amount), 0))
        ).scalar() or 0

        sharia_compliant = db.session.execute(
            db.select(func.count(Contract.id)).where(
                Contract.is_halal == True,
                Contract.status.in_(['active', 'overdue', 'closed'])
            )
        ).scalar() or 0
        total_contracts = db.session.execute(
            db.select(func.count(Contract.id)).where(Contract.status != 'draft')
        ).scalar() or 1

        return jsonify({
            'by_status': by_status,
            'by_category': by_category,
            'overdue_data': overdue_data,
            'total_portfolio': float(total_portfolio),
            'total_collected': float(total_collected),
            'sharia_compliance_pct': round(sharia_compliant / total_contracts * 100, 1),
        })

    # ══════════════════════════════════════════════════════════════════════════
    # BACKUPS
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/backups')
    def backups_list():
        backups = db.session.execute(
            db.select(Backup).order_by(desc(Backup.created_at))
        ).scalars().all()
        return render_template('backups.html', backups=backups)

    @app.route('/backups/create', methods=['POST'])
    def backup_create():
        note = request.form.get('note', '')
        try:
            filename = backup_module.create_backup(db, note=note)
            flash(f'Резервная копия создана: {filename}', 'success')
        except Exception as e:
            flash(f'Ошибка создания резервной копии: {e}', 'danger')
        return redirect(url_for('backups_list'))

    @app.route('/backups/<int:backup_id>/download')
    def backup_download(backup_id):
        b = db.session.get(Backup, backup_id) or abort(404)
        filepath = os.path.join(os.path.dirname(__file__), 'backups', b.filename)
        if not os.path.exists(filepath):
            abort(404)
        return send_file(filepath, as_attachment=True, download_name=b.filename)

    @app.route('/backups/<int:backup_id>/restore', methods=['POST'])
    def backup_restore(backup_id):
        b = db.session.get(Backup, backup_id) or abort(404)
        try:
            backup_module.restore_backup(b.filename, db)
            flash(f'База данных восстановлена из {b.filename}', 'success')
        except Exception as e:
            flash(f'Ошибка восстановления: {e}', 'danger')
        return redirect(url_for('backups_list'))

    @app.route('/backups/<int:backup_id>/delete', methods=['POST'])
    def backup_delete(backup_id):
        b = db.session.get(Backup, backup_id) or abort(404)
        filepath = os.path.join(os.path.dirname(__file__), 'backups', b.filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        db.session.delete(b)
        db.session.commit()
        flash('Резервная копия удалена', 'warning')
        return redirect(url_for('backups_list'))

    # ══════════════════════════════════════════════════════════════════════════
    # SEED DATA
    # ══════════════════════════════════════════════════════════════════════════

    def seed_demo_data():
        if db.session.execute(db.select(func.count(Client.id))).scalar() > 0:
            return

        c1 = Client(
            last_name='Алиев', first_name='Руслан', middle_name='Магомедович',
            birth_date=date(1985, 3, 15), gender='male', citizenship='Россия',
            passport_series='2214', passport_number='345678',
            passport_issued_by='УФМС России по г. Москве', passport_issued_date=date(2015, 6, 1),
            inn='7720123456', snils='123-456-789 01',
            phone='+7-905-123-45-67', email='alieff@example.com',
            address_registration='г. Москва, ул. Ленина, д. 10, кв. 5',
            address_actual='г. Москва, ул. Садовая, д. 3, кв. 12',
            employer_name='ООО "РосТехник"', position='Инженер',
            employment_type='employed', work_experience_months=60,
            monthly_income=85000, income_confirmed=True,
            marital_status='married', children_count=2,
            education='university', own_property=True, own_car=True,
            credit_history_status='good', credit_score=750, status='active',
        )

        c2 = Client(
            last_name='Мусаева', first_name='Заира', middle_name='Исмаиловна',
            birth_date=date(1990, 7, 22), gender='female', citizenship='Россия',
            passport_series='0512', passport_number='987654',
            passport_issued_by='УФМС России по Республике Дагестан',
            passport_issued_date=date(2018, 9, 10),
            inn='0501234567', phone='+7-928-456-78-90',
            address_registration='г. Махачкала, ул. Гагарина, д. 25, кв. 8',
            address_actual='г. Махачкала, ул. Гагарина, д. 25, кв. 8',
            employer_name='ИП Мусаева З.И.', position='Предприниматель',
            employment_type='self_employed', work_experience_months=36,
            monthly_income=55000, income_confirmed=False,
            marital_status='married', children_count=1,
            education='college', credit_history_status='satisfactory',
            credit_score=580, status='active',
        )

        c3 = Client(
            last_name='Хасанов', first_name='Тимур', middle_name='Рустамович',
            birth_date=date(1978, 11, 5), gender='male', citizenship='Россия',
            passport_series='0308', passport_number='112233',
            passport_issued_by='ОВД г. Казани', passport_issued_date=date(2010, 4, 20),
            inn='1650123456', phone='+7-917-789-01-23',
            address_registration='г. Казань, ул. Баумана, д. 15, кв. 22',
            address_actual='г. Казань, ул. Баумана, д. 15, кв. 22',
            employer_name='АО "КазТрансСтрой"', position='Директор',
            employment_type='business_owner', work_experience_months=120,
            monthly_income=150000, income_confirmed=True,
            marital_status='married', children_count=3,
            education='university', own_property=True, own_car=True,
            credit_history_status='good', credit_score=820, status='active',
        )

        db.session.add_all([c1, c2, c3])
        db.session.flush()

        # Contract 1 – active
        today = date.today()
        con1 = Contract(
            contract_number='МУР-2024-001',
            client_id=c1.id,
            item_name='Холодильник Samsung RF65A967FSR',
            item_category='appliances',
            item_condition='new',
            supplier_name='М.Видео', supplier_inn='7812345678',
            cost_price=85000, markup_percent=15.0, total_price=97750,
            down_payment=10000, financed_amount=87750,
            months=12, monthly_payment=7312.5,
            contract_date=today - timedelta(days=90),
            first_payment_date=today - timedelta(days=60),
            payment_day_of_month=5, payment_method='cash',
            is_halal=True, sharia_board_approval=True,
            status='active',
        )

        # Contract 2 – overdue
        con2 = Contract(
            contract_number='МУР-2024-002',
            client_id=c2.id,
            item_name='Ноутбук ASUS VivoBook 15',
            item_category='electronics',
            item_condition='new',
            supplier_name='DNS', supplier_inn='2509987654',
            cost_price=55000, markup_percent=10.0, total_price=60500,
            down_payment=5000, financed_amount=55500,
            months=6, monthly_payment=9250,
            contract_date=today - timedelta(days=180),
            first_payment_date=today - timedelta(days=150),
            payment_day_of_month=10, payment_method='bank_transfer',
            is_halal=True, sharia_board_approval=True,
            status='active',
        )

        # Contract 3 – draft
        con3 = Contract(
            contract_number='МУР-2024-003',
            client_id=c3.id,
            item_name='Автомобиль Toyota Camry 2023',
            item_category='auto',
            item_condition='new',
            supplier_name='Тойота-Казань', supplier_inn='1650543210',
            cost_price=2500000, markup_percent=12.0, total_price=2800000,
            down_payment=500000, financed_amount=2300000,
            months=36, monthly_payment=63888.89,
            contract_date=today,
            first_payment_date=today + timedelta(days=30),
            payment_day_of_month=15, payment_method='bank_transfer',
            is_halal=True, sharia_board_approval=False,
            status='draft',
        )

        db.session.add_all([con1, con2, con3])
        db.session.flush()

        # Generate schedules
        generate_schedule(con1)
        generate_schedule(con2)
        generate_schedule(con3)

        # Add some payments for contract 1
        sched1 = db.session.execute(
            db.select(PaymentSchedule).where(
                PaymentSchedule.contract_id == con1.id,
                PaymentSchedule.installment_num == 1
            )
        ).scalar_one_or_none()
        if sched1:
            p1 = Payment(
                contract_id=con1.id, schedule_id=sched1.id,
                amount=7312.5, payment_date=sched1.due_date,
                payment_method='cash', receipt_number='ЧЕК-001',
                received_by='Администратор',
            )
            sched1.paid_amount = 7312.5
            sched1.status = 'paid'
            sched1.paid_date = sched1.due_date
            db.session.add(p1)

        # Guarantor for contract 1
        g1 = Guarantor(
            contract_id=con1.id,
            last_name='Алиев', first_name='Магомед', middle_name='Алиевич',
            phone='+7-905-000-11-22', relationship='parent',
            passport_series='2210', passport_number='654321',
            passport_issued_by='УФМС г. Москвы',
            passport_issued_date=date(2010, 1, 1),
            address_registration='г. Москва, ул. Ленина, д. 10, кв. 3',
            employer_name='Пенсионер', monthly_income=25000,
            guarantor_type='personal',
        )
        db.session.add(g1)
        db.session.commit()

    # Init DB
    with app.app_context():
        db.create_all()
        try:
            from dateutil.relativedelta import relativedelta as _r
            seed_demo_data()
        except Exception as e:
            print(f'Seed error: {e}')

    return app


# For direct run / import
app = create_app()
