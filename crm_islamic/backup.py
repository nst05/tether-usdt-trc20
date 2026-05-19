import json
import os
from datetime import datetime, date


def _get_backup_dir():
    """Папка резервных копий: рядом с БД (или рядом с .py в dev-режиме)."""
    base = os.environ.get('CRM_DB_DIR', os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(base, 'backups')
    os.makedirs(d, exist_ok=True)
    return d


def _serialize(obj):
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    return str(obj)


def create_backup(db, note=""):
    from .models import Client, Guarantor, Contract, PaymentSchedule, Payment, Backup

    backup_dir = _get_backup_dir()
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f'backup_{timestamp}.json'
    filepath = os.path.join(backup_dir, filename)

    def row_to_dict(row):
        d = {}
        for c in row.__table__.columns:
            val = getattr(row, c.name)
            if isinstance(val, (datetime, date)):
                val = val.isoformat()
            d[c.name] = val
        return d

    data = {
        'created_at': datetime.utcnow().isoformat(),
        'version': '1.0',
        'clients': [row_to_dict(r) for r in db.session.execute(db.select(Client)).scalars()],
        'guarantors': [row_to_dict(r) for r in db.session.execute(db.select(Guarantor)).scalars()],
        'contracts': [row_to_dict(r) for r in db.session.execute(db.select(Contract)).scalars()],
        'payment_schedules': [row_to_dict(r) for r in db.session.execute(db.select(PaymentSchedule)).scalars()],
        'payments': [row_to_dict(r) for r in db.session.execute(db.select(Payment)).scalars()],
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=_serialize)

    size_kb = os.path.getsize(filepath) / 1024.0

    backup_rec = Backup(
        filename=filename,
        file_size_kb=round(size_kb, 2),
        backup_type='manual',
        notes=note,
    )
    db.session.add(backup_rec)
    db.session.commit()
    return filename


def restore_backup(filename, db):
    from .models import Client, Guarantor, Contract, PaymentSchedule, Payment, Backup

    backup_dir = _get_backup_dir()
    filepath = os.path.join(backup_dir, filename)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f'Backup file not found: {filename}')

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    db.session.execute(db.delete(Payment))
    db.session.execute(db.delete(PaymentSchedule))
    db.session.execute(db.delete(Guarantor))
    db.session.execute(db.delete(Contract))
    db.session.execute(db.delete(Client))
    db.session.commit()

    def parse_date(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s).date() if 'T' in s else date.fromisoformat(s)
        except Exception:
            return None

    def parse_dt(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return None

    for row in data.get('clients', []):
        obj = Client(
            id=row['id'],
            created_at=parse_dt(row.get('created_at')),
            updated_at=parse_dt(row.get('updated_at')),
            status=row.get('status', 'active'),
            last_name=row.get('last_name', ''),
            first_name=row.get('first_name', ''),
            middle_name=row.get('middle_name'),
            birth_date=parse_date(row.get('birth_date')),
            birth_place=row.get('birth_place'),
            nationality=row.get('nationality'),
            citizenship=row.get('citizenship'),
            gender=row.get('gender'),
            passport_series=row.get('passport_series'),
            passport_number=row.get('passport_number'),
            passport_issued_by=row.get('passport_issued_by'),
            passport_issued_date=parse_date(row.get('passport_issued_date')),
            passport_expires_date=parse_date(row.get('passport_expires_date')),
            inn=row.get('inn'),
            snils=row.get('snils'),
            phone=row.get('phone'),
            phone2=row.get('phone2'),
            email=row.get('email'),
            address_registration=row.get('address_registration'),
            address_actual=row.get('address_actual'),
            employer_name=row.get('employer_name'),
            employer_address=row.get('employer_address'),
            employer_phone=row.get('employer_phone'),
            position=row.get('position'),
            employment_type=row.get('employment_type'),
            work_experience_months=row.get('work_experience_months'),
            monthly_income=row.get('monthly_income', 0),
            additional_income=row.get('additional_income', 0),
            income_confirmed=row.get('income_confirmed', False),
            marital_status=row.get('marital_status'),
            children_count=row.get('children_count', 0),
            dependents_count=row.get('dependents_count', 0),
            education=row.get('education'),
            own_property=row.get('own_property', False),
            own_car=row.get('own_car', False),
            credit_history_status=row.get('credit_history_status', 'none'),
            credit_score=row.get('credit_score', 0),
            blacklisted=row.get('blacklisted', False),
            blacklist_reason=row.get('blacklist_reason'),
            notes=row.get('notes'),
            photo_path=row.get('photo_path'),
        )
        db.session.add(obj)

    db.session.flush()

    for row in data.get('contracts', []):
        obj = Contract(
            id=row['id'],
            contract_number=row.get('contract_number'),
            client_id=row['client_id'],
            item_name=row.get('item_name', ''),
            item_category=row.get('item_category'),
            item_description=row.get('item_description'),
            item_serial_number=row.get('item_serial_number'),
            item_condition=row.get('item_condition', 'new'),
            supplier_name=row.get('supplier_name'),
            supplier_inn=row.get('supplier_inn'),
            supplier_contract_number=row.get('supplier_contract_number'),
            cost_price=row.get('cost_price', 0),
            markup_percent=row.get('markup_percent', 0),
            total_price=row.get('total_price', 0),
            down_payment=row.get('down_payment', 0),
            financed_amount=row.get('financed_amount', 0),
            months=row.get('months', 12),
            monthly_payment=row.get('monthly_payment', 0),
            contract_date=parse_date(row.get('contract_date')),
            first_payment_date=parse_date(row.get('first_payment_date')),
            last_payment_date=parse_date(row.get('last_payment_date')),
            payment_day_of_month=row.get('payment_day_of_month', 5),
            payment_method=row.get('payment_method', 'cash'),
            is_halal=row.get('is_halal', True),
            halal_certificate_number=row.get('halal_certificate_number'),
            sharia_board_approval=row.get('sharia_board_approval', False),
            sharia_board_note=row.get('sharia_board_note'),
            status=row.get('status', 'active'),
            early_closure_date=parse_date(row.get('early_closure_date')),
            early_closure_reason=row.get('early_closure_reason'),
            notes=row.get('notes'),
            created_at=parse_dt(row.get('created_at')),
            updated_at=parse_dt(row.get('updated_at')),
        )
        db.session.add(obj)

    db.session.flush()

    for row in data.get('guarantors', []):
        obj = Guarantor(
            id=row['id'],
            client_id=row.get('client_id'),
            contract_id=row['contract_id'],
            relationship=row.get('relationship'),
            guarantor_type=row.get('guarantor_type', 'personal'),
            property_description=row.get('property_description'),
            last_name=row.get('last_name', ''),
            first_name=row.get('first_name', ''),
            middle_name=row.get('middle_name'),
            phone=row.get('phone'),
            passport_series=row.get('passport_series'),
            passport_number=row.get('passport_number'),
            passport_issued_by=row.get('passport_issued_by'),
            passport_issued_date=parse_date(row.get('passport_issued_date')),
            address_registration=row.get('address_registration'),
            employer_name=row.get('employer_name'),
            monthly_income=row.get('monthly_income', 0),
            notes=row.get('notes'),
        )
        db.session.add(obj)

    db.session.flush()

    for row in data.get('payment_schedules', []):
        obj = PaymentSchedule(
            id=row['id'],
            contract_id=row['contract_id'],
            installment_num=row.get('installment_num'),
            due_date=parse_date(row.get('due_date')),
            amount=row.get('amount', 0),
            status=row.get('status', 'pending'),
            paid_amount=row.get('paid_amount', 0),
            paid_date=parse_date(row.get('paid_date')),
        )
        db.session.add(obj)

    db.session.flush()

    for row in data.get('payments', []):
        obj = Payment(
            id=row['id'],
            contract_id=row['contract_id'],
            schedule_id=row.get('schedule_id'),
            amount=row.get('amount', 0),
            payment_date=parse_date(row.get('payment_date')),
            payment_method=row.get('payment_method', 'cash'),
            receipt_number=row.get('receipt_number'),
            received_by=row.get('received_by'),
            note=row.get('note'),
            created_at=parse_dt(row.get('created_at')),
        )
        db.session.add(obj)

    db.session.commit()
    return True


def get_backup_list():
    backup_dir = _get_backup_dir()
    files = []
    for fn in sorted(os.listdir(backup_dir), reverse=True):
        if fn.endswith('.json') and fn.startswith('backup_'):
            fp = os.path.join(backup_dir, fn)
            files.append({
                'filename': fn,
                'size_kb': round(os.path.getsize(fp) / 1024, 2),
                'modified': datetime.fromtimestamp(os.path.getmtime(fp)),
            })
    return files
