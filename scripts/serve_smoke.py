"""Start a disposable synthetic-data server for browser tests; never production."""
import argparse
import tempfile
from pathlib import Path

import uvicorn
from claire.config import Settings
from claire.db import Base, Family, User
from claire.identity import passwords
from claire.main import create_app
from sqlalchemy.orm import Session

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8010)
    port = parser.parse_args().port
    with tempfile.TemporaryDirectory(prefix="claire-smoke-") as temporary:
        app = create_app(Settings(database_url=f"sqlite:///{Path(temporary) / 'smoke.db'}",
                                  origin=f"http://127.0.0.1:{port}", secure_cookies=False,
                                  static_dir=Path("apps/frontend/dist").resolve(),
                                  data_dir=Path(temporary) / "archive"))
        Base.metadata.create_all(app.state.engine)
        with Session(app.state.engine) as db:
            family = Family(name="Example family")
            db.add(family)
            db.flush()
            db.add(User(email="alice@example.test", family_id=family.id,
                        password_hash=passwords.hash("synthetic-browser-password"), role="member"))
            db.add(User(email="admin@example.test", family_id=family.id,
                        password_hash=passwords.hash("synthetic-browser-password"), role="family_admin"))
            db.commit()
        uvicorn.run(app, host="127.0.0.1", port=port, access_log=False)
