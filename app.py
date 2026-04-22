import os
import json
import uuid
import logging
import threading
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')

socketio = SocketIO(app, cors_allowed_origins="*",
                    logger=False, engineio_logger=False)

TRIPS_FILE = os.path.join(os.path.dirname(__file__), 'trips.json')

DEFAULT_TRIPS = [
    {
        "id": "nsam-ekounou",
        "name": "Nsam → Carrefour Ekounou",
        "color": "#e74c3c",
        "waypoints": [
            [3.8373, 11.5082],
            [3.8348, 11.5098],
            [3.8320, 11.5128],
            [3.8292, 11.5158],
            [3.8258, 11.5185],
            [3.8228, 11.5212],
            [3.8198, 11.5238]
        ]
    },
    {
        "id": "citeu-mendong",
        "name": "Cité U → Mendong",
        "color": "#3498db",
        "waypoints": [
            [3.8682, 11.5178],
            [3.8635, 11.5132],
            [3.8582, 11.5075],
            [3.8522, 11.4998],
            [3.8462, 11.4918],
            [3.8405, 11.4848],
            [3.8358, 11.4782],
            [3.8318, 11.4728]
        ]
    }
]


def load_trips():
    if os.path.exists(TRIPS_FILE):
        try:
            with open(TRIPS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error('Error loading trips: %s', e)
    data = [t.copy() for t in DEFAULT_TRIPS]
    save_trips(data)
    return data


def save_trips(trips_data):
    try:
        with open(TRIPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(trips_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error('Error saving trips: %s', e)


trips = load_trips()
active_users = {}        # {sid: {id, username, trip_id, lat, lng}}
_users_lock = threading.Lock()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'active_users': len(active_users)})


@app.route('/api/trips', methods=['GET'])
def get_trips():
    return jsonify(trips)


@app.route('/api/trips', methods=['POST'])
def create_trip():
    data = request.get_json()
    if not data or not data.get('name', '').strip():
        return jsonify({'error': 'Name is required'}), 400
    trip = {
        'id': str(uuid.uuid4()),
        'name': data['name'].strip(),
        'color': data.get('color', '#9b59b6'),
        'waypoints': data.get('waypoints', [])
    }
    trips.append(trip)
    save_trips(trips)
    socketio.emit('trips_updated', trips)
    return jsonify(trip), 201


@app.route('/api/trips/<trip_id>', methods=['PUT'])
def update_trip(trip_id):
    data = request.get_json()
    for i, trip in enumerate(trips):
        if trip['id'] == trip_id:
            trips[i] = {
                'id': trip_id,
                'name': data.get('name', trip['name']).strip(),
                'color': data.get('color', trip['color']),
                'waypoints': data.get('waypoints', trip['waypoints'])
            }
            save_trips(trips)
            socketio.emit('trips_updated', trips)
            return jsonify(trips[i])
    return jsonify({'error': 'Trip not found'}), 404


@app.route('/api/trips/<trip_id>', methods=['DELETE'])
def delete_trip(trip_id):
    global trips
    before = len(trips)
    trips = [t for t in trips if t['id'] != trip_id]
    if len(trips) == before:
        return jsonify({'error': 'Trip not found'}), 404
    save_trips(trips)
    socketio.emit('trips_updated', trips)
    return '', 204


def _snapshot():
    with _users_lock:
        return list(active_users.values())


@socketio.on('connect')
def on_connect():
    logger.info('Client connected: %s', request.sid)
    emit('user_id', {'id': request.sid})
    emit('trips_updated', trips)
    emit('users_updated', _snapshot())


@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    changed = False
    with _users_lock:
        if sid in active_users:
            del active_users[sid]
            changed = True
    if changed:
        emit('users_updated', _snapshot(), broadcast=True)
    logger.info('Client disconnected: %s', sid)


@socketio.on('join_trip')
def on_join_trip(data):
    sid = request.sid
    with _users_lock:
        active_users[sid] = {
            'id': sid,
            'username': str(data.get('username', 'Anonymous'))[:30],
            'trip_id': data.get('trip_id'),
            'lat': active_users.get(sid, {}).get('lat'),   # keep last known pos on rejoin
            'lng': active_users.get(sid, {}).get('lng'),
        }
    emit('users_updated', _snapshot(), broadcast=True)


@socketio.on('location_update')
def on_location_update(data):
    sid = request.sid
    with _users_lock:
        if sid not in active_users:
            return
        try:
            active_users[sid]['lat'] = float(data['lat'])
            active_users[sid]['lng'] = float(data['lng'])
        except (KeyError, ValueError, TypeError) as e:
            logger.error('Invalid location data from %s: %s', sid, e)
            return
    emit('users_updated', _snapshot(), broadcast=True)


if __name__ == '__main__':
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    logger.info('Starting on %s:%s debug=%s', host, port, debug)
    socketio.run(app, host=host, port=port, debug=debug)
