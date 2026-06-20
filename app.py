import os
import json
import uuid
import time
import logging
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')

socketio = SocketIO(app, cors_allowed_origins="*", logger=False, engineio_logger=False)

TRIPS_FILE        = os.path.join(os.path.dirname(__file__), 'trips.json')
RESERVATIONS_FILE = os.path.join(os.path.dirname(__file__), 'reservations.json')

DEFAULT_TRIPS = [
    {
        "id": "nsam-ekounou",
        "name": "Nsam → Carrefour Ekounou",
        "color": "#e74c3c",
        "waypoints": [
            [3.8373, 11.5082], [3.8348, 11.5098], [3.8320, 11.5128],
            [3.8292, 11.5158], [3.8258, 11.5185], [3.8228, 11.5212], [3.8198, 11.5238]
        ],
        "stops": [], "matricule": None
    },
    {
        "id": "citeu-mendong",
        "name": "Cité U → Mendong",
        "color": "#3498db",
        "waypoints": [
            [3.8682, 11.5178], [3.8635, 11.5132], [3.8582, 11.5075],
            [3.8522, 11.4998], [3.8462, 11.4918], [3.8405, 11.4848],
            [3.8358, 11.4782], [3.8318, 11.4728]
        ],
        "stops": [], "matricule": None
    }
]


# ── Data helpers ──────────────────────────────────────────────

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error('Error loading %s: %s', path, e)
    return default() if callable(default) else default


def save_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error('Error saving %s: %s', path, e)


def load_trips():
    data = load_json(TRIPS_FILE, None)
    if data is None:
        data = [dict(t) for t in DEFAULT_TRIPS]
        save_json(TRIPS_FILE, data)
    else:
        for t in data:
            t.setdefault('stops', [])
            t.setdefault('matricule', None)
    return data


trips        = load_trips()
reservations = load_json(RESERVATIONS_FILE, list)
bus_positions = {}   # {trip_id: {lat, lng, matricule, timestamp}}


# ── Pages ─────────────────────────────────────────────────────

def no_cache_response(template):
    resp = app.make_response(render_template(template))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/')
def index():
    return no_cache_response('index.html')


@app.route('/admin')
def admin_page():
    return no_cache_response('admin.html')


@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'active_buses': len(bus_positions),
        'pending_reservations': sum(1 for r in reservations if r.get('status') == 'pending')
    })


# ── Trip API ──────────────────────────────────────────────────

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
        'waypoints': data.get('waypoints', []),
        'stops': data.get('stops', []),
        'matricule': None
    }
    trips.append(trip)
    save_json(TRIPS_FILE, trips)
    socketio.emit('trips_updated', trips)
    return jsonify(trip), 201


@app.route('/api/trips/<trip_id>', methods=['PUT'])
def update_trip(trip_id):
    data = request.get_json()
    for i, trip in enumerate(trips):
        if trip['id'] == trip_id:
            trips[i] = {
                'id': trip_id,
                'name':      data.get('name', trip['name']).strip(),
                'color':     data.get('color', trip['color']),
                'waypoints': data.get('waypoints', trip['waypoints']),
                'stops':     data.get('stops', trip.get('stops', [])),
                'matricule': data.get('matricule', trip.get('matricule'))
            }
            save_json(TRIPS_FILE, trips)
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
    bus_positions.pop(trip_id, None)
    save_json(TRIPS_FILE, trips)
    socketio.emit('trips_updated', trips)
    socketio.emit('bus_positions_updated', bus_positions)
    return '', 204


# ── Reservation API ───────────────────────────────────────────

@app.route('/api/reservations', methods=['GET'])
def get_reservations():
    return jsonify(reservations)


@app.route('/api/reservations', methods=['POST'])
def create_reservation():
    data = request.get_json() or {}
    for field in ['name', 'phone', 'date', 'time', 'location']:
        if not str(data.get(field, '')).strip():
            return jsonify({'error': f'Le champ {field} est requis'}), 400
    res = {
        'id':          str(uuid.uuid4()),
        'name':        str(data['name']).strip()[:100],
        'email':       str(data.get('email', '')).strip()[:100],
        'phone':       str(data['phone']).strip()[:30],
        'date':        str(data['date']),
        'time':        str(data['time']),
        'location':    str(data['location']).strip()[:200],
        'pickup_lat':  data.get('pickup_lat'),
        'pickup_lng':  data.get('pickup_lng'),
        'message':     str(data.get('message', '')).strip()[:500],
        'status':      'pending',
        'admin_response': None,
        'created_at':  time.strftime('%Y-%m-%dT%H:%M:%S')
    }
    reservations.append(res)
    save_json(RESERVATIONS_FILE, reservations)
    socketio.emit('reservation_created', res)
    return jsonify(res), 201


@app.route('/api/reservations/<res_id>', methods=['PUT'])
def update_reservation(res_id):
    data = request.get_json() or {}
    for i, res in enumerate(reservations):
        if res['id'] == res_id:
            if 'status' in data:
                reservations[i]['status'] = data['status']
            if 'admin_response' in data:
                reservations[i]['admin_response'] = data['admin_response']
            save_json(RESERVATIONS_FILE, reservations)
            socketio.emit('reservation_updated', reservations[i])
            return jsonify(reservations[i])
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/reservations/<res_id>', methods=['DELETE'])
def delete_reservation(res_id):
    global reservations
    before = len(reservations)
    reservations = [r for r in reservations if r['id'] != res_id]
    if len(reservations) == before:
        return jsonify({'error': 'Not found'}), 404
    save_json(RESERVATIONS_FILE, reservations)
    socketio.emit('reservation_deleted', {'id': res_id})
    return '', 204


# ── WebSocket ─────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    logger.info('Client connected: %s', request.sid)
    emit('trips_updated', trips)
    emit('bus_positions_updated', bus_positions)


@socketio.on('disconnect')
def on_disconnect():
    logger.info('Client disconnected: %s', request.sid)


@socketio.on('bus_location_update')
def on_bus_location_update(data):
    matricule = str(data.get('matricule', '')).strip()
    if not matricule:
        return
    trip = next((t for t in trips if t.get('matricule') == matricule), None)
    if not trip:
        emit('bus_error', {'message': "Matricule non reconnu."})
        return
    try:
        lat = float(data['lat'])
        lng = float(data['lng'])
    except (KeyError, ValueError, TypeError):
        return
    bus_positions[trip['id']] = {
        'lat': lat, 'lng': lng,
        'matricule': matricule,
        'timestamp': time.time()
    }
    emit('bus_positions_updated', bus_positions, broadcast=True)


if __name__ == '__main__':
    host  = os.environ.get('HOST', '0.0.0.0')
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    logger.info('Starting on %s:%s debug=%s', host, port, debug)
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
