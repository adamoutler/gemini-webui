from flask_socketio import SocketIO
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect

socketio = SocketIO(async_mode="eventlet")
csrf = CSRFProtect()
talisman = Talisman()
