"""Start a disposable synthetic-data server for browser tests; never production."""
import tempfile
from pathlib import Path

import uvicorn
from sqlalchemy.orm import Session

from claire.config import Settings
from claire.db import Base, Family, User
from claire.identity import passwords
from claire.main import create_app

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="claire-smoke-") as temporary:
        app = create_app(Settings(database_url=f"sqlite:///{Path(temporary) / 'smoke.db'}",
                                  origin="http://127.0.0.1:8000", secure_cookies=False,
                                  static_dir=Path("apps/frontend/dist").resolve()))
        Base.metadata.create_all(app.state.engine)
        with Session(app.state.engine) as db:
            family = Family(name="Example family")
            db.add(family)
            db.flush()
            db.add(User(email="alice@example.test", family_id=family.id,
                        password_hash=passwords.hash("synthetic-browser-password"), role="member"))
            db.commit()
        uvicorn.run(app, host="127.0.0.1", port=8000, access_log=False)
