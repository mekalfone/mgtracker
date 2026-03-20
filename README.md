# Realtime Location Tracker

A real-time location tracking application that allows multiple devices to share and trace their displacement on an OpenStreetMap-based interface.

## Features

- Real-time location sharing between connected devices
- Visual tracing of movement paths for each user
- OpenStreetMap integration with Leaflet.js
- WebSocket-based communication for live updates

## Technologies Used

- **Backend**: Python with Flask and Flask-SocketIO
- **Frontend**: HTML, JavaScript, Leaflet.js for maps
- **Real-time Communication**: Socket.IO
- **Mapping**: OpenStreetMap tiles

## Setup

1. Clone the repository and navigate to the project directory.

2. Create a virtual environment (recommended):
   ```
   python -m venv venv
   venv\Scripts\activate  # On Windows
   ```

3. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Copy the environment file and configure:
   ```
   cp .env.example .env
   # Edit .env with your settings
   ```

5. Run the server:
   ```
   python app.py
   ```

6. Check health endpoint: `http://localhost:5000/health`

7. Open your browser and navigate to `http://localhost:5000`

7. Allow location permissions when prompted

## Production Deployment

For production deployment:

1. Set `DEBUG=False` in your environment variables
2. Use a strong `SECRET_KEY`
3. Configure `cors_allowed_origins` in `app.py` to your domain instead of "*"
4. Use a production WSGI server like Gunicorn with eventlet:
   ```
   gunicorn --worker-class eventlet -w 1 wsgi:app
   ```
5. Consider using a reverse proxy like Nginx for SSL and load balancing

### AWS Elastic Beanstalk Deployment

1. Install AWS CLI and EB CLI:
   ```
   pip install awsebcli
   ```

2. Initialize EB in your project:
   ```
   eb init
   ```
   - Select your region
   - Choose Python platform
   - Create a new application

3. Create an environment:
   ```
   eb create production-env
   ```

4. Set environment variables:
   ```
   eb setenv SECRET_KEY=your-secure-key DEBUG=False
   ```

5. Deploy:
   ```
   eb deploy
   ```

6. Open the app:
   ```
   eb open
   ```

The `.ebextensions` files are configured for WebSocket support on ALB.

### AWS EC2 Manual Deployment

1. Launch an EC2 instance (Ubuntu recommended)
2. Install Python, pip, and dependencies
3. Clone your repo and install requirements
4. Run with Gunicorn:
   ```
   gunicorn --worker-class eventlet -w 1 wsgi:app --bind 0.0.0.0:8000
   ```
5. Set up Nginx as reverse proxy for SSL/WebSocket support

## Environment Variables

- `SECRET_KEY`: Flask secret key for sessions
- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (default: 5000)
- `DEBUG`: Enable debug mode (default: False)

## How It Works

- Each connected device sends its GPS location to the server periodically
- The server broadcasts location updates to all connected clients
- Clients display markers and movement paths for all active users
- Paths are color-coded for different users

## Requirements

- Python 3.7+
- Modern web browser with geolocation support
- Internet connection for map tiles and real-time updates

## Notes

- Location data is stored in memory; paths reset on server restart
- For persistent storage, integrate a database like PostgreSQL
- For production use, add authentication and rate limiting