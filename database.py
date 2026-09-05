# database.py
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "database.db"

PLAN_LIMITS = {
    "free": 3,
    "premium": 999
}

def get_moscow_time():
    return datetime.utcnow()

def get_moscow_now_str():
    return get_moscow_time().strftime('%Y-%m-%d %H:%M:%S')

class Database:
    def __init__(self):
        self._init_db()

    def _get_connection(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT NOT NULL,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_banned INTEGER DEFAULT 0,
                    is_premium INTEGER DEFAULT 0,
                    premium_until TIMESTAMP,
                    plan TEXT DEFAULT 'free',
                    free_until TIMESTAMP,
                    subgram_linked INTEGER DEFAULT 0,
                    notify_24h_sent INTEGER DEFAULT 0,
                    notify_expired_sent INTEGER DEFAULT 0,
                    notify_1h_sent INTEGER DEFAULT 0
                )
            """)
            
            try:
                conn.execute("ALTER TABLE users ADD COLUMN free_until TIMESTAMP")
            except sqlite3.OperationalError:
                pass
            
            try:
                conn.execute("ALTER TABLE users ADD COLUMN subgram_linked INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            
            try:
                conn.execute("ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'")
            except sqlite3.OperationalError:
                pass
            
            try:
                conn.execute("ALTER TABLE users ADD COLUMN notify_1h_sent INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_tokens (
                    user_id INTEGER PRIMARY KEY,
                    token TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS device_fingerprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    fingerprint TEXT NOT NULL,
                    device_name TEXT,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, fingerprint)
                )
            """)
            
            try:
                conn.execute("ALTER TABLE device_fingerprints ADD COLUMN device_name TEXT")
            except sqlite3.OperationalError:
                pass

            try:
                conn.execute("ALTER TABLE device_fingerprints ADD COLUMN platform TEXT")
            except sqlite3.OperationalError:
                pass

            try:
                conn.execute("ALTER TABLE device_fingerprints ADD COLUMN os TEXT")
            except sqlite3.OperationalError:
                pass

            try:
                conn.execute("ALTER TABLE device_fingerprints ADD COLUMN os_version TEXT")
            except sqlite3.OperationalError:
                pass
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS payments_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount INTEGER,
                    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS premium_purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount INTEGER,
                    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_key TEXT NOT NULL,
                    duration_key TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    UNIQUE(plan_key, duration_key)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    agreement_shown INTEGER DEFAULT 0
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS admin_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    action TEXT NOT NULL,
                    target_user_id INTEGER,
                    details TEXT,
                    ip TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            conn.execute("""
                INSERT OR IGNORE INTO settings (key, value)
                VALUES ('maintenance_mode', '0')
            """)
            
            conn.execute("""
                INSERT OR IGNORE INTO settings (key, value)
                VALUES ('last_user_update', '1970-01-01 00:00:00')
            """)
            
            default_prices = [
                ("premium", "month", 199),
                ("premium", "3months", 549),
                ("premium", "6months", 999),
            ]
            
            for plan_key, duration_key, price in default_prices:
                conn.execute("""
                    INSERT OR IGNORE INTO prices (plan_key, duration_key, price)
                    VALUES (?, ?, ?)
                """, (plan_key, duration_key, price))
            
            conn.execute("""
                INSERT OR IGNORE INTO admin_users (username, password)
                VALUES ('hizol', 'DAKq2mAinhWQ')
            """)
            
            conn.commit()
            logger.info("База данных инициализирована")

    def update_user_info(self, user_id: int, first_name: str, username: str = None):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE users 
                SET first_name = ?, username = ?
                WHERE user_id = ?
            """, (first_name, username, user_id))
            conn.commit()

    def get_all_users_with_details(self, limit: int = None, offset: int = None) -> list:
        with self._get_connection() as conn:
            moscow_now = get_moscow_time()
            query = """
                SELECT user_id, first_name, username, plan, is_banned, is_premium, premium_until, free_until,
                       (is_premium = 1 OR free_until > ?) as is_active
                FROM users
                ORDER BY user_id DESC
            """
            if limit is not None and offset is not None:
                query += " LIMIT ? OFFSET ?"
                rows = conn.execute(query, (moscow_now, limit, offset)).fetchall()
            elif limit is not None:
                query += " LIMIT ?"
                rows = conn.execute(query, (moscow_now, limit)).fetchall()
            else:
                rows = conn.execute(query, (moscow_now,)).fetchall()
            return [dict(row) for row in rows]

    def get_last_user_update_time(self) -> datetime:
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'last_user_update'").fetchone()
            if row:
                return datetime.fromisoformat(row['value'])
            return datetime(1970, 1, 1)

    def set_last_user_update_time(self, update_time: datetime):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO settings (key, value)
                VALUES ('last_user_update', ?)
            """, (update_time.isoformat(),))
            conn.commit()

    def get_maintenance_mode(self) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'maintenance_mode'").fetchone()
            if row:
                return row['value'] == '1'
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance_mode', '0')")
            conn.commit()
            return False

    def set_maintenance_mode(self, enabled: bool):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO settings (key, value)
                VALUES ('maintenance_mode', ?)
            """, ('1' if enabled else '0',))
            conn.commit()

    def log_admin_action(self, admin_id: int, action: str, target_user_id: int = None, details: str = None, ip: str = None):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO admin_logs (admin_id, action, target_user_id, details, ip)
                VALUES (?, ?, ?, ?, ?)
            """, (admin_id, action, target_user_id, details, ip))
            conn.commit()

    def get_price(self, plan_key: str, duration_key: str) -> int:
        with self._get_connection() as conn:
            row = conn.execute("SELECT price FROM prices WHERE plan_key = ? AND duration_key = ?", (plan_key, duration_key)).fetchone()
            return row['price'] if row else 199

    def set_price(self, plan_key: str, duration_key: str, price: int):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO prices (plan_key, duration_key, price)
                VALUES (?, ?, ?)
            """, (plan_key, duration_key, price))
            conn.commit()

    def get_all_prices(self) -> dict:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT plan_key, duration_key, price FROM prices").fetchall()
            result = {}
            for row in rows:
                if row['plan_key'] not in result:
                    result[row['plan_key']] = {}
                result[row['plan_key']][row['duration_key']] = row['price']
            return result

    def set_agreement_shown(self, user_id: int):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_settings (user_id, agreement_shown)
                VALUES (?, 1)
            """, (user_id,))
            conn.commit()

    def get_agreement_shown(self, user_id: int) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT agreement_shown FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
            return row['agreement_shown'] == 1 if row else False

    def check_admin_credentials(self, username: str, password: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM admin_users WHERE username = ? AND password = ?",
                (username, password)
            ).fetchone()
            return row is not None

    def get_admin_id(self, username: str) -> Optional[int]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT id FROM admin_users WHERE username = ?", (username,)).fetchone()
            return row['id'] if row else None

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def create_user(self, user_id: int, first_name: str, username: str = None):
        free_until = get_moscow_time() + timedelta(days=3)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO users (user_id, first_name, username, plan, free_until, subgram_linked, notify_24h_sent, notify_expired_sent, notify_1h_sent)
                VALUES (?, ?, ?, 'free', ?, 0, 0, 0, 0)
            """, (user_id, first_name, username, free_until))
            conn.commit()
            logger.info(f"User created: {user_id} ({first_name}) with free_until {free_until}")

    def is_subscription_active(self, user_id: int) -> bool:
        with self._get_connection() as conn:
            moscow_now = get_moscow_time()
            row = conn.execute("""
                SELECT (is_premium = 1 OR free_until > ?) as is_active 
                FROM users WHERE user_id = ?
            """, (moscow_now, user_id)).fetchone()
            return row['is_active'] == 1 if row else False

    def get_free_until(self, user_id: int) -> Optional[datetime]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT free_until FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row and row['free_until']:
                return datetime.fromisoformat(row['free_until'])
            return None

    def get_subscription_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT free_until, is_premium, premium_until, plan, 
                       notify_24h_sent, notify_expired_sent, notify_1h_sent, subgram_linked
                FROM users WHERE user_id = ?
            """, (user_id,)).fetchone()
            return dict(row) if row else None

    def set_notify_24h_sent(self, user_id: int, sent: int = 1):
        with self._get_connection() as conn:
            conn.execute("UPDATE users SET notify_24h_sent = ? WHERE user_id = ?", (sent, user_id))
            conn.commit()

    def set_notify_expired_sent(self, user_id: int, sent: int = 1):
        with self._get_connection() as conn:
            conn.execute("UPDATE users SET notify_expired_sent = ? WHERE user_id = ?", (sent, user_id))
            conn.commit()

    def set_notify_1h_sent(self, user_id: int, sent: int = 1):
        with self._get_connection() as conn:
            conn.execute("UPDATE users SET notify_1h_sent = ? WHERE user_id = ?", (sent, user_id))
            conn.commit()

    def reset_notifications(self, user_id: int):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE users SET notify_24h_sent = 0, notify_expired_sent = 0, notify_1h_sent = 0 
                WHERE user_id = ?
            """, (user_id,))
            conn.commit()

    def get_all_users(self) -> list:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT user_id FROM users ORDER BY user_id DESC").fetchall()
            return [row['user_id'] for row in rows]

    def get_user_count(self) -> int:
        with self._get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
            return row['count']

    def is_user_banned(self, user_id: int) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return row['is_banned'] == 1 if row else False

    def ban_user(self, user_id: int):
        with self._get_connection() as conn:
            conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
            conn.commit()

    def unban_user(self, user_id: int):
        with self._get_connection() as conn:
            conn.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
            conn.commit()

    def activate_premium(self, user_id: int, days: int = 30):
        premium_until = get_moscow_time() + timedelta(days=days)
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE users SET is_premium = 1, premium_until = ?, plan = 'premium', 
                       free_until = NULL,
                       notify_24h_sent = 0, notify_expired_sent = 0, notify_1h_sent = 0 
                WHERE user_id = ?
            """, (premium_until, user_id))
            conn.commit()

    def extend_free_subscription(self, user_id: int, days: int = 3):
        moscow_now = get_moscow_time()
        new_end = moscow_now + timedelta(days=days)
        
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE users SET free_until = ?, notify_24h_sent = 0, notify_expired_sent = 0, notify_1h_sent = 0 
                WHERE user_id = ?
            """, (new_end, user_id))
            conn.commit()
        return new_end

    def disable_premium(self, user_id: int):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE users SET is_premium = 0, premium_until = NULL, plan = 'free' 
                WHERE user_id = ?
            """, (user_id,))
            conn.commit()

    def check_premium_active(self, user_id: int) -> bool:
        with self._get_connection() as conn:
            moscow_now = get_moscow_time()
            row = conn.execute("""
                SELECT (is_premium = 1 AND premium_until > ?) as is_active 
                FROM users WHERE user_id = ?
            """, (moscow_now, user_id)).fetchone()
            return row['is_active'] == 1 if row else False

    def get_user_token(self, user_id: int) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT token FROM user_tokens WHERE user_id = ?", (user_id,)).fetchone()
            return row['token'] if row else None

    def save_user_token(self, user_id: int, token: str):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_tokens (user_id, token)
                VALUES (?, ?)
            """, (user_id, token))
            conn.commit()

    def get_user_plan(self, user_id: int) -> str:
        with self._get_connection() as conn:
            row = conn.execute("SELECT plan FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return row['plan'] if row else 'free'

    def set_user_plan(self, user_id: int, plan: str):
        with self._get_connection() as conn:
            conn.execute("UPDATE users SET plan = ? WHERE user_id = ?", (plan, user_id))
            conn.commit()

    def get_device_limit(self, user_id: int) -> int:
        plan = self.get_user_plan(user_id)
        return PLAN_LIMITS.get(plan, 3)

    def register_device_fingerprint(self, user_id: int, fingerprint: str, device_name: str = None, platform: str = None, os: str = None, os_version: str = None):
        with self._get_connection() as conn:
            moscow_now = get_moscow_now_str()
            conn.execute("""
                INSERT INTO device_fingerprints (user_id, fingerprint, device_name, platform, os, os_version, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, fingerprint) DO UPDATE SET 
                    last_seen = ?,
                    device_name = COALESCE(?, device_name),
                    platform = COALESCE(?, platform),
                    os = COALESCE(?, os),
                    os_version = COALESCE(?, os_version)
            """, (user_id, fingerprint, device_name, platform, os, os_version, moscow_now, moscow_now, device_name, platform, os, os_version))
            conn.commit()
            conn.execute("""
                DELETE FROM device_fingerprints 
                WHERE last_seen < datetime(?, '-1 day')
            """, (moscow_now,))
            conn.commit()

    def get_active_devices_count(self, user_id: int) -> int:
        with self._get_connection() as conn:
            moscow_now = get_moscow_now_str()
            row = conn.execute("""
                SELECT COUNT(DISTINCT fingerprint) as count 
                FROM device_fingerprints 
                WHERE user_id = ? AND last_seen > datetime(?, '-1 day')
            """, (user_id, moscow_now)).fetchone()
            return row['count'] if row else 0

    def is_device_limit_exceeded(self, user_id: int) -> bool:
        limit = self.get_device_limit(user_id)
        count = self.get_active_devices_count(user_id)
        return count >= limit

    def device_exists(self, user_id: int, fingerprint: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT fingerprint FROM device_fingerprints 
                WHERE user_id = ? AND fingerprint = ?
            """, (user_id, fingerprint)).fetchone()
            return row is not None

    def get_devices(self, user_id: int) -> list:
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT id, fingerprint, device_name, platform, os, os_version FROM device_fingerprints 
                WHERE user_id = ? 
                ORDER BY first_seen DESC
            """, (user_id,)).fetchall()
            return [dict(row) for row in rows]

    def delete_device(self, device_id: int):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM device_fingerprints WHERE id = ?", (device_id,))
            conn.commit()

    def log_payment(self, user_id: int, amount: int):
        with self._get_connection() as conn:
            conn.execute("INSERT INTO payments_log (user_id, amount) VALUES (?, ?)", (user_id, amount))
            conn.commit()

    def log_premium_purchase(self, user_id: int, amount: int):
        with self._get_connection() as conn:
            conn.execute("INSERT INTO premium_purchases (user_id, amount) VALUES (?, ?)", (user_id, amount))
            conn.commit()

    def get_stats(self) -> dict:
        with self._get_connection() as conn:
            moscow_now = get_moscow_time()
            today = moscow_now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_ago = today - timedelta(days=7)
            month_ago = today - timedelta(days=30)
            
            today_str = today.strftime('%Y-%m-%d %H:%M:%S')
            week_ago_str = week_ago.strftime('%Y-%m-%d %H:%M:%S')
            month_ago_str = month_ago.strftime('%Y-%m-%d %H:%M:%S')

            total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            today_users = conn.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (today_str,)).fetchone()[0]
            week_users = conn.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (week_ago_str,)).fetchone()[0]
            month_users = conn.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (month_ago_str,)).fetchone()[0]

            today_payments = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payments_log WHERE date >= ?", (today_str,)).fetchone()[0]
            week_payments = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payments_log WHERE date >= ?", (week_ago_str,)).fetchone()[0]
            month_payments = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payments_log WHERE date >= ?", (month_ago_str,)).fetchone()[0]
            total_payments = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payments_log").fetchone()[0]

            today_sales = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM premium_purchases WHERE date >= ?", (today_str,)).fetchone()[0]
            week_sales = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM premium_purchases WHERE date >= ?", (week_ago_str,)).fetchone()[0]
            month_sales = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM premium_purchases WHERE date >= ?", (month_ago_str,)).fetchone()[0]
            total_sales = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM premium_purchases").fetchone()[0]

            return {
                "total_users": total_users,
                "today_users": today_users,
                "week_users": week_users,
                "month_users": month_users,
                "today_payments": today_payments,
                "week_payments": week_payments,
                "month_payments": month_payments,
                "total_payments": total_payments,
                "today_sales": today_sales,
                "week_sales": week_sales,
                "month_sales": month_sales,
                "total_sales": total_sales,
            }

    def update_subgram_linked(self, user_id: int, linked: int = 1):
        with self._get_connection() as conn:
            conn.execute("UPDATE users SET subgram_linked = ? WHERE user_id = ?", (linked, user_id))
            conn.commit()

    def is_subgram_linked(self, user_id: int) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT subgram_linked FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return row['subgram_linked'] == 1 if row else False

db = Database()