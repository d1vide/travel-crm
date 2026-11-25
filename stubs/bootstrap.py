import uvicorn

from stubs.migrate import upgrade
from stubs.store import Settings

if __name__ == "__main__":
    upgrade(Settings())
    uvicorn.run("stubs.main:create_app", factory=True, host="0.0.0.0", port=8010, access_log=False)
