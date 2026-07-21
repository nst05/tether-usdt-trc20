"""Наполнение демо-данными: python seed.py"""
import random
from datetime import datetime, timedelta

try:
    from .app import create_app
    from .models import db, Client, Courier, Shipment, ShipmentEvent, SHIPMENT_STATUS_FLOW
except ImportError:
    from app import create_app
    from models import db, Client, Courier, Shipment, ShipmentEvent, SHIPMENT_STATUS_FLOW


def run():
    app = create_app()
    with app.app_context():
        if db.session.scalar(db.select(db.func.count(Shipment.id))):
            print('База уже содержит данные — пропускаю сидинг.')
            return

        couriers = [
            Courier(first_name='Иван', last_name='Петров', phone='+7 900 111-22-33',
                    vehicle_type='car', vehicle_number='А123ВС77', zone='Центр', status='active'),
            Courier(first_name='Алексей', last_name='Смирнов', phone='+7 900 222-33-44',
                    vehicle_type='scooter', vehicle_number='7712АА', zone='Север', status='on_delivery'),
            Courier(first_name='Дмитрий', last_name='Козлов', phone='+7 900 333-44-55',
                    vehicle_type='van', vehicle_number='В456ЕК77', zone='Юг', status='active'),
        ]
        db.session.add_all(couriers)

        clients = [
            Client(name='ООО «Маркет Плюс»', client_type='business',
                   contact_person='Ольга Иванова', phone='+7 495 100-20-30',
                   email='order@marketplus.ru', address='Москва, ул. Ленина, 10'),
            Client(name='Сергей Николаев', client_type='individual',
                   phone='+7 916 555-66-77'),
        ]
        db.session.add_all(clients)
        db.session.flush()

        recipients = [
            ('Мария Соколова', '+7 903 111-00-11', 'Москва, ул. Тверская, 15, кв. 42'),
            ('Андрей Волков', '+7 903 222-00-22', 'Москва, Ленинский пр-т, 90, кв. 7'),
            ('Елена Морозова', '+7 903 333-00-33', 'Москва, ул. Арбат, 25, кв. 3'),
            ('Павел Лебедев', '+7 903 444-00-44', 'Москва, ул. Мясницкая, 8, оф. 501'),
            ('Наталья Орлова', '+7 903 555-00-55', 'Москва, Кутузовский пр-т, 12, кв. 88'),
        ]
        services = ['standard', 'express', 'same_day']
        statuses = ['created', 'picked_up', 'in_transit', 'out_for_delivery', 'delivered']

        year = datetime.utcnow().year
        for i in range(1, 13):
            name, phone, addr = random.choice(recipients)
            client = random.choice(clients)
            status = random.choice(statuses)
            courier = random.choice(couriers) if status != 'created' else None
            s = Shipment(
                tracking_number=f'VEH-{year}-{100000 + i}',
                client_id=client.id,
                courier_id=courier.id if courier else None,
                sender_name=client.name,
                sender_phone=client.phone,
                sender_address=client.address or 'Москва, склад веho',
                recipient_name=name, recipient_phone=phone, recipient_address=addr,
                description=random.choice(['Документы', 'Одежда', 'Электроника', 'Книги', 'Косметика']),
                weight_kg=round(random.uniform(0.3, 8.0), 1),
                dimensions=f'{random.randint(15,50)}x{random.randint(15,40)}x{random.randint(5,30)} см',
                service_type=random.choice(services),
                price=random.choice([250, 350, 450, 600, 800]),
                cod_amount=random.choice([0, 0, 1500, 3200, 5000]),
                status=status,
                created_at=datetime.utcnow() - timedelta(days=random.randint(0, 20)),
            )
            if status == 'delivered':
                s.delivered_at = datetime.utcnow() - timedelta(hours=random.randint(1, 48))
            db.session.add(s)
            db.session.flush()

            # события истории до текущего статуса
            flow_idx = SHIPMENT_STATUS_FLOW.index(status) if status in SHIPMENT_STATUS_FLOW else 0
            base = s.created_at
            for j, st in enumerate(SHIPMENT_STATUS_FLOW[:flow_idx + 1]):
                db.session.add(ShipmentEvent(
                    shipment_id=s.id, status=st,
                    timestamp=base + timedelta(hours=j * 6),
                    location=random.choice(['Сортировочный центр', 'Склад Москва-Юг', 'В пути', None]),
                ))

        db.session.commit()
        print(f'Готово: {len(couriers)} курьеров, {len(clients)} клиентов, 12 отправлений.')


if __name__ == '__main__':
    run()
