"""Tests for per-user vehicles and backward-compatible invoice linkage."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.database.migrations.add_vehicles import migrate
from web.database.models import Base, Invoice, User, Vehicle
from web.routers.invoices import update_invoice
from web.routers.vehicles import create_vehicle, list_vehicles, update_vehicle
from web.schemas.invoices import InvoiceUpdate
from web.schemas.vehicles import VehicleCreate, VehicleUpdate


class VehicleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(google_sub="vehicle-owner", email="owner@example.com")
        self.other_user = User(google_sub="other-owner", email="other@example.com")
        self.db.add_all([self.user, self.other_user])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.other_user)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_create_list_and_deactivate_vehicle(self):
        vehicle = create_vehicle(
            VehicleCreate(name="  Toyota Corolla  ", registration="ke-885-hh"),
            user=self.user,
            db=self.db,
        )

        self.assertEqual(vehicle.name, "Toyota Corolla")
        self.assertEqual(vehicle.registration, "KE885HH")
        self.assertEqual(list_vehicles(True, self.user, self.db), [vehicle])

        updated = update_vehicle(
            vehicle.id,
            VehicleUpdate(is_active=False),
            user=self.user,
            db=self.db,
        )
        self.assertFalse(updated.is_active)
        self.assertEqual(list_vehicles(True, self.user, self.db), [])
        self.assertEqual(list_vehicles(False, self.user, self.db), [vehicle])

    def test_vehicle_is_scoped_to_its_owner(self):
        vehicle = create_vehicle(
            VehicleCreate(name="Toyota", registration="KE885HH"),
            user=self.user,
            db=self.db,
        )

        with self.assertRaises(HTTPException) as raised:
            update_vehicle(
                vehicle.id,
                VehicleUpdate(name="Not mine"),
                user=self.other_user,
                db=self.db,
            )

        self.assertEqual(raised.exception.status_code, 404)

    def test_invoice_keeps_historical_registration_after_vehicle_changes(self):
        vehicle = create_vehicle(
            VehicleCreate(name="Toyota", registration="KE885HH"),
            user=self.user,
            db=self.db,
        )
        invoice = Invoice(
            user_id=self.user.id,
            filename="2026-08-01-001_card_omv_KE885HH.pdf",
            vehicle_id=vehicle.id,
            vehicle_registration="KE885HH",
            is_vehicle_expense=True,
        )
        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)

        update_vehicle(
            vehicle.id,
            VehicleUpdate(registration="BA123CD"),
            user=self.user,
            db=self.db,
        )
        result = update_invoice(
            invoice.id,
            InvoiceUpdate(vehicle_id=vehicle.id, comment="Metadata edit"),
            user=self.user,
            db=self.db,
        )

        self.assertEqual(result.vehicle_registration, "KE885HH")
        self.assertEqual(result.filename, "2026-08-01-001_card_omv_KE885HH.pdf")


class VehicleMigrationTests(unittest.TestCase):
    def test_existing_registrations_are_backfilled_and_linked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "legacy.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
            conn.execute(
                """
                CREATE TABLE invoices (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    vehicle_registration VARCHAR(16)
                )
                """
            )
            conn.execute("INSERT INTO users (id) VALUES (1)")
            conn.execute(
                "INSERT INTO invoices (id, user_id, vehicle_registration) VALUES (1, 1, 'KE885HH')"
            )
            conn.commit()
            conn.close()

            self.assertTrue(migrate(db_path))

            conn = sqlite3.connect(db_path)
            vehicle = conn.execute(
                "SELECT id, name, registration, is_active FROM vehicles"
            ).fetchone()
            invoice_vehicle_id = conn.execute(
                "SELECT vehicle_id FROM invoices WHERE id = 1"
            ).fetchone()[0]
            conn.close()

            self.assertEqual(vehicle[1:], ("KE885HH", "KE885HH", 1))
            self.assertEqual(invoice_vehicle_id, vehicle[0])


if __name__ == "__main__":
    unittest.main()
