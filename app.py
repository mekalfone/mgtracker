from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import json
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# In production, set cors_allowed_origins to your domain
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

# Store user paths and markers (in production, use a database)
user_paths = {}
user_markers = {}
connected_users = set()

# Main page route
@app.route('/')
def index():
    return render_template('index.html')

# Health check route
@app.route('/health')
def health():
    return {'status': 'healthy', 'active_users': len(connected_users)}

# Handle client connection
@socketio.on('connect')
def handle_connect():
    logger.info('Client connected: %s', request.sid)
    try:
        connected_users.add(request.sid)
        emit('user_id', request.sid)
    except Exception as e:
        logger.error('Error in handle_connect: %s', e)

# Handle client disconnection
@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected: %s', request.sid)
    user_id = request.sid
    try:
        connected_users.discard(user_id)
        if user_id in user_paths:
            del user_paths[user_id]
        if user_id in user_markers:
            del user_markers[user_id]
        emit('user_disconnected', user_id, broadcast=True)
    except Exception as e:
        logger.error('Error in handle_disconnect: %s', e)

# Handle location updates from clients
@socketio.on('location_update')
def handle_location_update(data):
    user_id = request.sid
    try:
        lat = data['lat']
        lng = data['lng']
        logger.debug('Location update from %s: %s, %s', user_id, lat, lng)
        
        if user_id not in user_paths:
            user_paths[user_id] = []
        user_paths[user_id].append([lat, lng])
        
        # Keep only last 100 points for performance
        if len(user_paths[user_id]) > 100:
            user_paths[user_id].pop(0)
        
        emit('update_user_path', {'user_id': user_id, 'path': user_paths[user_id]}, broadcast=True)
    except KeyError as e:
        logger.error('Missing key in location_update data: %s', e)
    except Exception as e:
        logger.error('Error in handle_location_update: %s', e)

if __name__ == '__main__':
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    logger.info('Starting server on %s:%s, debug=%s', host, port, debug)
    socketio.run(app, host=host, port=port, debug=debug)