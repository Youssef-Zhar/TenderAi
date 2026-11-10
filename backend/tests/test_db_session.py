
from unittest.mock import MagicMock, patch

from app.db import session as db_session


def test_get_db_yields_session_and_closes_it():
    fake_db = MagicMock()

    with patch.object(db_session, "SessionLocal", return_value=fake_db) as factory:
        db_generator = db_session.get_db()

        yielded_db = next(db_generator)

        assert yielded_db is fake_db
        factory.assert_called_once_with()
        fake_db.close.assert_not_called()

        try:
            next(db_generator)
        except StopIteration:
            pass

        fake_db.close.assert_called_once_with()

def test_get_db_closes_session_when_exception_occurs():
    fake_db = MagicMock()

    with patch.object(db_session, "SessionLocal", return_value=fake_db):
        db_generator = db_session.get_db()

        yielded_db = next(db_generator)
        assert yielded_db is fake_db

        try:
            db_generator.throw(RuntimeError("Database operation failed"))
        except RuntimeError as exc:
            assert str(exc) == "Database operation failed"

        fake_db.close.assert_called_once_with()
