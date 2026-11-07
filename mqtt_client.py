import json
import logging
import threading
import paho.mqtt.client as mqtt
from models import db, AssetMeter, AssetMeterReading, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dictionary to hold active MQTT clients: key is "broker:port", value is mqtt.Client
active_clients = {}
clients_lock = threading.Lock()

def flatten_mqtt_payload(data, prefix=''):
    flattened = {}
    if isinstance(data, dict):
        if 'tag' in data and 'value' in data:
            flattened[str(data['tag'])] = data['value']
        elif 'name' in data and 'value' in data:
            flattened[str(data['name'])] = data['value']
            
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                flattened.update(flatten_mqtt_payload(v, f"{prefix}{k}."))
            else:
                flattened[f"{prefix}{k}"] = v
                
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                if 'tag' in item and 'value' in item:
                    flattened[str(item['tag'])] = item['value']
                elif 'name' in item and 'value' in item:
                    flattened[str(item['name'])] = item['value']
            flattened.update(flatten_mqtt_payload(item, f"{prefix}[{i}]."))
    return flattened

def on_connect(client, userdata, flags, rc):
    broker = userdata['broker']
    app = userdata['app']
    if rc == 0:
        logger.info(f"[MQTT Manager] Connected successfully to {broker}!")
        with app.app_context():
            meters = AssetMeter.query.filter_by(mqtt_broker=broker).all()
            for m in meters:
                if m.mqtt_topic:
                    client.subscribe(m.mqtt_topic)
                    logger.info(f" -> Subscribed to: {m.mqtt_topic}")
    else:
        logger.error(f"[MQTT Manager] Failed to connect to {broker}, code {rc}")

def on_message(client, userdata, msg):
    try:
        app = userdata['app']
        broker = userdata['broker']
        topic = msg.topic
        
        raw_payload = ''
        try:
            raw_payload = msg.payload.decode('utf-8')
        except Exception:
            pass
            
        with app.app_context():
            meters = AssetMeter.query.filter_by(mqtt_broker=broker).all()
            
            matched_meters = []
            for m in meters:
                if m.mqtt_topic and mqtt.topic_matches_sub(m.mqtt_topic, topic):
                    matched_meters.append(m)
                    
            if not matched_meters:
                return
                
            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                return
                
            flat_payload = flatten_mqtt_payload(payload)
                
            sys_user = User.query.filter((User.role == 'Admin') | (User.role == 'Manager')).first()
            user_id = sys_user.id if sys_user else None
                
            for meter in matched_meters:
                payload_key = meter.mqtt_payload_key
                if payload_key and payload_key in flat_payload:
                    val = flat_payload[payload_key]
                    try:
                        reading_val = float(val)
                        reading = AssetMeterReading(
                            meter_id=meter.id,
                            reading_value=reading_val,
                            user_id=user_id
                        )
                        db.session.add(reading)
                    except (ValueError, TypeError):
                        pass
            
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"[MQTT Error] DB Commit Failed: {e}")
                
    except Exception as e:
        logger.error(f"[MQTT Error] Uncaught exception in on_message: {e}")
    finally:
        try:
            db.session.remove()
        except Exception:
            pass

def start_client_for_broker(app, broker, port):
    key = f"{broker}:{port}"
    with clients_lock:
        if key in active_clients:
            return active_clients[key]
            
        client = mqtt.Client()
        client.user_data_set({'app': app, 'broker': broker})
        client.on_connect = on_connect
        client.on_message = on_message
        
        try:
            client.connect(broker, port, 60)
            client.loop_start()
            active_clients[key] = client
            logger.info(f"[MQTT Manager] Spawned new standalone background thread for {broker}:{port}")
            return client
        except Exception as e:
            logger.error(f"[MQTT Manager] Could not start client for {broker}:{port} - {e}")
            return None

def refresh_mqtt_managers(app):
    from werkzeug.local import LocalProxy
    if isinstance(app, LocalProxy):
        app = app._get_current_object()
        
    with app.app_context():
        meters = AssetMeter.query.filter(AssetMeter.mqtt_broker.isnot(None), AssetMeter.mqtt_broker != '').all()
        
        broker_topics = {}
        for m in meters:
            port = m.mqtt_port if m.mqtt_port else 1883
            key = f"{m.mqtt_broker}:{port}"
            if key not in broker_topics:
                broker_topics[key] = {'broker': m.mqtt_broker, 'port': port, 'topics': set()}
            if m.mqtt_topic:
                broker_topics[key]['topics'].add(m.mqtt_topic)
                
        for key, info in broker_topics.items():
            client = start_client_for_broker(app, info['broker'], info['port'])
            if client:
                for t in info['topics']:
                    client.subscribe(t)

def start_mqtt(app):
    refresh_mqtt_managers(app)
