from gevent import monkey
monkey.patch_all(subprocess=False)
from backend.app import app, socketio
app = app
