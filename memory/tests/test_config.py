"""DSN-будівник Memory."""
from app.config import Settings


def test_dsn_built_from_parts():
    s = Settings()
    s.postgres_user = "u"
    s.postgres_password = "p"
    s.postgres_host = "h"
    s.postgres_port = 1234
    s.postgres_db = "d"
    assert s.dsn == "postgresql://u:p@h:1234/d"
