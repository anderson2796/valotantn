from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import requests
import sys
import sqlite3
import jwt
import datetime
import time
import random
import threading
import urllib.parse
print("[STARTUP] server.py loading...", flush=True)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import hashlib
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES = True
except Exception as e:
    HAS_POSTGRES = False
    print(f"Warning: Psycopg2 not available: {e}")

try:
    from curl_cffi import requests as c_requests
    HAS_CURL_CFFI = True
except Exception:
    c_requests = requests # Fallback to standard requests if curl_cffi fails
    HAS_CURL_CFFI = False

def log_debug(msg):
    print(f"[DEBUG] {msg}", flush=True)

# Set base directory for static files (project root)
# The backend is in c:\Users\Anderson\Desktop\Sistemas\Valorantn\backend
# So root is one level up
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)
# Enable CORS permissively
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route('/')
def serve_index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(BASE_DIR, path)

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.datetime.utcnow().isoformat()}), 200

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'el_secreto_super_seguro_para_valorantn')

# Configuration
HENRIK_API_KEY = os.environ.get('HENRIK_API_KEY', '')
TRN_API_KEY = os.environ.get('TRN_API_KEY', '')
API_TIMEOUT = 10

# Global Caches (Simple in-memory)
REGION_CACHE = {} # { "name#tag": "region" }
AGGREGATE_CACHE = {} # { "user_id": { "data": ..., "expires": ... } }

# Security Manager for sensitive data encryption
class SecurityManager:
    def __init__(self):
        # In production, this should be a stable environment variable
        master_pwd = os.environ.get('MASTER_ENCRYPTION_KEY', 'valorantn_default_key_for_dev')
        salt = b'valorantn_salt_fixed' # In a real prod environment, use a unique salt per user or a fixed salt for the app
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_pwd.encode()))
        self.fernet = Fernet(key)

    def encrypt(self, data):
        if not data: return None
        return self.fernet.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data):
        if not encrypted_data: return None
        try:
            return self.fernet.decrypt(encrypted_data.encode()).decode()
        except:
            return "[Error Decrypting]"

    def hash_email(self, email):
        """Creates a deterministic hash of the email for database lookups without decrypting."""
        if not email: return None
        return hashlib.sha256(email.lower().strip().encode()).hexdigest()

security = SecurityManager()

class PgConnectionWrapper:
    """Wraps a psycopg2 connection to provide SQLite-like .execute() interface."""
    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, sql, params=()):
        sql = sql.replace('?', '%s')
        is_select = 'SELECT' in sql.upper()
        has_returning = 'RETURNING' in sql.upper()
        if is_select and not has_returning:
            cur = self._conn.cursor(cursor_factory=RealDictCursor)
        else:
            cur = self._conn.cursor()
        cur.execute(sql, params)
        if not is_select and not has_returning:
            self._conn.commit()
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def cursor(self):
        return self._conn.cursor(cursor_factory=RealDictCursor)


def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')

    if db_url and HAS_POSTGRES:
        try:
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
            log_debug("Connecting to PostgreSQL...")
            raw_conn = psycopg2.connect(db_url, connect_timeout=8)
            log_debug("Postgres connected successfully")
            return PgConnectionWrapper(raw_conn), True
        except Exception as e:
            log_debug(f"Postgres connection failed: {e}")
            is_render = 'RENDER' in os.environ
            if is_render:
                raise ConnectionError(f"Database unavailable: {e}")

    # Local SQLite Fallback
    log_debug("Using SQLite fallback.")
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn, False

def init_db():
    conn, is_postgres = get_db_connection()
    
    id_type = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    text_type = "TEXT"
    
    # Use connection directly for SQLite shortcuts, cursor for Postgres
    cursor = conn.cursor() if is_postgres else conn
    
    # Tables creation
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS users (
            id {id_type},
            email {text_type} NOT NULL,
            email_hash {text_type} UNIQUE NOT NULL,
            password_hash {text_type} NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Auto-migration for SQLite if table exists but email_hash is missing
    # Migrations for existing tables
    if is_postgres:
        # Check for email_hash in users
        try:
            cursor.execute("SELECT email_hash FROM users LIMIT 1")
        except:
            conn.rollback() 
            log_debug("Migrating Postgres: adding email_hash column...")
            cursor.execute("ALTER TABLE users ADD COLUMN email_hash TEXT UNIQUE")
            conn.commit()
    else:
        # SQLite migrations
        try:
            cursor.execute("SELECT email_hash FROM users LIMIT 1")
        except Exception as e:
            log_debug(f"Migrating SQLite (email_hash): {e}")
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN email_hash TEXT UNIQUE")
                conn.commit()
            except:
                pass

    # Ensure accounts have necessary columns (migration safety)
    if is_postgres:
        try:
            cursor.execute("SELECT puuid FROM valorant_accounts LIMIT 1")
        except:
            conn.rollback()
            log_debug("Migrating Postgres: valorant_accounts columns...")
            cursor.execute("ALTER TABLE valorant_accounts ADD COLUMN puuid TEXT")
            cursor.execute("ALTER TABLE valorant_accounts ADD COLUMN account_level INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE valorant_accounts ADD COLUMN region TEXT DEFAULT 'latam'")
            cursor.execute("ALTER TABLE valorant_accounts ADD COLUMN card_small TEXT")
            conn.commit()

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS valorant_accounts (
            id {id_type},
            user_id INTEGER NOT NULL,
            name {text_type} NOT NULL,
            tag {text_type} NOT NULL,
            puuid {text_type},
            account_level INTEGER DEFAULT 0,
            region {text_type} DEFAULT 'latam',
            card_small {text_type},
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            UNIQUE(user_id, name, tag)
        )
    ''')
    
    # More SQLite migrations
    if not is_postgres:
        new_cols = [
            ("valorant_accounts", "puuid", "TEXT"),
            ("valorant_accounts", "account_level", "INTEGER DEFAULT 0"),
            ("valorant_accounts", "region", "TEXT DEFAULT 'latam'"),
            ("valorant_accounts", "card_small", "TEXT")
        ]
        for table, col, ctype in new_cols:
            try:
                cursor.execute(f"SELECT {col} FROM {table} LIMIT 1")
            except:
                log_debug(f"Migrating SQLite: adding {col} to {table}...")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ctype}")
                conn.commit()

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS manual_matches (
            id {id_type},
            user_id INTEGER NOT NULL,
            result {text_type},
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER,
            damage INTEGER,
            rounds INTEGER,
            acs INTEGER,
            kast REAL,
            hs REAL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    conn.close()

# Run init_db safely (triggered on first request or main)
_db_initialized = False

def ensure_db_initialized():
    global _db_initialized
    if not _db_initialized:
        try:
            log_debug("Ensuring database is initialized...")
            init_db()
            _db_initialized = True
        except Exception as e:
            log_debug(f"init_db FAILED during safety check: {e}")

def get_db():
    ensure_db_initialized()
    conn, _ = get_db_connection()
    return conn

def get_user_id_for_account(name, tag):
    """Find user_id for a given encrypted account name#tag."""
    try:
        conn = get_db()
        # Fetch only what we need
        accounts = conn.execute("SELECT user_id, name, tag FROM valorant_accounts").fetchall()
        conn.close()
        for acc in accounts:
            try:
                acc_name = security.decrypt(acc['name'])
                acc_tag = security.decrypt(acc['tag'])
                if acc_name.lower() == name.lower() and acc_tag.lower() == tag.lower():
                    return acc['user_id']
            except:
                continue
    except Exception as e:
        print(f"Error in user_id lookup: {e}", flush=True)
    return None

def merge_manual_stats(stats, user_id):
    """Aggregate manual matches into provided stats dict."""
    if not user_id:
        return stats
    try:
        conn = get_db()
        manual = conn.execute("SELECT * FROM manual_matches WHERE user_id = ?", (user_id,)).fetchall()
        conn.close()
        
        if not manual:
            return stats

        print(f"  Merging {len(manual)} manual matches for user {user_id}", flush=True)
        for m in manual:
            stats['games'] = stats.get('games', 0) + 1
            stats['kills'] = stats.get('kills', 0) + (m['kills'] or 0)
            stats['deaths'] = stats.get('deaths', 0) + (m['deaths'] or 0)
            stats['assists'] = stats.get('assists', 0) + (m['assists'] or 0)
            stats['damage'] = stats.get('damage', 0) + (m['damage'] or 0)
            stats['rounds'] = stats.get('rounds', 0) + (m['rounds'] or 0)
            stats['score'] = stats.get('score', 0) + ((m['acs'] or 0) * (m['rounds'] or 0))
            
            res = (m['result'] or "").lower()
            if any(win_word in res for win_word in ['win', 'vitoria', 'vitória', 'victoria']):
                stats['wins'] = stats.get('wins', 0) + 1
            else:
                stats['losses'] = stats.get('losses', 0) + 1
                
        # Re-derive percentages and rates
        d_div = stats['deaths'] if stats['deaths'] > 0 else 1
        r_div = stats['rounds'] if stats['rounds'] > 0 else 1
        g_div = stats['games']  if stats['games']  > 0 else 1
        stats['kd'] = round(stats['kills'] / d_div, 2)
        stats['kpr'] = round(stats['kills'] / r_div, 2)
        stats['damagePerRound'] = round(stats['damage'] / r_div, 1)
        stats['acs'] = round(stats['score'] / r_div, 1)
        stats['winPercentValue'] = round((stats['wins'] / g_div) * 100, 1)
        stats['winPercent'] = f"{stats['winPercentValue']}%"
        stats['kad'] = round((stats['kills'] + stats['assists']) / d_div, 2)
    except Exception as e:
        print(f"Error merging manual stats: {e}", flush=True)
    return stats

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        
        if not token:
            return jsonify({'error': 'Token is missing!'}), 401
            
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            conn = get_db()
            current_user = conn.execute("SELECT * FROM users WHERE id = ?", (data['user_id'],)).fetchone()
            conn.close()
            if not current_user:
                return jsonify({'error': 'User not found!'}), 401
        except Exception as e:
            return jsonify({'error': 'Token is invalid!'}), 401
            
        return f(current_user, *args, **kwargs)
    return decorated

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
        
    email_hash = security.hash_email(email)
    encrypted_email = security.encrypt(email)
    hashed_password = generate_password_hash(password)
    
    conn = get_db()
    try:
        log_debug(f"Attempting to register user: {email_hash[:10]}...")
        conn.execute(
            "INSERT INTO users (email, email_hash, password_hash) VALUES (?, ?, ?)", 
            (encrypted_email, email_hash, hashed_password)
        )
        if hasattr(conn, 'commit'): conn.commit()
        log_debug("User registration committed to DB.")
    except Exception as e:
        err_str = str(e).lower()
        if "unique" in err_str or "already registered" in err_str:
            conn.close()
            return jsonify({'error': 'Email ya registrado.'}), 400
        log_debug(f"Registration Error: {e}")
        conn.close()
        return jsonify({'error': f'Error en base de datos: {str(e)}'}), 500
    
    conn.close()
    return jsonify({'message': 'User created successfully'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
        
    email_hash = security.hash_email(email)
    
    conn = get_db()
    # Search by hash for performance and security
    log_debug(f"Login attempt for hash: {email_hash[:10]}...")
    user = conn.execute("SELECT * FROM users WHERE email_hash = ?", (email_hash,)).fetchone()
    conn.close()
    
    if not user:
        log_debug("Login failed: User record not found.")
        return jsonify({'error': 'Credenciales inválidas'}), 401

    if check_password_hash(user['password_hash'], password):
        token = jwt.encode({
            'user_id': user['id'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        decrypted_email = security.decrypt(user['email'])
        return jsonify({'token': token, 'email': decrypted_email})
    
    log_debug("Login failed: Wrong password.")
    return jsonify({'error': 'Credenciales inválidas'}), 401

@app.route('/api/user/data', methods=['GET'])
@token_required
def get_user_data(current_user):
    conn = get_db()
    accounts = conn.execute("SELECT * FROM valorant_accounts WHERE user_id = ?", (current_user['id'],)).fetchall()
    matches = conn.execute("SELECT * FROM manual_matches WHERE user_id = ?", (current_user['id'],)).fetchall()
    conn.close()
    
    acc_list = [{
        'id': a['id'],
        'name': security.decrypt(a['name']),
        'tag': security.decrypt(a['tag']),
        'puuid': security.decrypt(a['puuid']),
        'account_level': a['account_level'],
        'region': a['region'],
        'card': {'small': a['card_small']} if a['card_small'] else None
    } for a in accounts]
    
    match_list = [dict(m) for m in matches]
    
    return jsonify({'accounts': acc_list, 'manual_matches': match_list})
    
@app.route('/api/user/accounts', methods=['POST'])
@token_required
def add_user_account(current_user):
    data = request.json
    name = data.get('name')
    tag = data.get('tag')
    puuid = data.get('puuid')
    
    # Encrypt account details
    enc_name = security.encrypt(name)
    enc_tag = security.encrypt(tag)
    enc_puuid = security.encrypt(puuid)
    
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO valorant_accounts (user_id, name, tag, puuid, account_level, region, card_small) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (current_user['id'], enc_name, enc_tag, enc_puuid, data.get('account_level', 0), data.get('region', 'latam'), data.get('card', {}).get('small', ''))
        )
        conn.commit()
    except Exception as e:
        err_str = str(e).lower()
        conn.close()
        if 'unique' in err_str or 'duplicate' in err_str:
            return jsonify({'error': 'Account already added'}), 400
        return jsonify({'error': str(e)}), 500
    conn.close()
    return jsonify({'message': 'Account added successfully'}), 201

@app.route('/api/user/accounts/<puuid>', methods=['DELETE'])
@token_required
def delete_user_account(current_user, puuid):
    conn = get_db()
    conn.execute("DELETE FROM valorant_accounts WHERE user_id = ? AND puuid = ?", (current_user['id'], puuid))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Account deleted successfully'})

@app.route('/api/user/matches', methods=['POST'])
@token_required
def add_user_match(current_user):
    data = request.json
    conn, is_pg = get_db_connection()
    try:
        sql = "INSERT INTO manual_matches (user_id, result, kills, deaths, assists, damage, rounds, acs, kast, hs) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        if is_pg:
            sql += " RETURNING id"
            cur = conn.execute(sql, (current_user['id'], data.get('result'), data.get('kills', 0), data.get('deaths', 0), data.get('assists', 0), data.get('damage', 0), data.get('rounds', 0), data.get('acs', 0), data.get('kast', 0.0), data.get('hs', 0.0)))
            match_id = cur.fetchone()[0]
        else:
            cur = conn.execute(sql, (current_user['id'], data.get('result'), data.get('kills', 0), data.get('deaths', 0), data.get('assists', 0), data.get('damage', 0), data.get('rounds', 0), data.get('acs', 0), data.get('kast', 0.0), data.get('hs', 0.0)))
            match_id = cur.lastrowid
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500
    conn.close()
    
    data['id'] = match_id
    return jsonify({'message': 'Match added successfully', 'match': data}), 201

@app.route('/api/user/matches/<int:match_id>', methods=['DELETE'])
@token_required
def delete_user_match(current_user, match_id):
    conn = get_db()
    conn.execute("DELETE FROM manual_matches WHERE user_id = ? AND id = ?", (current_user['id'], match_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Match deleted successfully'})

# Tracker.gg Internal API Config
TRACKER_API_URL = 'https://api.tracker.gg/api/v2/valorant/standard/profile/riot'

# Rank Hierarchy for comparison
RANK_ORDER = {
    "Unrated": 0, "Iron 1": 1, "Iron 2": 2, "Iron 3": 3,
    "Bronze 1": 4, "Bronze 2": 5, "Bronze 3": 6,
    "Silver 1": 7, "Silver 2": 8, "Silver 3": 9,
    "Gold 1": 10, "Gold 2": 11, "Gold 3": 12,
    "Platinum 1": 13, "Platinum 2": 14, "Platinum 3": 15,
    "Diamond 1": 16, "Diamond 2": 17, "Diamond 3": 18,
    "Ascendant 1": 19, "Ascendant 2": 20, "Ascendant 3": 21,
    "Immortal 1": 22, "Immortal 2": 23, "Immortal 3": 24,
    "Radiant": 25
}

# Rank to Tier ID for Icons
RANK_TO_TIER = {
    # Arabic numerals (from Tracker.gg)
    "Iron 1": 3, "Iron 2": 4, "Iron 3": 5,
    "Bronze 1": 6, "Bronze 2": 7, "Bronze 3": 8,
    "Silver 1": 9, "Silver 2": 10, "Silver 3": 11,
    "Gold 1": 12, "Gold 2": 13, "Gold 3": 14,
    "Platinum 1": 15, "Platinum 2": 16, "Platinum 3": 17,
    "Diamond 1": 18, "Diamond 2": 19, "Diamond 3": 20,
    "Ascendant 1": 21, "Ascendant 2": 22, "Ascendant 3": 23,
    "Immortal 1": 24, "Immortal 2": 25, "Immortal 3": 26,
    # Roman numerals (from Henrik API)
    "Iron I": 3, "Iron II": 4, "Iron III": 5,
    "Bronze I": 6, "Bronze II": 7, "Bronze III": 8,
    "Silver I": 9, "Silver II": 10, "Silver III": 11,
    "Gold I": 12, "Gold II": 13, "Gold III": 14,
    "Platinum I": 15, "Platinum II": 16, "Platinum III": 17,
    "Diamond I": 18, "Diamond II": 19, "Diamond III": 20,
    "Ascendant I": 21, "Ascendant II": 22, "Ascendant III": 23,
    "Immortal I": 24, "Immortal II": 25, "Immortal III": 26,
    "Radiant": 27, "Unrated": 0
}

def get_tracker_data(name, tag):
    """Fetch profile data from Tracker.gg with fallback to direct segment fetching."""
    # Proper URL encoding for names with spaces/special chars
    encoded_name = urllib.parse.quote(name)
    encoded_tag = urllib.parse.quote(tag)
    
    # 1. Primary Attempt: Overview
    url = f"https://api.tracker.gg/api/v2/valorant/standard/profile/riot/{encoded_name}%23{encoded_tag}"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'https://tracker.gg/valorant/profile/riot/{encoded_name}%23{encoded_tag}/overview',
        'Origin': 'https://tracker.gg',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    if TRN_API_KEY:
        headers['TRN-Api-Key'] = TRN_API_KEY
    
    try:
        # 1. Primary Attempt: Direct Playlist Segments (Best for lifetime totals)
        # This endpoint specifically returns the aggregated data for a playlist
        segments_url = f"https://api.tracker.gg/api/v2/valorant/standard/profile/riot/{encoded_name}%23{encoded_tag}/segments/playlist?playlist=competitive"
        print(f"Tracker.gg: Fetching lifetime segments for {name}#{tag}...", flush=True)
        if HAS_CURL_CFFI:
            resp = c_requests.get(segments_url, headers=headers, impersonate="chrome120", timeout=API_TIMEOUT)
        else:
            resp = c_requests.get(segments_url, headers=headers, timeout=API_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('data'):
                print(f"Tracker.gg: SUCCESS fetching segments for {name}#{tag}!", flush=True)
                return data
        
        # 2. Secondary Attempt: Overview
        print(f"Tracker.gg: Direct segments failed or empty (Code: {resp.status_code}). Trying profile overview...", flush=True)
        url = f"https://api.tracker.gg/api/v2/valorant/standard/profile/riot/{encoded_name}%23{encoded_tag}"
        if HAS_CURL_CFFI:
            resp = c_requests.get(url, headers=headers, impersonate="chrome120", timeout=API_TIMEOUT)
        else:
            resp = c_requests.get(url, headers=headers, timeout=API_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        
        print(f"Tracker.gg: FAILED both attempts for {name}#{tag} (Last Code: {resp.status_code})", flush=True)
            
    except Exception as e:
        print(f"Error fetching tracker data for {name}: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
    return None

def get_tracker_agents(name, tag):
    """Fetch agent-specific segments from Tracker.gg."""
    url = f"https://api.tracker.gg/api/v2/valorant/standard/profile/riot/{name}%23{tag}/segments/agent?playlist=competitive"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'https://tracker.gg/valorant/profile/riot/{name}%23{tag}/overview',
        'Origin': 'https://tracker.gg'
    }
    try:
        log_debug(f"Fetching Tracker.gg for {name}#{tag} (timeout={API_TIMEOUT}s)")
        if HAS_CURL_CFFI:
            response = c_requests.get(url, headers=headers, impersonate="chrome110", timeout=API_TIMEOUT)
        else:
            response = c_requests.get(url, headers=headers, timeout=API_TIMEOUT)
        
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error fetching agent data for {name}: {e}", flush=True)
    return None

def get_agent_stats_fallback(name, tag, region='latam'):
    """Fallback to match-based agents if tracker fails."""
    print(f"  Fallback: getting agents from matches for {name} (Region: {region})", flush=True)
    m_resp = fetch_henrik(f"/v3/matches/{region}/{name}/{tag}?mode=competitive&size=100")
    if m_resp and m_resp.status_code == 200:
        matches = m_resp.json().get('data', [])
        fb_agents = {}
        for m in matches:
            p = next((x for x in m.get('players', {}).get('all_players', []) 
                    if x['name'].lower() == name.lower() and x['tag'].lower() == tag.lower()), None)
            if p:
                char = p.get('character', 'Unknown')
                if char not in fb_agents:
                    fb_agents[char] = {
                        'name': char, 
                        'icon': p.get('assets', {}).get('agent', {}).get('small'), 
                        'matches': 0, 'wins': 0, 'kills': 0, 'deaths': 0, 'damage': 0, 'rounds': 0, 'score': 0, 'playtime_seconds': 0
                    }
                g = fb_agents[char]
                g['matches'] += 1
                g['kills'] += p.get('stats', {}).get('kills', 0)
                g['deaths'] += p.get('stats', {}).get('deaths', 0)
                g['damage'] += p.get('stats', {}).get('damage', 0)
                g['rounds'] += m.get('metadata', {}).get('rounds_played', 0)
                g['score'] += p.get('stats', {}).get('score', 0)
                # Estimate 100s per round as playtime
                g['playtime_seconds'] += (m.get('metadata', {}).get('rounds_played', 0) * 100) 
                
                my_t = p.get('team', '').lower()
                wt = 'red' if m.get('teams', {}).get('red', {}).get('has_won') else 'blue'
                if my_t == wt: g['wins'] += 1
        
        # Convert to list format
        res = []
        for c, d in fb_agents.items():
            wr = int((d['wins'] / d['matches']) * 100) if d['matches'] > 0 else 0
            d['win_percent'] = f"{wr}%"
            d['kd'] = round(d['kills'] / d['deaths'], 2) if d['deaths'] > 0 else d['kills']
            d['adr'] = round(d['damage'] / d['rounds'], 1) if d['rounds'] > 0 else 0
            d['acs'] = round(d['score'] / d['rounds'], 1) if d['rounds'] > 0 else 0
            hours = d['playtime_seconds'] // 3600
            d['playtime'] = f"{hours}h" if hours > 0 else "0h"
            res.append(d)
        return res
    return []

def parse_agent_segments(t_data):
    """
    Extract agent stats from Tracker.gg segments (type='agent').
    """
    agents = []
    try:
        data_content = t_data.get('data', {})
        if isinstance(data_content, list):
            segments = data_content
        else:
            segments = data_content.get('segments', [])
            
        for seg in segments:
            if seg.get('type') != 'agent':
                continue
            s = seg.get('stats', {})
            agent_name = seg.get('metadata', {}).get('name', 'Unknown')
            icon_url = seg.get('metadata', {}).get('imageUrl', None)
            if not icon_url:
                # Try assets path
                agent_id = seg.get('metadata', {}).get('agentId', '')
                if agent_id:
                    icon_url = f"https://media.valorant-api.com/agents/{agent_id}/displayicon.png"
            agent_stats = {
                'name': agent_name,
                'icon': icon_url,
                'matches': int(s.get('matchesPlayed', {}).get('value', 0)),
                'wins': int(s.get('matchesWon', {}).get('value', 0)),
                'win_percent': s.get('matchesWinPct', {}).get('displayValue', '0%'),
                'kd': float(s.get('kDRatio', {}).get('value', 0)),
                'kills': int(s.get('kills', {}).get('value', 0)),
                'deaths': int(s.get('deaths', {}).get('value', 0)),
                'adr': float(s.get('damagePerRound', {}).get('value', 0)),
                'acs': float(s.get('scorePerRound', {}).get('value', 0)),
                'playtime': s.get('timePlayed', {}).get('displayValue', '0h'),
                'playtime_seconds': int(s.get('timePlayed', {}).get('value', 0)),
                'rounds': int(s.get('roundsPlayed', {}).get('value', 0)),
                'score': int(s.get('score', {}).get('value', 0)),
                'damage': int(s.get('damage', {}).get('value', 0))
            }
            agents.append(agent_stats)
    except Exception as e:
        print(f"Error parsing agent segments: {e}", flush=True)
    return agents


def parse_tracker_data(t_data, name, tag, rank="Career Total", tier_id=0):
    """
    Parse the Tracker.gg profile JSON.
    Structure: t_data.data.segments[] where type='season' has career stats per Act.
    We sum all 'season' segments to get full career totals.
    """
    try:
        data_content = t_data.get('data', {})
        if isinstance(data_content, list):
            segments = data_content
        else:
            segments = data_content.get('segments', [])
            
        if not segments:
            print("Tracker.gg: No segments found in response.", flush=True)
            return None

        # 1. Try to find the 'playlist' segment for 'competitive'
        playlist_seg = next((seg for seg in segments if seg.get('type') == 'playlist' and seg.get('attributes', {}).get('playlist') == 'competitive'), None)
        
        if not playlist_seg and segments:
            # If we only have ONE segment and it's a playlist type, use it (direct fetch result)
            if len(segments) == 1 and segments[0].get('type') == 'playlist':
                playlist_seg = segments[0]

        if playlist_seg:
            s = playlist_seg.get('stats', {})
            print(f"Tracker.gg: Using 'playlist' segment for competitive lifetime stats.", flush=True)
            
            # Extract raw values
            games = int(s.get('matchesPlayed', {}).get('value', 0))
            rounds = int(s.get('roundsPlayed', {}).get('value', 0))
            kills = int(s.get('kills', {}).get('value', 0))
            deaths = int(s.get('deaths', {}).get('value', 0))
            assists = int(s.get('assists', {}).get('value', 0))
            wins = int(s.get('matchesWon', {}).get('value', 0))
            losses = int(s.get('matchesLost', {}).get('value', 0))
            score = int(s.get('score', {}).get('value', 0))
            damage = int(s.get('damage', {}).get('value', 0))
            
            # Fallback for deaths to avoid div by zero
            d_div = deaths if deaths > 0 else 1
            r_div = rounds if rounds > 0 else 1
            g_div = games if games > 0 else 1
            
            hits_head = int(s.get('dealtHeadshots', {}).get('value', 0))
            hits_total = hits_head + int(s.get('dealtBodyshots', {}).get('value', 0)) + int(s.get('dealtLegshots', {}).get('value', 0))
            
            stats = {
                'wins': wins, 'losses': losses, 'games': games,
                'kills': kills, 'deaths': deaths, 'assists': assists,
                'damage': damage, 'rounds': rounds, 'score': score,
                'headshots': int(s.get('headshots', {}).get('value', 0)),
                'hits_head': hits_head,
                'hits_body': int(s.get('dealtBodyshots', {}).get('value', 0)),
                'hits_leg': int(s.get('dealtLegshots', {}).get('value', 0)),
                'clutches': int(s.get('clutches', {}).get('value', 0)),
                'flawless': int(s.get('flawless', {}).get('value', 0)),
                'winPercent': s.get('matchesWinPct', {}).get('displayValue', f"{round(float(wins/g_div)*100.0, 1)}%"),
                'winPercentValue': float(s.get('matchesWinPct', {}).get('value', round(float(wins/g_div)*100.0, 1))),
                'kd': float(s.get('kDRatio', {}).get('value', round(float(kills/d_div), 2))),
                'kpr': float(s.get('killsPerRound', {}).get('value', round(float(kills/r_div), 2))),
                'damagePerRound': float(s.get('damagePerRound', {}).get('value', round(float(damage/r_div), 1))),
                'acs': float(s.get('scorePerRound', {}).get('value', round(float(score/r_div), 1))),
                'headshotPercent': s.get('headshotsPercentage', {}).get('displayValue', '0%'),
                'headshotPercentValue': float(s.get('headshotsPercentage', {}).get('value', 0.0)),
                'kast': s.get('kAST', {}).get('displayValue', '0%'),
                'kastValue': float(s.get('kAST', {}).get('value', 0.0)),
                'dd': float(s.get('damageDeltaPerRound', {}).get('value', 0.0)),
                'kad': float(s.get('kADRatio', {}).get('value', round(float((kills + assists)/d_div), 2)))
            }
            return {
                'name': name, 'tag': tag, 'rank': rank, 'tier_id': tier_id,
                'stats': stats, 'agents': []
            }

        # 2. Fallback: Sum all 'season' competitive segments (if playlist segment is missing)
        season_segs = [seg for seg in segments if seg.get('type') == 'season']
        if not season_segs:
            print("Tracker.gg: No season segments found.", flush=True)
            return None

        # Accumulate totals across all seasons
        totals = {
            'matchesPlayed': 0, 'matchesWon': 0, 'matchesLost': 0,
            'kills': 0, 'deaths': 0, 'assists': 0,
            'damage': 0, 'roundsPlayed': 0, 'score': 0,
            'headshots': 0, 'dealtHeadshots': 0, 'dealtBodyshots': 0, 'dealtLegshots': 0,
            'clutches': 0, 'flawless': 0,
            # Weighted sums for averages
            '_kd_sum': 0.0, '_kpr_sum': 0.0, '_dpr_sum': 0.0,
            '_acs_sum': 0.0, '_kast_sum': 0.0, '_dd_sum': 0.0,
            '_hs_sum': 0.0, '_kad_sum': 0.0
        }

        for seg in season_segs:
            s = seg.get('stats', {})
            w = int(s.get('matchesPlayed', {}).get('value', 0))  # weight = games in this seg
            totals['matchesPlayed']  += w
            totals['matchesWon']     += int(s.get('matchesWon', {}).get('value', 0))
            totals['matchesLost']    += int(s.get('matchesLost', {}).get('value', 0))
            totals['kills']          += int(s.get('kills', {}).get('value', 0))
            totals['deaths']         += int(s.get('deaths', {}).get('value', 0))
            totals['assists']        += int(s.get('assists', {}).get('value', 0))
            totals['damage']         += int(s.get('damage', {}).get('value', 0))
            totals['roundsPlayed']   += int(s.get('roundsPlayed', {}).get('value', 0))
            totals['score']          += int(s.get('score', {}).get('value', 0))
            totals['headshots']      += int(s.get('headshots', {}).get('value', 0))
            totals['dealtHeadshots'] += int(s.get('dealtHeadshots', {}).get('value', 0))
            totals['dealtBodyshots'] += int(s.get('dealtBodyshots', {}).get('value', 0))
            totals['dealtLegshots']  += int(s.get('dealtLegshots', {}).get('value', 0))
            totals['clutches']       += int(s.get('clutches', {}).get('value', 0))
            totals['flawless']       += int(s.get('flawless', {}).get('value', 0))
            # Weighted rate accumulators
            totals['_kast_sum'] += float(s.get('kAST', {}).get('value', 0)) * w
            totals['_dd_sum']   += float(s.get('damageDeltaPerRound', {}).get('value', 0)) * w

        # Final derived stats - compute from raw totals for accuracy
        games   = totals['matchesPlayed']
        rounds  = totals['roundsPlayed']
        deaths  = totals['deaths'] if totals['deaths'] > 0 else 1
        r_div   = rounds if rounds > 0 else 1
        g_div   = games  if games  > 0 else 1
        hits_total = totals['dealtHeadshots'] + totals['dealtBodyshots'] + totals['dealtLegshots']

        kd   = round(float(totals['kills'] / deaths), 2)
        kpr  = round(float(totals['kills'] / r_div), 2)
        dpr  = round(float(totals['damage'] / r_div), 1)
        acs  = round(float(totals['score'] / r_div), 1)
        wr   = round(float((totals['matchesWon'] / g_div) * 100), 1)
        kast_avg = round(float(totals['_kast_sum'] / g_div), 1) if games > 0 else 0.0
        dd_avg   = round(float(totals['_dd_sum'] / g_div), 1)   if games > 0 else 0.0
        kad  = round(float((totals['kills'] + totals['assists']) / deaths), 2)
        hs_pct_val = round(float((totals['dealtHeadshots'] / hits_total) * 100), 1) if hits_total > 0 else 0.0

        stats = {
            'wins':              totals['matchesWon'],
            'losses':            totals['matchesLost'],
            'games':             games,
            'kills':             totals['kills'],
            'deaths':            totals['deaths'],
            'assists':           totals['assists'],
            'damage':            totals['damage'],
            'rounds':            rounds,
            'score':             totals['score'],
            'headshots':         totals['headshots'],
            'hits_head':         totals['dealtHeadshots'],
            'hits_body':         totals['dealtBodyshots'],
            'hits_leg':          totals['dealtLegshots'],
            'clutches':          totals['clutches'],
            'flawless':          totals['flawless'],
            'winPercent':        f"{wr}%",
            'winPercentValue':   wr,
            'kd':                kd,
            'kpr':               kpr,
            'damagePerRound':    dpr,
            'acs':               acs,
            'headshotPercent':   f"{hs_pct_val}%",
            'headshotPercentValue': hs_pct_val,
            'kast':              f"{kast_avg}%",
            'kastValue':         kast_avg,
            'dd':                dd_avg,
            'kad':               kad
        }

        print(f"Parsed Tracker career: {games} games, {totals['kills']} kills across {len(season_segs)} seasons", flush=True)
        return {
            'name': name, 'tag': tag,
            'rank': rank, 'tier_id': tier_id,
            'stats': stats,
            'agents': []  # filled separately
        }

    except Exception as e:
        import traceback
        print(f"Error parsing Tracker data: {e}\n{traceback.format_exc()}", flush=True)
        return None



# Restore Helper Functions
HENRIK_API_URL = 'https://api.henrikdev.xyz/valorant'

def fetch_henrik(endpoint):
    # Ensure name/tag in endpoint are encoded if they are part of the path
    # However, endpoint is already a full path like /v1/account/name/tag
    # We should probably handle encoding at the call site or here
    url = f"{HENRIK_API_URL}{endpoint}"
    headers = {"Authorization": HENRIK_API_KEY} if HENRIK_API_KEY else {}
    try:
        log_debug(f"Fetching HenrikDev: {endpoint} (timeout={API_TIMEOUT}s)")
        return requests.get(url, headers=headers, timeout=API_TIMEOUT)
    except Exception as e:
        log_debug(f"HenrikDev API Connection Error: {e}")
        return None

def get_account_region(name, tag):
    """Determine region for the account using HenrikDev v1/account or v2 fallback"""
    cache_key = f"{name.lower()}#{tag.lower()}"
    if cache_key in REGION_CACHE:
        return REGION_CACHE[cache_key]
        
    safe_name = urllib.parse.quote(name)
    safe_tag = urllib.parse.quote(tag)
    
    region = 'na'
    # Try V1
    resp = fetch_henrik(f"/v1/account/{safe_name}/{safe_tag}")
    if resp and resp.status_code == 200:
        region = resp.json().get('data', {}).get('region', 'na')
    else:
        # Try V2 fallback
        log_debug(f"Region lookup: V1 failed ({resp.status_code if resp else 'No Resp'}), trying V2...")
        resp = fetch_henrik(f"/v2/account/{safe_name}/{safe_tag}")
        if resp and resp.status_code == 200:
            region = resp.json().get('data', {}).get('region', 'na')
            
    REGION_CACHE[cache_key] = region
    return region

def get_stats_dict(name, tag):
    # Strategy 1: Try Tracker.gg (Lifetime)
    t_data = get_tracker_data(name, tag)
    if t_data:
        parsed = parse_tracker_data(t_data, name, tag)
        if parsed and 'stats' in parsed:
            print(f"  Using Tracker.gg data for {name}", flush=True)
            return parsed['stats']

    # Strategy 2: HenrikDev Fallback
    try:
        region = get_account_region(name, tag)
        print(f"  Fetch region: {region}", flush=True)
        # Try size=20 (Optimized from 1000)
        resp = fetch_henrik(f"/v3/matches/{region}/{name}/{tag}?mode=competitive&size=20")
        if not resp or resp.status_code != 200: 
            print(f"  Fetch failed: {resp.status_code if resp else 'No Resp'}", flush=True)
            return None
        
        matches = resp.json().get('data', [])
        print(f"  Fetched {len(matches)} matches.", flush=True)
        
        if len(matches) > 0:
            print(f"  Newest: {matches[0]['metadata'].get('game_start_patched', 'Unknown')}", flush=True)
            print(f"  Oldest: {matches[-1]['metadata'].get('game_start_patched', 'Unknown')}", flush=True)

        s = {'wins':0,'losses':0,'games':0,'kills':0,'deaths':0,'assists':0,'damage':0,'rounds':0}
        
        for m in matches:
            p = next((x for x in m.get('players',{}).get('all_players',[]) if x['name'].lower()==name.lower() and x['tag'].lower()==tag.lower()), None)
            if p:
                ps = p.get('stats', {}) or {}
                s['games']+=1
                s['kills']+=ps.get('kills', 0)
                s['deaths']+=ps.get('deaths', 0)
                s['assists']+=ps.get('assists', 0)
                s['damage']+=ps.get('damage', 0)
                s['rounds']+=m.get('metadata', {}).get('rounds_played', 0)
                
                mt = p.get('team', '').lower()
                wt = 'red' if m.get('teams', {}).get('red', {}).get('has_won') else 'blue'
                if mt == wt: s['wins']+=1
                else: s['losses']+=1
        return s
    except Exception as e:
        print(f"Error in stats dict: {e}", flush=True)
        return None

@app.route('/api/v1/account/<name>/<tag>')
def get_v1_account(name, tag):
    # Re-encode for the actual API call
    safe_name = urllib.parse.quote(name)
    safe_tag = urllib.parse.quote(tag)
    print(f"Validating account {name}#{tag}...", flush=True)
    
    # Stage 1: HenrikDev V1
    resp = fetch_henrik(f"/v1/account/{safe_name}/{safe_tag}")
    if resp and resp.status_code == 200:
        return jsonify(resp.json().get('data', {}))
    
    # Stage 2: HenrikDev V2 Fallback (Better for console or newer accounts)
    log_debug(f"Lookup: Henrik V1 failed ({resp.status_code if resp else 'No Resp'}), trying V2...")
    resp_v2 = fetch_henrik(f"/v2/account/{safe_name}/{safe_tag}")
    if resp_v2 and resp_v2.status_code == 200:
        return jsonify(resp_v2.json().get('data', {}))
        
    # Stage 3: Tracker.gg Fallback (Minimal info but clarifies existence)
    log_debug("Lookup: Henrik V2 failed, trying Tracker.gg...")
    t_data = get_tracker_data(name, tag)
    if t_data and t_data.get('data'):
        p_data = t_data['data']
        # Synthesize a Henrik-like 'data' object
        metadata = p_data.get('metadata', {})
        return jsonify({
            'puuid': p_data.get('platformInfo', {}).get('platformUserIdentifier'),
            'name': name,
            'tag': tag,
            'account_level': 0, # Tracker doesn't easily expose this in overview
            'region': 'na', # Tracker gives country, not Riot region
            'card': {'small': metadata.get('avatarUrl')}
        })

    # Error reporting
    err_msg = 'Account not found'
    status_code = 404
    if resp_v2: # Use V2 response for more accurate status
        if resp_v2.status_code == 429:
            err_msg = 'API Rate Limited (Henrik). Try again in a minute.'
            status_code = 429
        elif resp_v2.status_code == 403:
            err_msg = 'API Access Forbidden.'
            status_code = 403
        else:
            err_msg = f'Account not found (V2 Code: {resp_v2.status_code})'

    return jsonify({'error': err_msg}), status_code

@app.route('/api/profile/<name>/<tag>', methods=['GET'])
def get_profile(name, tag):
    print(f"Fetching profile for {name}#{tag}...", flush=True)

    # 0. Detect region FIRST so all API calls use the correct region
    region = get_account_region(name, tag)
    print(f"  Region detected: {region}", flush=True)

    # 1. Get Rank (Peak Rank preferred)
    rank_display = "Unrated"
    tier_id = 0
    mmr_resp = fetch_henrik(f"/v2/mmr/{region}/{name}/{tag}")
    if mmr_resp and mmr_resp.status_code == 200:
        mmr_data = mmr_resp.json().get('data', {})
        highest = mmr_data.get('highest_rank', {})
        rank_display = highest.get('patched_tier', 'Unrated')
        tier_id = highest.get('tier', 0)
        if not rank_display or rank_display == "Unrated":
            curr = mmr_data.get('current_data', {})
            rank_display = curr.get('currenttierpatched', 'Unrated')
            tier_id = curr.get('currenttier', 0)
    else:
        print(f"  MMR fetch failed/empty for {name} (Code: {mmr_resp.status_code if mmr_resp else 'No Resp'})", flush=True)

    # STRATEGY 1: Try Tracker.gg (Preferred for Lifetime Stats)
    t_data = get_tracker_data(name, tag)
    print(f"  Tracker.gg fetch result: {'SUCCESS' if t_data else 'FAILED'}", flush=True)
    if t_data:
        parsed = parse_tracker_data(t_data, name, tag, rank=rank_display, tier_id=tier_id)
        print(f"  Tracker.gg parse result: {'SUCCESS' if parsed else 'FAILED'}", flush=True)
        if parsed:
            # Merge Manual Matches
            u_id = get_user_id_for_account(name, tag)
            if u_id:
                parsed['stats'] = merge_manual_stats(parsed['stats'], u_id)
                
            # Fetch agents
            agent_data = get_tracker_agents(name, tag)
            if agent_data:
                parsed['agents'] = parse_agent_segments(agent_data)
            if not parsed.get('agents'):
                parsed['agents'] = get_agent_stats_fallback(name, tag, region=region)
            print("Serving data from Tracker.gg", flush=True)
            return jsonify(parsed)

    # STRATEGY 2: Fallback to HenrikDev (Recent Stats)
    print("Tracker.gg failed, falling back to HenrikDev...", flush=True)

    try:
        # Fetch Matches (Optimized size for performance)
        matches_resp = fetch_henrik(f"/v3/matches/{region}/{name}/{tag}?mode=competitive&size=20")
        all_matches = []
        if matches_resp and matches_resp.status_code == 200:
            all_matches = matches_resp.json().get('data', [])
        print(f"  Fetched {len(all_matches)} matches from HenrikDev.", flush=True)

        # Aggregate Stats
        stats = {
            'wins': 0, 'losses': 0, 'games': 0,
            'kills': 0, 'deaths': 0, 'assists': 0,
            'damage': 0, 'rounds': 0,
            'score': 0,
            'headshots': 0, 'bodyshots': 0, 'legshots': 0
        }
        agent_stats = {}

        for m in all_matches:
            # More robust player search: check name/tag case-insensitive, but handle None
            player = None
            players_list = m.get('players', {}).get('all_players', [])
            for p in players_list:
                p_name = (p.get('name') or "").lower()
                p_tag = (p.get('tag') or "").lower()
                if p_name == name.lower() and p_tag == tag.lower():
                    player = p
                    break
            
            if player:
                stats['games'] += 1
                p_stats = player.get('stats', {}) or {}
                rounds_played = m.get('metadata', {}).get('rounds_played', 0)

                stats['kills']   += p_stats.get('kills', 0)
                stats['deaths']  += p_stats.get('deaths', 0)
                stats['assists'] += p_stats.get('assists', 0)
                stats['damage']  += p_stats.get('damage', 0)
                stats['score']   += p_stats.get('score', 0)
                stats['rounds']  += rounds_played
                stats['headshots'] += p_stats.get('headshots', 0)
                stats['bodyshots'] += p_stats.get('bodyshots', 0)
                stats['legshots']  += p_stats.get('legshots', 0)

                my_team = player.get('team', '').lower()
                teams = m.get('teams', {})
                won = (my_team == 'red' and teams.get('red', {}).get('has_won')) or \
                      (my_team == 'blue' and teams.get('blue', {}).get('has_won'))
                if won: stats['wins'] += 1
                else:   stats['losses'] += 1

                # Agent Stats
                char = player.get('character', 'Unknown')
                assets = (player.get('assets') or {}).get('agent') or {}
                if char not in agent_stats:
                    agent_stats[char] = {
                        'name': char, 'icon': assets.get('small'),
                        'matches': 0, 'wins': 0, 'kills': 0, 'deaths': 0,
                        'damage': 0, 'score': 0, 'rounds': 0
                    }
                ag = agent_stats[char]
                ag['matches'] += 1
                ag['kills']   += p_stats.get('kills', 0)
                ag['deaths']  += p_stats.get('deaths', 0)
                ag['damage']  += p_stats.get('damage', 0)
                ag['score']   += p_stats.get('score', 0)
                ag['rounds']  += rounds_played
                if won: ag['wins'] += 1

        # Calculate Derived Stats
        d = stats['deaths'] if stats['deaths'] > 0 else 1
        r = stats['rounds'] if stats['rounds'] > 0 else 1
        g = stats['games']  if stats['games']  > 0 else 1
        total_shots = stats['headshots'] + stats['bodyshots'] + stats['legshots']

        kd  = round(stats['kills'] / d, 2)
        kpr = round(stats['kills'] / r, 2)
        dpr = round(stats['damage'] / r, 1)
        acs = round(stats['score'] / r, 1)
        wr  = round((stats['wins'] / g) * 100, 1)
        hs_pct = f"{round((stats['headshots'] / total_shots) * 100, 1)}%" if total_shots > 0 else "0%"
        kad = round((stats['kills'] + stats['assists']) / d, 2)

        # Format Agent List
        agents_list = []
        for char, d_ag in agent_stats.items():
            r_ag = d_ag['rounds'] if d_ag['rounds'] > 0 else 1
            d_deaths = d_ag['deaths'] if d_ag['deaths'] > 0 else 1
            m_ag = d_ag['matches'] if d_ag['matches'] > 0 else 1
            agents_list.append({
                'name':        char,
                'icon':        d_ag['icon'],
                'matches':     d_ag['matches'],
                'win_percent': f"{int(round((d_ag['wins'] / m_ag) * 100))}%",
                'kd':          round(d_ag['kills'] / d_deaths, 2),
                'adr':         round(d_ag['damage'] / r_ag, 1),
                'acs':         round(d_ag['score'] / r_ag, 1),
                'playtime':    f"{d_ag['matches']}P"
            })
        agents_list.sort(key=lambda x: x['matches'], reverse=True)

        profile_res = {
            'name': name, 'tag': tag,
            'rank': rank_display, 'tier_id': tier_id,
            'stats': {
                'wins':              stats['wins'],
                'losses':            stats['losses'],
                'games':             stats['games'],
                'kills':             stats['kills'],
                'deaths':            stats['deaths'],
                'assists':           stats['assists'],
                'winPercent':        f"{wr}%",
                'winPercentValue':   wr,
                'kd':                kd,
                'kpr':               kpr,
                'damagePerRound':    dpr,
                'acs':               acs,
                'headshotPercent':   hs_pct,
                'headshotPercentValue': round((stats['headshots'] / total_shots) * 100, 1) if total_shots > 0 else 0,
                'kast':              'N/A',
                'kastValue':         0,
                'dd':                0,
                'kad':               kad,
                'clutches':          0,
                'flawless':          0,
                'score':             stats['score'],
                'headshots':         stats['headshots'],
                'damage':            stats['damage'],
                'rounds':            stats['rounds'],
            },
            'agents': agents_list
        }

        # Merge Manual Matches into Fallback Stats
        u_id = get_user_id_for_account(name, tag)
        if u_id:
            profile_res['stats'] = merge_manual_stats(profile_res['stats'], u_id)

        return jsonify(profile_res)

    except Exception as e:
        log_debug(f"    Fallback for {name}#{tag}")
        m_resp = fetch_henrik(f"/v3/matches/{region}/{name}/{tag}?mode=competitive&size=20")
        if m_resp and m_resp.status_code == 200:
            matches = m_resp.json().get('data', [])
            fb_agents_map = {}
            for m in matches:
                p = next((x for x in m.get('players', {}).get('all_players', [])
                        if x['name'].lower() == name.lower() and x['tag'].lower() == tag.lower()), None)
                if p:
                    ps = p.get('stats', {})
                    r_p = m.get('metadata', {}).get('rounds_played', 0)
                    local_total['games'] += 1
                    local_total['kills'] += ps.get('kills', 0)
                    local_total['deaths'] += ps.get('deaths', 0)
                    local_total['assists'] += ps.get('assists', 0)
                    local_total['damage'] += ps.get('damage', 0)
                    local_total['rounds'] += r_p
                    local_total['score'] += ps.get('score', 0)
                    local_total['headshots'] += ps.get('headshots', 0)
                    local_total['hits_total'] += (ps.get('headshots', 0) + ps.get('bodyshots', 0) + ps.get('legshots', 0))

                    my_t = p.get('team', '').lower()
                    wt = 'red' if m.get('teams', {}).get('red', {}).get('has_won') else 'blue'
                    if my_t == wt: local_total['wins'] += 1
                    else: local_total['losses'] += 1

                    char = p.get('character', 'Unknown')
                    if char not in fb_agents_map:
                        assets = p.get('assets') or {}
                        agent_assets = assets.get('agent') or {}
                        fb_agents_map[char] = {
                            'name': char, 'icon': agent_assets.get('small'),
                            'matches': 0, 'wins': 0, 'kills': 0, 'deaths': 0,
                            'score': 0, 'rounds': 0, 'damage': 0, 'playtime_seconds': 0
                        }
                    ag = fb_agents_map[char]
                    ag['matches'] += 1
                    ag['kills'] += ps.get('kills', 0)
                    ag['deaths'] += ps.get('deaths', 0)
                    ag['damage'] += ps.get('damage', 0)
                    ag['rounds'] += r_p
                    ag['score'] += ps.get('score', 0)
            local_agents = list(fb_agents_map.values())

    return local_total, local_agents, best_rank, best_tier


@app.route('/api/aggregate', methods=['POST'])
@token_required
def aggregate_accounts(current_user):
    u_id = current_user['id']
    now = time.time()
    if u_id in AGGREGATE_CACHE:
        entry = AGGREGATE_CACHE[u_id]
        if now < entry['expires']:
            cached = entry['data']
            # Don't serve empty cache
            if cached.get('total', {}).get('games', 0) > 0:
                log_debug(f"Serving aggregate from cache for user {u_id}")
                return jsonify(cached)
            else:
                log_debug(f"Cache for user {u_id} is empty/stale, re-fetching")
                del AGGREGATE_CACHE[u_id]

    data_in = request.json
    accounts = data_in.get('accounts', [])
    log_debug(f"AGGREGATION START: {len(accounts)} accounts")
    
    total = {
        'games': 0, 'wins': 0, 'losses': 0,
        'kills': 0, 'deaths': 0, 'assists': 0,
        'damage': 0, 'rounds': 0, 'level': 0,
        'clutches': 0, 'flawless': 0, 'score': 0,
        'headshots': 0, 'hits_total': 0, 
        'kast_weighted': 0.0, 'dd_weighted': 0.0
    }
    
    highest_rank_name = "Unrated"
    highest_level = 0
    highest_tier = -1
    global_agents = {}
    
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Note: process_account is defined globally below
            future_to_acc = {executor.submit(process_account, acc): acc for acc in accounts}

            for future in as_completed(future_to_acc):
                acc = future_to_acc[future]
                try:
                    to_val = API_TIMEOUT + 5
                    result = future.result(timeout=to_val)
                    if not result: continue

                    l_total, l_agents, b_rank, b_tier = result

                    for k in total:
                        if k in l_total: total[k] += l_total[k]

                    if b_tier is not None and b_tier > highest_tier:
                        highest_tier = b_tier
                        highest_rank_name = b_rank

                    if l_total.get('level', 0) > highest_level:
                        highest_level = l_total['level']

                    for a in l_agents:
                        char = a['name']
                        if char not in global_agents:
                            global_agents[char] = {
                                'name': char, 'icon': a['icon'],
                                'matches': 0, 'wins': 0, 'kills': 0, 'deaths': 0,
                                'score': 0, 'rounds': 0, 'damage': 0, 'playtime_seconds': 0
                            }
                        g = global_agents[char]
                        g['matches'] += a['matches']
                        g['wins'] += a['wins']
                        g['kills'] += a.get('kills', 0)
                        g['deaths'] += a.get('deaths', 0)
                        g['damage'] += a.get('damage', 0)
                        g['rounds'] += a.get('rounds', 0)
                        g['score'] += a.get('score', 0)
                        g['playtime_seconds'] += a.get('playtime_seconds', 0)

                except Exception as e:
                    log_debug(f"Error processing account {acc.get('name')}: {e}")

    except Exception as e:
        log_debug(f"ThreadPool error: {e}")
        return jsonify({'error': 'Error en procesamiento paralelo', 'detail': str(e)}), 500

    games = total['games'] if total['games'] > 0 else 1
    rounds_total = total['rounds'] if total['rounds'] > 0 else 1
    deaths_total = total['deaths'] if total['deaths'] > 0 else 1
    hits_total = total['hits_total'] if total['hits_total'] > 0 else 1

    derived = {
        'winRate': round(float(total['wins'] / games) * 100, 1),
        'kd': round(float(total['kills'] / deaths_total), 2),
        'kpr': round(float(total['kills'] / rounds_total), 2),
        'adr': round(float(total['damage'] / rounds_total), 1),
        'acs': round(float(total['score'] / rounds_total), 1),
        'hs': round(float(total['headshots'] / hits_total) * 100, 1) if total['headshots'] > 0 else 0.0,
        'kast': round(float(total['kast_weighted'] / rounds_total), 1),
        'kad': round(float(total['kills'] + total['assists']) / deaths_total, 2),
        'dd': round(float(total['dd_weighted'] / rounds_total), 1)
    }

    processed_agents = []
    for char, g in global_agents.items():
        ma = g['matches'] if g['matches'] > 0 else 1
        ro = g['rounds'] if g['rounds'] > 0 else 1
        de = g['deaths'] if g['deaths'] > 0 else 1
        g['win_percent'] = f"{round((g['wins']/ma)*100, 1)}%"
        g['kd'] = round(g['kills']/de, 2)
        g['adr'] = round(g['damage']/ro, 1)
        g['acs'] = round(g['score']/ro, 1)
        h = g['playtime_seconds'] // 3600
        g['playtime'] = f"{h}h"
        processed_agents.append(g)

    processed_agents.sort(key=lambda x: x['matches'], reverse=True)

    tier_id = RANK_TO_TIER.get(highest_rank_name, 0)
    if tier_id == 0 and highest_rank_name != 'Unrated':
        # Try case-insensitive match
        for k, v in RANK_TO_TIER.items():
            if k.lower() == highest_rank_name.lower():
                tier_id = v
                break
    rank_img = f"https://media.valorant-api.com/competitivetiers/03621f52-342b-cf4e-4f86-9350a49c6d04/{tier_id}/largeicon.png"
    if tier_id == 0:
        rank_img = "https://media.valorant-api.com/competitivetiers/03621f52-342b-cf4e-4f86-9350a49c6d04/0/largeicon.png"

    res_final = {
        'total': total,
        'derived': derived,
        'highest_rank': highest_rank_name,
        'highest_rank_image': rank_img,
        'agents': processed_agents
    }
    
    AGGREGATE_CACHE[u_id] = { 'data': res_final, 'expires': time.time() + 300 }
    return jsonify(res_final)

def process_account(acc):
    """Worker function to process a single account with fallbacks."""
    local_total = {
        'games': 0, 'wins': 0, 'losses': 0,
        'kills': 0, 'deaths': 0, 'assists': 0,
        'damage': 0, 'rounds': 0, 'score': 0,
        'headshots': 0, 'hits_total': 0, 
        'clutches': 0, 'flawless': 0,
        'kast_weighted': 0.0, 'dd_weighted': 0.0,
        'level': 0
    }
    local_agents = []
    best_rank = "Unrated"
    best_tier = -1

    try:
        if acc.get('type') == 'manual':
            s = acc.get('stats', {})
            local_total['games'] = (s.get('wins', 0) + s.get('losses', 0))
            local_total['wins'] = s.get('wins', 0)
            local_total['losses'] = s.get('losses', 0)
            local_total['kills'] = s.get('kills', 0)
            local_total['deaths'] = s.get('deaths', 0)
            local_total['assists'] = s.get('assists', 0)
            local_total['damage'] = s.get('damage', 0)
            local_total['rounds'] = s.get('rounds', 0)
            r = s.get('rounds', 0) or 1
            local_total['score'] = (s.get('acs', 200) * r)
            local_total['kast_weighted'] = (s.get('kast', 75.0) * r)
            local_total['hits_total'] = r * 10
            local_total['headshots'] = (s.get('hs', 15.0) / 100.0) * local_total['hits_total']
            return local_total, local_agents, best_rank, best_tier

        name = acc.get('name')
        tag = acc.get('tag')
        region = acc.get('region', 'latam')
        local_total['level'] = int(acc.get('account_level', 0))
        print(f"[AGG] Processing: {name}#{tag} region={region} level={local_total['level']}", flush=True)

        # 1. Rank from Henrik MMR
        mmr_resp = fetch_henrik(f"/v2/mmr/{region}/{name}/{tag}")
        if mmr_resp and mmr_resp.status_code == 200:
            m_data = mmr_resp.json().get('data', {})
            h = m_data.get('highest_rank', {})
            best_rank = h.get('patched_tier', 'Unrated')
            best_tier = h.get('tier', -1)
            print(f"[AGG] Rank OK: {best_rank} (tier {best_tier})", flush=True)
        else:
            code = mmr_resp.status_code if mmr_resp else 'None'
            print(f"[AGG] Rank FAILED: HTTP {code}", flush=True)

        # 2. Tracker.gg Stats (Lifetime)
        t_data = get_tracker_data(name, tag)
        if t_data:
            p = parse_tracker_data(t_data, name, tag)
            if p and p.get('stats'):
                s = p['stats']
                print(f"[AGG] Tracker OK: {s.get('kills',0)}K {s.get('deaths',0)}D {s.get('games',0)}G", flush=True)
                saved_level = local_total['level']  # preserve level from account_level
                for k in local_total:
                    if k in s and k != 'level': local_total[k] = s[k]  # never overwrite level
                local_total['level'] = saved_level
                local_total['hits_total'] = s.get('hits_head',0) + s.get('hits_body',0) + s.get('hits_leg',0)
                local_total['kast_weighted'] = s.get('kastValue',0) * s.get('rounds',0)
                local_total['dd_weighted'] = s.get('dd',0) * s.get('rounds',0)
                
                # Agents
                a_raw = get_tracker_agents(name, tag)
                local_agents = parse_agent_segments(a_raw) if a_raw else get_agent_stats_fallback(name, tag, region)
                return local_total, local_agents, best_rank, best_tier
            else:
                print(f"[AGG] Tracker data empty after parse for {name}#{tag}", flush=True)
        else:
            print(f"[AGG] Tracker FAILED for {name}#{tag} - falling back to Henrik matches", flush=True)

        # 3. Henrik Fallback (Recent matches - try competitive then unrated)
        enc_name = urllib.parse.quote(name)
        enc_tag = urllib.parse.quote(tag)
        henrik_matches = []
        for mode in ['competitive', 'unrated', 'deathmatch']:
            m_resp = fetch_henrik(f"/v3/matches/{region}/{enc_name}/{enc_tag}?mode={mode}&size=20")
            if m_resp and m_resp.status_code == 200:
                henrik_matches = m_resp.json().get('data', [])
                if henrik_matches:
                    print(f"[AGG] Henrik {mode} matches: {len(henrik_matches)} found", flush=True)
                    break
            print(f"[AGG] Henrik {mode} failed or empty", flush=True)
        
        print(f"[AGG] Total Henrik matches to process: {len(henrik_matches)}", flush=True)
        fb_agents = {}
        for m in henrik_matches:
            p = next((x for x in m.get('players', {}).get('all_players', []) if x['name'].lower()==name.lower() and x['tag'].lower()==tag.lower()), None)
            if p:
                ps = p.get('stats', {})
                r_p = m.get('metadata', {}).get('rounds_played', 0)
                local_total['games'] += 1
                local_total['kills'] += ps.get('kills', 0)
                local_total['deaths'] += ps.get('deaths', 0)
                local_total['assists'] += ps.get('assists', 0)
                local_total['damage'] += ps.get('damage', 0)
                local_total['rounds'] += r_p
                local_total['score'] += ps.get('score', 0)
                local_total['headshots'] += ps.get('headshots', 0)
                local_total['hits_total'] += (ps.get('headshots',0)+ps.get('bodyshots',0)+ps.get('legshots',0))
                t_win = 'red' if m.get('teams',{}).get('red',{}).get('has_won') else 'blue'
                if p.get('team','').lower() == t_win: local_total['wins'] += 1
                else: local_total['losses'] += 1
                char = p.get('character', 'Unknown')
                if char not in fb_agents:
                    fb_agents[char] = {
                        'name': char, 'icon': p.get('assets',{}).get('agent',{}).get('small'),
                        'matches': 0, 'wins': 0, 'kills': 0, 'deaths': 0,
                        'score': 0, 'rounds': 0, 'damage': 0, 'playtime_seconds': 0
                    }
                ga = fb_agents[char]
                ga['matches'] += 1
                ga['kills'] += ps.get('kills', 0)
                ga['deaths'] += ps.get('deaths', 0)
                ga['damage'] += ps.get('damage', 0)
                ga['rounds'] += r_p
                ga['score'] += ps.get('score', 0)
                if p.get('team','').lower() == t_win: ga['wins'] += 1
        local_agents = list(fb_agents.values())

    except Exception as e:
        log_debug(f"Process account failed for {acc.get('name')}: {e}")

    return local_total, local_agents, best_rank, best_tier

@app.route('/api/debug/db')
def debug_db():
    db_url = os.environ.get('DATABASE_URL')
    status = {
        'HAS_POSTGRES': HAS_POSTGRES,
        'DATABASE_URL_SET': bool(db_url),
        'DATABASE_URL_TYPE': db_url[:10] + "..." if db_url else "None",
        'VERSION': '1.0.4-fallback-fix'
    }
    try:
        conn, is_pg = get_db_connection()
        status['CONNECTION'] = 'OK'
        status['DB_TYPE'] = "PostgreSQL" if is_pg else "SQLite"
        
        # Check users table columns
        if is_pg:
            cur = conn.cursor()
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
            status['USERS_COLUMNS'] = [row[0] if isinstance(row, tuple) else row['column_name'] for row in cur.fetchall()]
        else:
            cur = conn.execute("PRAGMA table_info(users)")
            status['USERS_COLUMNS'] = [row[1] for row in cur.fetchall()]
        conn.close()
    except Exception as e:
        status['CONNECTION'] = f'FAILED: {str(e)}'
    
    return jsonify(status)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("="*50)
    print(f"VALORANT STATS (HENRIK) SERVER - Listening on port {port}")
    print("="*50)
    app.run(host='0.0.0.0', port=port)

print("[STARTUP] server.py loaded successfully.", flush=True)
