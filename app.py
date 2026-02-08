import telebot
from telebot.apihelper import ApiTelegramException
import time
import requests
import json
import sqlite3
import threading
from datetime import datetime, timedelta
from telebot import types
import re
import logging
import os
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import traceback
import io
import html

# Bot Configuration
BOT_TOKEN = "84863258:AAHR-7XmPq-2p7HlmEsDHCad-bmr0CG7jDE"
ADMIN_IDS = [8291098446, 7265489223]
CHANNEL_URL = "https://t.me/ZeroCyphh"
CHANNEL_ID = "@ZeroCyphh"
MIN_GROUP_MEMBERS = 25
DAILY_LIMIT = 100
SUPER_GROUP_IDS = []  # Official group that doesn't require verification

# API URLs and Config
MOBILE_API_URL = "https://sandhu-psi.vercel.app/get_data?mobile={num}&key=data"
AADHAR_API_URL = "http://62.122.189.157:5000/aadhar?aadhar={}"
TG_API_URL = "https://tg-info-neon.vercel.app/user-details?user={}"
PAK_API_URL = "https://pak-num-api.vercel.app/search?number={}"
RC_API_URL = "https://vehicle.cars24.team/v1/2025-09/vehicle-number/{}"
IP_API_URL = "https://ip-info.bjcoderx.workers.dev/?ip={}"
UPI_API_URL = "https://mult880.vercel.app/upi?upi_id={}"
IFSC_API_URL = "https://ifsc.razorpay.com/{}"
FF_API_URL = "http://raw.thug4ff.com/info?uid={}"
EMAIL_API_URL = "http://osintx.info/API/krobetahack.php?key=P6NW6D1&type=email&term={}"
IMCR_API_URL = "https://raju09.serv00.net/ICMR/ICMR_api.php?phone={}"
CNIC_API_URL = "https://paknuminfo-by-narcos.vercel.app/api/familyinfo?cnic={}"

# Aadhar API Config
AADHAR_COOKIES = {
    "__test": "e0615bdcb82125f7d0d63cb18e2feacb",  # update if expired
}

AADHAR_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Cache settings
CACHE_SIZE = 1000  # Increased cache size
CACHE_TTL = 3600  # 1 hour

# Thread pool for background tasks - increased workers
executor = ThreadPoolExecutor(max_workers=100)

AUTO_BACKUP_INTERVAL_SECONDS = 24 * 60 * 60

def send_safe_message(chat_id, text, reply_markup=None, reply_to_message_id=None):
    """Send message safely, trying HTML first, then plain text if it fails"""
    try:
        # First try HTML parsing
        return send_message_with_tracking(chat_id, text, reply_markup=reply_markup, 
                                        parse_mode='HTML', reply_to_message_id=reply_to_message_id)
    except Exception as e:
        logger.warning(f"HTML parse failed, trying without parse mode: {e}")
        try:
            # If HTML fails, try without parse mode
            return send_message_with_tracking(chat_id, text, reply_markup=reply_markup, 
                                            parse_mode=None, reply_to_message_id=reply_to_message_id)
        except Exception as e2:
            logger.error(f"Message sending failed completely: {e2}")
            return None

def convert_markdown_to_html(text):
    """Convert simple markdown formatting to HTML for Telegram"""
    if not text:
        return text
    
    # First escape HTML special characters
    text = html.escape(text)
    
    # Convert **bold** to <b>bold</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    
    # Convert `code` to <code>code</code>
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    # Convert [link text](url) to <a href="url">link text</a>
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    
    return text

def escape_markdown(text: str) -> str:
    """
    Escape Telegram Markdown special characters.
    """
    if text is None:
        return "N/A"
    
    # Convert to string and handle None values
    text = str(text) if text is not None else "N/A"
    
    # Escape special Markdown characters for Telegram
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

def escape_markdown2(text):
    """Alternative markdown escaping function"""
    if not text:
        return "N/A"
    text = str(text)
    return re.sub(r'([_*[\]()~`>#+-=|{}.!])', r'\\\1', text)
        
# Database connection pool with better error handling
class DBConnectionPool:
    def __init__(self, max_connections=50):  # Increased connections
        self.connections = {}
        self.max_connections = max_connections
        self.lock = threading.Lock()
        self.last_used = {}
        self.db_path = 'zerovenom_bot.db'
        
        # Ensure database directory exists and has proper permissions
        self._ensure_database_setup()
    
    def _ensure_database_setup(self):
        """Ensure database file exists and has proper permissions"""
        try:
            # Check if database exists
            if not os.path.exists(self.db_path):
                # Create database file
                conn = sqlite3.connect(self.db_path)
                conn.close()
                
            # Set proper permissions (read/write for owner, read for group/others)
            os.chmod(self.db_path, 0o644)
            
            # Also ensure the directory is writable
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            if db_dir and not os.access(db_dir, os.W_OK):
                logger.warning(f"Database directory {db_dir} is not writable")
                
        except Exception as e:
            logger.error(f"Error setting up database: {e}")
    
    def get_connection(self):
        thread_id = threading.get_ident()
        with self.lock:
            if len(self.connections) >= self.max_connections:
                self._cleanup_old_connections()
                
            if thread_id not in self.connections:
                try:
                    # Create connection with better settings
                    conn = sqlite3.connect(
                        self.db_path,
                        timeout=30.0,  # Increase timeout
                        isolation_level=None,  # Auto-commit mode
                        check_same_thread=False  # Allow multi-threaded access
                    )
                    
                    # Configure connection settings
                    conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
                    conn.execute("PRAGMA synchronous=NORMAL")  # Balance between safety and speed
                    conn.execute("PRAGMA cache_size=10000")  # Increase cache size
                    conn.execute("PRAGMA temp_store=MEMORY")  # Use memory for temp storage
                    conn.execute("PRAGMA mmap_size=268435456")  # 256MB memory mapping
                    conn.row_factory = sqlite3.Row
                    
                    self.connections[thread_id] = conn
                    
                except Exception as e:
                    logger.error(f"Error creating database connection: {e}")
                    # Fallback to basic connection
                    conn = sqlite3.connect(self.db_path)
                    conn.row_factory = sqlite3.Row
                    self.connections[thread_id] = conn
            
            self.last_used[thread_id] = time.time()
            return self.connections[thread_id]

    def _cleanup_old_connections(self):
        current_time = time.time()
        idle_connections = [tid for tid, last_time in self.last_used.items() 
                          if current_time - last_time > 180]  # 3 minutes
        
        for tid in idle_connections:
            if tid in self.connections:
                try:
                    self.connections[tid].close()
                except:
                    pass
                del self.connections[tid]
                del self.last_used[tid]

    def close_all(self):
        with self.lock:
            for conn in self.connections.values():
                try:
                    conn.close()
                except:
                    pass
            self.connections.clear()
            self.last_used.clear()

# Initialize the connection pool
db_pool = DBConnectionPool()

# Initialize bot with a larger threaded pool
bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=50)

# Retry mechanism for Telegram API calls
def telegram_api_retry(func, *args, **kwargs):
    """Wrapper function to handle Telegram API retries"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except ApiTelegramException as e:
            if e.error_code == 429:  # Too Many Requests
                retry_after = e.result_json.get('parameters', {}).get('retry_after', 5)
                logger.warning(f"Rate limited. Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
            else:
                raise
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            logger.warning(f"API call failed (attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(1)
    
    return None

def send_message_with_tracking(chat_id, text, reply_markup=None, parse_mode=None, reply_to_message_id=None):
    """Send message and store it for potential deletion later. Send long responses as files."""
    try:
        # Check if message is too long (Telegram limit is 4096 characters)
        if len(text) > 3500:  # Lower threshold to send as file
            # Create a temporary file with the content
            import tempfile
            import os
            from io import StringIO

            # Create a temporary file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
                temp_file.write(text)
                temp_file_path = temp_file.name

            try:
                # Send the file
                with open(temp_file_path, 'rb') as file:
                    message = telegram_api_retry(bot.send_document, chat_id, file,
                                               caption="🔍 ZeroCyph OSINT Results",
                                               reply_markup=reply_markup,
                                               reply_to_message_id=reply_to_message_id)
                return message
            finally:
                # Clean up the temporary file
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
        else:
            # Message is within limit, send normally
            message = telegram_api_retry(bot.send_message, chat_id, text,
                                       reply_markup=reply_markup, parse_mode=parse_mode,
                                       reply_to_message_id=reply_to_message_id)
            return message
    except Exception as e:
        logger.error(f"Error sending message to {chat_id}: {e}")
        return None

def edit_message_with_tracking(chat_id, message_id, text, reply_markup=None, parse_mode=None):
    """Edit message and store it for potential deletion later"""
    try:
        message = telegram_api_retry(bot.edit_message_text, text, chat_id, message_id,
                                   reply_markup=reply_markup, parse_mode=parse_mode)
        return message
    except Exception as e:
        logger.error(f"Error editing message {message_id} in chat {chat_id}: {e}")
        return None

# Database setup with optimized schema and better error handling
def init_db():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = db_pool.get_connection()
            c = conn.cursor()
            
            # Enable foreign keys
            c.execute("PRAGMA foreign_keys = ON")
            
            # Users table
            c.execute('''CREATE TABLE IF NOT EXISTS users (
                         user_id INTEGER PRIMARY KEY,
                         username TEXT,
                         first_name TEXT,
                         last_name TEXT,
                         joined_date TEXT,
                         last_search TEXT,
                         daily_searches INTEGER DEFAULT 0,
                         search_date TEXT,
                         is_verified INTEGER DEFAULT 0,
                         has_seen_welcome INTEGER DEFAULT 0,
                         is_approved_private INTEGER DEFAULT 0
                         )''')
            
            # Groups table
            c.execute('''CREATE TABLE IF NOT EXISTS groups (
                         group_id INTEGER PRIMARY KEY,
                         group_title TEXT,
                         member_count INTEGER,
                         added_date TEXT,
                         is_banned INTEGER DEFAULT 0,
                         no_member_limit INTEGER DEFAULT 0,
                         group_username TEXT,
                         group_invite_link TEXT
                         )''')
            
            # Searches table with index for performance
            c.execute('''CREATE TABLE IF NOT EXISTS searches (
                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER,
                         search_type TEXT,
                         query TEXT,
                         timestamp TEXT,
                         FOREIGN KEY (user_id) REFERENCES users (user_id)
                         )''')
            
            
            # Create indices for frequently queried fields
            c.execute('CREATE INDEX IF NOT EXISTS idx_searches_user_id ON searches(user_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_searches_timestamp ON searches(timestamp)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_users_verified ON users(is_verified)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_users_approved_private ON users(is_approved_private)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_groups_no_member_limit ON groups(no_member_limit)')
            
            # Check if groups table has the new columns
            c.execute("PRAGMA table_info(groups)")
            columns = [column[1] for column in c.fetchall()]
            
            if 'group_username' not in columns:
                c.execute('ALTER TABLE groups ADD COLUMN group_username TEXT')
            
            if 'group_invite_link' not in columns:
                c.execute('ALTER TABLE groups ADD COLUMN group_invite_link TEXT')
            
            # Commit and close
            conn.commit()
            logger.info("Database initialized successfully")
            return True
            
        except sqlite3.OperationalError as e:
            logger.error(f"Database initialization error (attempt {attempt+1}/{max_retries}): {e}")
            if "readonly database" in str(e).lower():
                # Try to fix database permissions
                try:
                    if os.path.exists('zerovenom_bot.db'):
                        os.chmod('zerovenom_bot.db', 0o644)
                    logger.info("Attempted to fix database permissions")
                except:
                    pass
            if attempt == max_retries - 1:
                # Last attempt failed, try to recreate database
                try:
                    if os.path.exists('zerovenom_bot.db'):
                        os.remove('zerovenom_bot.db')
                    logger.info("Removed corrupted database, will recreate on next run")
                except:
                    pass
            time.sleep(1)  # Wait before retry
        except Exception as e:
            logger.error(f"Unexpected error in database initialization: {e}")
            if attempt == max_retries - 1:
                return False
            time.sleep(1)
    
    return False

# Database helper functions with better error handling and retries
def execute_db_query(query, params=None, fetch_one=False, fetch_all=False, commit=False):
    """Execute a database query with error handling and retries"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = db_pool.get_connection()
            c = conn.cursor()
            
            if params:
                c.execute(query, params)
            else:
                c.execute(query)
            
            result = None
            if fetch_one:
                result = c.fetchone()
            elif fetch_all:
                result = c.fetchall()
            
            if commit:
                conn.commit()
            
            return result
            
        except sqlite3.OperationalError as e:
            logger.error(f"Database query error (attempt {attempt+1}/{max_retries}): {e}")
            if "readonly database" in str(e).lower():
                # Try to fix database permissions
                try:
                    os.chmod('zerovenom_bot.db', 0o644)
                    logger.info("Attempted to fix database permissions")
                except:
                    pass
            if attempt == max_retries - 1:
                raise
            time.sleep(0.5)  # Wait before retry
        except Exception as e:
            logger.error(f"Unexpected database error: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(0.5)
    
    return None

def add_user(user_id, username, first_name, last_name):
    try:
        # Check if user exists
        user = execute_db_query(
            'SELECT user_id FROM users WHERE user_id = ?', 
            (user_id,), 
            fetch_one=True
        )
        
        if not user:
            # Insert new user
            execute_db_query(
                '''INSERT INTO users 
                   (user_id, username, first_name, last_name, joined_date, search_date, daily_searches, is_verified, has_seen_welcome, is_approved_private)
                   VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0)''', 
                (user_id, username, first_name, last_name, 
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 datetime.now().strftime("%Y-%m-%d")),
                commit=True
            )
        else:
            # Update existing user
            execute_db_query(
                '''UPDATE users SET 
                   username = ?, first_name = ?, last_name = ?
                   WHERE user_id = ? AND (username != ? OR first_name != ? OR last_name != ?)''', 
                (username, first_name, last_name, user_id, username, first_name, last_name),
                commit=True
            )
        
        logger.info(f"User {user_id} added/updated successfully")
        
    except Exception as e:
        logger.error(f"Error handling user: {e}")
        # Fallback: Try to create a simple connection
        try:
            conn = sqlite3.connect('zerovenom_bot.db')
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO users 
                         (user_id, username, first_name, last_name, joined_date, search_date, daily_searches, is_verified, has_seen_welcome, is_approved_private)
                         VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0)''', 
                      (user_id, username, first_name, last_name, 
                       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            conn.close()
        except Exception as e2:
            logger.error(f"Fallback user creation also failed: {e2}")

def get_user(user_id):
    try:
        user = execute_db_query(
            'SELECT * FROM users WHERE user_id = ?', 
            (user_id,), 
            fetch_one=True
        )
        
        if not user:
            # Auto-create user if not found
            try:
                # Get user info from bot API
                user_info = telegram_api_retry(bot.get_chat_member, user_id, user_id).user
                add_user(user_id, user_info.username, user_info.first_name, user_info.last_name)
                # Get the newly created user
                user = execute_db_query(
                    'SELECT * FROM users WHERE user_id = ?', 
                    (user_id,), 
                    fetch_one=True
                )
            except:
                # If we can't get info, create with basic info
                add_user(user_id, "", "User", "")
                user = execute_db_query(
                    'SELECT * FROM users WHERE user_id = ?', 
                    (user_id,), 
                    fetch_one=True
                )
        return user
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        return None

def is_user_verified(user_id):
    try:
        result = execute_db_query(
            'SELECT is_verified FROM users WHERE user_id = ?', 
            (user_id,), 
            fetch_one=True
        )
        
        if not result:
            # Auto-create user if not found
            add_user(user_id, "", "User", "")
            return False
        return result[0] == 1
    except Exception as e:
        logger.error(f"Error checking verification: {e}")
        return False

def is_user_approved_private(user_id):
    """Check if user is approved to use bot in private"""
    try:
        result = execute_db_query(
            'SELECT is_approved_private FROM users WHERE user_id = ?', 
            (user_id,), 
            fetch_one=True
        )
        
        if not result:
            # Auto-create user if not found
            add_user(user_id, "", "User", "")
            return False
        return result[0] == 1
    except Exception as e:
        logger.error(f"Error checking private approval: {e}")
        return False

def is_user_in_channel(user_id):
    """Check if user is a member of the channel"""
    try:
        member = telegram_api_retry(bot.get_chat_member, CHANNEL_ID, user_id)
        # Check if the user is a member, admin, or creator
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking channel membership for user {user_id}: {e}")
        return False

def verify_user(user_id):
    if is_user_in_channel(user_id):
        # Update database
        execute_db_query(
            'UPDATE users SET is_verified = 1 WHERE user_id = ?',
            (user_id,),
            commit=True
        )
        logger.info(f"User {user_id} verified successfully")
        return True
    return False

def approve_user_private(user_id):
    """Approve user to use bot in private"""
    try:
        execute_db_query(
            'UPDATE users SET is_approved_private = 1 WHERE user_id = ?',
            (user_id,),
            commit=True
        )
        logger.info(f"User {user_id} approved for private use")
        return True
    except Exception as e:
        logger.error(f"Error approving user for private use: {e}")
        return False

def demote_user_private(user_id):
    """Demote user from using bot in private"""
    try:
        execute_db_query(
            'UPDATE users SET is_approved_private = 0 WHERE user_id = ?',
            (user_id,),
            commit=True
        )
        logger.info(f"User {user_id} demoted from private use")
        return True
    except Exception as e:
        logger.error(f"Error demoting user from private use: {e}")
        return False

def add_group(group_id, group_title, member_count):
    try:
        # Get group username and invite link if possible
        group_username = None
        group_invite_link = None
        
        try:
            chat = telegram_api_retry(bot.get_chat, group_id)
            if chat.username:
                group_username = chat.username
                group_invite_link = f"https://t.me/{chat.username}"
            else:
                # Try to get invite link if bot is admin
                try:
                    bot_admins = telegram_api_retry(bot.get_chat_administrators, group_id)
                    is_admin = any(admin.user.id == bot.get_me().id for admin in bot_admins)
                    if is_admin:
                        group_invite_link = telegram_api_retry(bot.export_chat_invite_link, group_id)
                except:
                    pass
        except Exception as e:
            logger.error(f"Error getting group info: {e}")
        
        execute_db_query(
            '''INSERT OR REPLACE INTO groups 
               (group_id, group_title, member_count, added_date, group_username, group_invite_link)
               VALUES (?, ?, ?, ?, ?, ?)''', 
            (group_id, group_title, member_count, 
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             group_username, group_invite_link),
            commit=True
        )
        logger.info(f"Group {group_id} added successfully")
    except Exception as e:
        logger.error(f"Error adding group: {e}")

def is_group_banned(group_id):
    try:
        result = execute_db_query(
            'SELECT is_banned FROM groups WHERE group_id = ?', 
            (group_id,), 
            fetch_one=True
        )
        return result and result[0] == 1
    except Exception as e:
        logger.error(f"Error checking ban status: {e}")
        return False

def is_group_member_limit_removed(group_id):
    """Check if group has member limit removed"""
    try:
        result = execute_db_query(
            'SELECT no_member_limit FROM groups WHERE group_id = ?', 
            (group_id,), 
            fetch_one=True
        )
        return result and result[0] == 1
    except Exception as e:
        logger.error(f"Error checking member limit removal: {e}")
        return False

def ban_group(group_id):
    try:
        execute_db_query(
            'UPDATE groups SET is_banned = 1 WHERE group_id = ?', 
            (group_id,),
            commit=True
        )
        logger.info(f"Group {group_id} banned successfully")
        return True
    except Exception as e:
        logger.error(f"Error banning group: {e}")
        return False

def remove_group_member_limit(group_id):
    """Remove member limit requirement for a group"""
    try:
        execute_db_query(
            'UPDATE groups SET no_member_limit = 1 WHERE group_id = ?', 
            (group_id,),
            commit=True
        )
        logger.info(f"Member limit removed for group {group_id}")
        return True
    except Exception as e:
        logger.error(f"Error removing member limit for group: {e}")
        return False

def check_daily_limit(user_id):
    try:
        user = get_user(user_id)
        
        if not user:
            return False, "User not found"
        
        daily_searches = user[6]  # daily_searches column
        search_date = user[7]  # search_date column
        
        # Check daily limit
        today = datetime.now().strftime("%Y-%m-%d")
        if search_date != today:
            # Reset daily counter
            execute_db_query(
                'UPDATE users SET daily_searches = 0, search_date = ? WHERE user_id = ?', 
                (today, user_id),
                commit=True
            )
            daily_searches = 0
        
        if daily_searches >= DAILY_LIMIT:
            return False, f"Daily limit of {DAILY_LIMIT} searches exceeded"
        
        return True, "OK"
    except Exception as e:
        logger.error(f"Error checking daily limit: {e}")
        return False, "Error checking limit"

def update_search_stats(user_id, search_type, query):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today = datetime.now().strftime("%Y-%m-%d")
        
        execute_db_query(
            '''UPDATE users SET 
               last_search = ?,
               daily_searches = daily_searches + 1,
               search_date = ?
               WHERE user_id = ?''', 
            (now, today, user_id),
            commit=True
        )
        
        execute_db_query(
            'INSERT INTO searches (user_id, search_type, query, timestamp) VALUES (?, ?, ?, ?)',
            (user_id, search_type, query, now),
            commit=True
        )
        
        logger.info(f"Search stats updated for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating search stats: {e}")
        return False



# Utility functions
def clean_phone_number(number):
    static_regex = re.compile(r'[^\d]')
    cleaned = static_regex.sub('', number)
    if cleaned.startswith('91') and len(cleaned) == 12:
        cleaned = cleaned[2:]
    return cleaned

def format_cnic(cnic):
    """Format CNIC number with proper dashes"""
    # Remove all non-digits
    cleaned = re.sub(r'[^\d]', '', cnic)
    
    # Check if it's a valid CNIC length (13 digits)
    if len(cleaned) == 13:
        # Format as XXXXX-XXXXXXX-X
        return f"{cleaned[:5]}-{cleaned[5:12]}-{cleaned[12]}"
    else:
        # Return as-is if not 13 digits
        return cnic

def remove_unwanted_fields(data):
    """Remove unwanted fields from API response data"""
    if isinstance(data, dict):
        # Create a new dictionary without unwanted fields
        clean_data = {}
        for key, value in data.items():
            # Check both the original key and lowercase version for unwanted fields
            # Include both case-sensitive and case-insensitive checks
            cleaned_key = key.lower()
            if (cleaned_key not in ['channel', 'dev', 'developer', 'credit', 'source', 'api_source', 'note']
                and key not in ['Developer', 'Api_BY', 'Channel']):
                # Recursively process nested dictionaries or lists
                if isinstance(value, dict):
                    clean_data[key] = remove_unwanted_fields(value)
                elif isinstance(value, list):
                    clean_data[key] = [remove_unwanted_fields(item) if isinstance(item, dict) else item for item in value]
                else:
                    clean_data[key] = value
        return clean_data
    return data

# Cache for keyboards to avoid recreation
@lru_cache(maxsize=2)
def create_main_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    join_btn = types.InlineKeyboardButton("🔥 Join Channel", url=CHANNEL_URL)
    add_btn = types.InlineKeyboardButton("➕ Add to Group", 
                                        url=f"https://t.me/{bot.get_me().username}?startgroup=true")
    keyboard.add(join_btn, add_btn)
    return keyboard

@lru_cache(maxsize=1)
def create_verification_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    join_btn = types.InlineKeyboardButton("📢 Join Channel First", url=CHANNEL_URL)
    verify_btn = types.InlineKeyboardButton("✅ Verify & Continue", callback_data="verify")
    keyboard.add(join_btn)
    keyboard.add(verify_btn)
    return keyboard

# Keyboard for making bot admin
def create_admin_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    promote_btn = types.InlineKeyboardButton("👑 Make Bot Admin", callback_data="make_admin")
    keyboard.add(promote_btn)
    return keyboard

# Result cache
search_cache = {}

def get_cached_result(search_type, query):
    cache_key = f"{search_type}:{query}"
    if cache_key in search_cache:
        result, timestamp = search_cache[cache_key]
        if time.time() - timestamp < CACHE_TTL:
            return result
        del search_cache[cache_key]
    return None

def cache_result(search_type, query, result):
    if len(search_cache) > CACHE_SIZE:
        items_to_remove = int(CACHE_SIZE * 0.2)
        sorted_keys = sorted(search_cache.keys(), key=lambda k: search_cache[k][1])
        for key in sorted_keys[:items_to_remove]:
            del search_cache[key]
    
    cache_key = f"{search_type}:{query}"
    search_cache[cache_key] = (result, time.time())

# API functions with retry logic
def search_mobile(number):
    cached_result = get_cached_result("mobile", number)
    if cached_result:
        return cached_result

    try:
        response = requests.get(MOBILE_API_URL.format(num=number), timeout=8)
        json_response = response.json()

        # Debug logging
        logger.info(f"Mobile API Response: {json.dumps(json_response)}")

        # Handle the new API response format with header, total_records, and data keys
        if isinstance(json_response, dict):
            # Remove unwanted fields mentioned by the user
            json_response.pop('Developer', None)
            json_response.pop('developer', None)
            json_response.pop('credit', None)
            # Remove other potential unwanted fields
            json_response.pop('Api_BY', None)
            json_response.pop('Channel', None)  # Remove the Channel field as requested
            json_response.pop('channel', None)
            json_response.pop('dev', None)
            # Remove the specific fields mentioned in the example response (no credits)
            json_response.pop('developer', None)
            json_response.pop('owner', None)
            json_response.pop('powered_by', None)

            # Handle the new API response format with header, total_records, and data keys
            if 'data' in json_response and isinstance(json_response['data'], dict) and 'result' in json_response['data']:
                # The new API returns results in a nested structure: {"data": {"result": [...]}}
                processed_response = {
                    "success": json_response['data'].get('success', True),
                    "data": json_response['data']['result']
                }
                cache_result("mobile", number, processed_response)
                return processed_response
            # Handle the new API response format with "result" key containing array (as per your example)
            elif 'result' in json_response and isinstance(json_response['result'], list):
                # The new API returns results in a 'result' array with status field
                processed_response = {
                    "success": json_response.get('status', True),
                    "data": json_response['result']
                }
                cache_result("mobile", number, processed_response)
                return processed_response
            # Handle the new API response format with data1, data2, data3, etc.
            elif any(key.startswith('data') for key in json_response.keys()):
                # This is the new API format with data1, data2, data3, etc.
                data_list = []
                for key in json_response.keys():
                    if key.startswith('data'):
                        data_item = json_response[key]
                        if isinstance(data_item, dict):
                            # Add this data item to our list
                            data_list.append(data_item)

                # Create a new response with the expected format
                processed_response = {
                    "success": json_response.get('status', 'success') == 'success',
                    "data": data_list
                }
                cache_result("mobile", number, processed_response)
                return processed_response
            # Handle the new API response format with "data" key containing array
            elif 'data' in json_response and isinstance(json_response['data'], list):
                # The API returns results in a 'data' array (new format)
                processed_response = {"success": True, "data": json_response['data']}
                cache_result("mobile", number, processed_response)
                return processed_response
            # Handle the new API response format with "data" key containing array
            elif 'data' in json_response and isinstance(json_response['data'], dict):
                # The API returns results in a 'data' dict with 'result' array inside
                if 'result' in json_response['data'] and isinstance(json_response['data']['result'], list):
                    processed_response = {"success": json_response.get('success', True), "data": json_response['data']['result']}
                    cache_result("mobile", number, processed_response)
                    return processed_response
                else:
                    # If data is a dict but doesn't have result array, wrap it in a list
                    processed_response = {"success": json_response.get('success', True), "data": [json_response['data']]}
                    cache_result("mobile", number, processed_response)
                    return processed_response
            # Ensure the result is in the expected format for other APIs
            elif 'result' in json_response and isinstance(json_response['result'], list):
                # The API returns results in a 'result' array
                # Return the data in the expected format
                processed_response = {"success": json_response.get('success', True), "data": json_response['result']}
                cache_result("mobile", number, processed_response)
                return processed_response
            else:
                # If the response doesn't have the expected structure, return as is after cleaning
                cache_result("mobile", number, json_response)
                return json_response

        # Return the cleaned JSON response
        cache_result("mobile", number, json_response)
        return json_response
    except Exception as e:
        logger.error(f"Mobile API error: {e}")
        return {"success": False, "data": []}

def search_aadhar(aadhar):
    cached_result = get_cached_result("aadhar", aadhar)
    if cached_result:
        return cached_result

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Format URL with the given aadhar/id number
            url = AADHAR_API_URL.format(aadhar)
            logger.info(f"Aadhar API call (attempt {attempt+1}/{max_retries}): {url}")

            # Plain GET (no cookies, no headers, no params)
            response = requests.get(url, timeout=15)

            # Log the response for debugging
            logger.info(f"Aadhar API response status: {response.status_code}")
            logger.info(f"Aadhar API response preview: {response.text[:200]}")

            if response.status_code == 200:
                try:
                    json_response = response.json()

                    # Debug logging
                    logger.info(f"Aadhar API Response: {json.dumps(json_response)}")

                    # Remove unwanted fields from the response
                    if isinstance(json_response, dict):
                        # Remove unwanted fields mentioned by the user
                        json_response.pop('Developer', None)
                        json_response.pop('developer', None)
                        # Remove other potential unwanted fields
                        json_response.pop('Api_BY', None)
                        json_response.pop('Channel', None)
                        json_response.pop('channel', None)
                        json_response.pop('dev', None)
                        json_response.pop('credit', None)

                    # Return the cleaned JSON response
                    cache_result("aadhar", aadhar, json_response)
                    return json_response

                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from Aadhar API: {response.text[:200]}")
                    if attempt == max_retries - 1:
                        return {"success": False, "data": []}
            else:
                logger.error(f"Aadhar API HTTP error: {response.status_code}")
                if attempt == max_retries - 1:
                    return {"success": False, "data": []}

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Aadhar API connection error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return {"success": False, "data": []}

        except Exception as e:
            logger.error(f"Aadhar API error: {e}")
            if attempt == max_retries - 1:
                return {"success": False, "data": []}

    return {"success": False, "data": []}

def search_telegram(user_id):
    cached_result = get_cached_result("telegram", user_id)
    if cached_result:
        return cached_result
    
    try:
        response = requests.get(TG_API_URL.format(user_id), timeout=10)
        result = response.json()
        
        cache_result("telegram", user_id, result)
        return result
    except Exception as e:
        logger.error(f"Telegram API error: {e}")
        return {"success": False, "data": {}}

def search_pakistan_number(number):
    cached_result = get_cached_result("pakistan", number)
    if cached_result:
        return cached_result
    
    try:
        response = requests.get(PAK_API_URL.format(number), timeout=10)
        result = response.json()
        
        cache_result("pakistan", number, result)
        return result
    except Exception as e:
        logger.error(f"Pakistan API error: {e}")
        return {"success": False, "data": []}

def search_vehicle_rc(rc_number):    
    cached_result = get_cached_result("vehicle", rc_number)    
    if cached_result:    
        return cached_result    

    headers = {
        'authority': 'vehicle.cars24.team',
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9',
        'authorization': 'Basic YzJiX2Zyb250ZW5kOko1SXRmQTk2bTJfY3lRVk00dEtOSnBYaFJ0c0NtY1h1',
        'device_category': 'mSite',
        'origin': 'https://www.cars24.com',
        'origin_source': 'c2b-website',
        'platform': 'rto',
        'referer': 'https://www.cars24.com/',
        'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'cross-site',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
    }

    try:    
        response = requests.get(RC_API_URL.format(rc_number), headers=headers, timeout=10)    
        result = response.json()    

        if isinstance(result, dict) and result.get("success") and result.get("detail"):    
            detail = result["detail"]    
            detail['success'] = True    
            cache_result("vehicle", rc_number, detail)    
            return detail    
        else:    
            return {"success": False, "data": {}}    
    except Exception as e:    
        logger.error(f"Vehicle RC API error: {e}")    
        return {"success": False, "data": {}}

def search_ip_info(ip_address):
    """Search for IP information"""
    try:
        response = requests.get(IP_API_URL.format(ip_address), timeout=10)
        result = response.json()
        
        # Filter out dev and channel fields
        if "dev" in result:
            del result["dev"]
        if "channel" in result:
            del result["channel"]
            
        return result
    except Exception as e:
        logger.error(f"IP API error: {e}")
        return {"success": False, "error": str(e)}

def search_upi_info(upi_id):
    """Search for UPI information"""
    cached_result = get_cached_result("upi", upi_id)
    if cached_result:
        return cached_result
    
    try:
        response = requests.get(UPI_API_URL.format(upi_id), timeout=10)
        result = response.json()
        
        cache_result("upi", upi_id, result)
        return result
    except Exception as e:
        logger.error(f"UPI API error: {e}")
        return {"success": False, "error": str(e)}

def search_ifsc_info(ifsc_code):
    """Search for IFSC code information"""
    cached_result = get_cached_result("ifsc", ifsc_code)
    if cached_result:
        return cached_result
    
    try:
        response = requests.get(IFSC_API_URL.format(ifsc_code), timeout=10)
        result = response.json()
        
        cache_result("ifsc", ifsc_code, result)
        return result
    except Exception as e:
        logger.error(f"IFSC API error: {e}")
        return {"success": False, "error": str(e)}

def search_email_info(email):
    """Search for email to number information"""
    cached_result = get_cached_result("email", email)
    if cached_result:
        return cached_result
    
    try:
        response = requests.get(EMAIL_API_URL.format(email), timeout=10)
        result = response.json()
        
        cache_result("email", email, result)
        return result
    except Exception as e:
        logger.error(f"Email API error: {e}")
        return {"success": False, "error": str(e)}

def search_imcr(phone):
    """Search for ICMR information"""
    cached_result = get_cached_result("imcr", phone)
    if cached_result:
        return cached_result
    
    try:
        response = requests.get(IMCR_API_URL.format(phone), timeout=10)
        result = response.json()
        
        # Remove the credit field from the response
        if isinstance(result, dict) and 'credit' in result:
            result.pop('credit', None)
        
        cache_result("imcr", phone, result)
        return result
    except Exception as e:
        logger.error(f"IMCR API error: {e}")
        return {"success": False, "error": str(e)}

def search_freefire(uid):
    """Search for Free Fire user information"""
    cached_result = get_cached_result("freefire", uid)
    if cached_result:
        return cached_result
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(FF_API_URL.format(uid), timeout=15)
            response.raise_for_status()  # Raise an exception for bad status codes
            result = response.json()
            
            cache_result("freefire", uid, result)
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Free Fire API request error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                # Hide the actual API URL in the error message
                error_msg = f"{e.__class__.__name__}: {str(e).split(':', 1)[-1].strip()}" if ':' in str(e) else str(e)
                return {"success": False, "error": error_msg, "data": []}
            time.sleep(1)  # Wait before retry
        except ValueError as e:  # JSON decode error
            logger.error(f"Free Fire API JSON decode error: {e}")
            return {"success": False, "error": "Invalid JSON response", "data": []}
        except Exception as e:
            logger.error(f"Free Fire API error: {e}")
            return {"success": False, "error": str(e), "data": []}

def search_cnic_info(cnic):
    """Search for CNIC family information"""
    cached_result = get_cached_result("cnic", cnic)
    if cached_result:
        return cached_result
    
    try:
        response = requests.get(CNIC_API_URL.format(cnic), timeout=10)
        result = response.json()
        
        cache_result("cnic", cnic, result)
        return result
    except Exception as e:
        logger.error(f"CNIC API error: {e}")
        return {"success": False, "error": str(e)}

def format_response(data, search_type):
    if search_type == "mobile" or search_type == "aadhar" or search_type == "email" or search_type == "imcr":
        # Debug logging to see the data structure
        logger.info(f"Raw Response: {json.dumps(data)}")

        # Handle different response formats
        results = []

        # Case 1: Direct list response
        if isinstance(data, list):
            results = data
            # Remove unwanted fields from each result in the list
            results = [remove_unwanted_fields(result) for result in results if isinstance(result, dict)]

        # Case 2: Dictionary with 'data' key containing a list
        elif isinstance(data, dict) and 'data' in data and isinstance(data['data'], list):
            results = [remove_unwanted_fields(result) for result in data['data'] if isinstance(result, dict)]

        # Case 3: Dictionary with other structure but still has data
        elif isinstance(data, dict) and 'data' in data:
            # If data is not a list, try to convert it
            if isinstance(data['data'], dict):
                results = [remove_unwanted_fields(data['data'])]
            else:
                results = [remove_unwanted_fields(result) for result in data['data'] if isinstance(result, dict)]

        # Case 4: Dictionary without 'data' key but has other keys
        elif isinstance(data, dict) and len(data) > 0:
            # Remove unwanted fields from the data
            cleaned_data = remove_unwanted_fields(data)
            # Check if it has a success flag
            if 'success' in cleaned_data and cleaned_data.get('success', False):
                # Create a list with all keys except 'success'
                result_dict = {k: v for k, v in cleaned_data.items() if k != 'success'}
                results = [result_dict]
            else:
                # Just use the entire dict as a single result
                results = [cleaned_data]

        # Debug logging
        logger.info(f"Processed Results: {json.dumps(results)}")

        if not results or not isinstance(results, list) or len(results) == 0:
            logger.info(f"No valid results found for {search_type}")
            return ["❌ No results found"]

        # Filter out non-dictionary results
        results = [r for r in results if isinstance(r, dict) and len(r) > 0]

        if not results:
            logger.info(f"No valid dictionary results found for {search_type}")
            return ["❌ No valid results found"]

        total_results = len(results)

        # Create a single formatted string containing all results
        all_results_content = f"🔍 ZeroCyph OSINT Results\n\n"

        # Add raw JSON section for all results
        all_results_content += f"👤 **{search_type.capitalize()} Search Results**\n\n"
        # Create a clean version of results without unwanted fields for JSON display
        clean_results = []
        for result in results:
            clean_result = remove_unwanted_fields(result)
            clean_results.append(clean_result)
        all_results_content += "```json\n"
        all_results_content += json.dumps(clean_results, indent=1)
        all_results_content += "\n```\n\n"

        # Add all individual results to the single content
        for i, result in enumerate(results, 1):
            # Remove unwanted fields from the individual result
            clean_result = remove_unwanted_fields(result)

            # Create a formatted result with all fields from the API
            formatted = f"🔍 **Result {i}/{total_results}**\n\n"

            # Define field mappings for better UI
            if search_type == "mobile":
                field_mapping = {
                    "mobile": "📱 Mobile",
                    "name": "👤 Name",
                    "father_name": "👨‍👦 Father Name",
                    "address": "🏠 Address",
                    "alt_mobile": "📞 Alt Mobile",
                    "circle": "🌐 Circle",
                    "id_number": "🆔 ID Number",
                    "email": "📧 Email",
                    "id": "🆔 ID"
                }
            elif search_type == "email":
                field_mapping = {
                    "id": "🆔 ID",
                    "mobile": "📱 Mobile",
                    "name": "👤 Name",
                    "father_name": "👨‍👦 Father_Name",
                    "address": "🏠 Address",
                    "alt_mobile": "📞 Alt_Mobile",
                    "circle": "🌐 Circle",
                    "id_number": "🆔 Id_Number",
                    "email": "📧 Email"
                }
            elif search_type == "imcr":
                field_mapping = {
                    "name": "👤 Name",
                    "fathersName": "👨‍👦 Father's Name",
                    "phoneNumber": "📱 Phone Number",
                    "aadharNumber": "🆔 Aadhar Number",
                    "age": "🎂 Age",
                    "gender": "⚧ Gender",
                    "address": "🏠 Address",
                    "district": "🏛️ District",
                    "pincode": "📮 Pincode",
                    "state": "🗺️ State",
                    "town": "🏘️ Town"
                }
            else:  # aadhar
                field_mapping = {
                    "aadhar": "🆔 Aadhar",
                    "name": "👤 Name",
                    "fname": "👨‍👦 Father",
                    "mobile": "📱 Mobile",
                    "alt_mobile": "📞 Alt Mobile",
                    "address": "🏠 Address",
                    "circle": "🌐 Circle",
                    "email": "✉️ Email"
                }

            # Add all fields from the API response with proper formatting
            for key, value in clean_result.items():
                # Skip empty keys
                if key is None or key == "":
                    continue

                # Skip unwanted keys
                if key.lower() in ['channel', 'dev', 'developer', 'credit', 'source', 'api_source', 'note']:
                    continue

                # Get the display label for this field
                label = field_mapping.get(key, key.title())

                # Escape markdown characters for the label
                escaped_label = escape_markdown(label)

                # Format the value - clean up any unwanted characters
                if value is None or value == "":
                    formatted_value = "N/A"
                else:
                    # Clean up the value - remove excessive special characters
                    cleaned_value = str(value)
                    # Replace multiple exclamation marks with single space
                    cleaned_value = re.sub(r'!+', ' ', cleaned_value)
                    # Remove extra spaces
                    cleaned_value = re.sub(r'\s+', ' ', cleaned_value).strip()
                    formatted_value = escape_markdown(cleaned_value)

                formatted += f"**{escaped_label}:** {formatted_value}\n"

            all_results_content += formatted.strip() + "\n\n" + "━━━━━━━━━━━━━━━━━━━━\n\n"

        # Remove the last divider
        if all_results_content.endswith("━━━━━━━━━━━━━━━━━━━━\n\n"):
            all_results_content = all_results_content[:-22]

        return [all_results_content]  # Return as single item in array
    
    elif search_type == "telegram":
        if not data.get('success', False):
            return ["❌ No Telegram user data found"]

        user_data = data.get('data', {})

        # Create a single formatted string containing all results
        all_results_content = f"🔍 ZeroCyph OSINT Results\n\n"

        # Create formatted response with raw JSON section
        all_results_content += f"👤 **Telegram User Information**\n\n"
        all_results_content += "```json\n"
        all_results_content += json.dumps(data, indent=1)
        all_results_content += "\n```\n\n"

        all_results_content += f"""
🔍 **Telegram User Information**

🆔 **User ID:** {escape_markdown(str(user_data.get('id', 'N/A')))}
👤 **Name:** {escape_markdown(f"{user_data.get('first_name', 'N/A')} {user_data.get('last_name', '')}")}
🤖 **Bot:** {'Yes' if user_data.get('is_bot', False) else 'No'}
✅ **Active:** {'Yes' if user_data.get('is_active', False) else 'No'}
📅 **First Message:** {escape_markdown(str(user_data.get('first_msg_date', 'N/A')))}
📅 **Last Message:** {escape_markdown(str(user_data.get('last_msg_date', 'N/A')))}
👥 **Groups Admin:** {escape_markdown(str(user_data.get('adm_in_groups', 0)))}
📊 **Total Groups:** {escape_markdown(str(user_data.get('total_groups', 0)))}
💬 **Total Messages:** {escape_markdown(str(user_data.get('total_msg_count', 0)))}
📝 **Group Messages:** {escape_markdown(str(user_data.get('msg_in_groups_count', 0)))}
🔄 **Names Count:** {escape_markdown(str(user_data.get('names_count', 0)))}
🔄 **Usernames Count:** {escape_markdown(str(user_data.get('usernames_count', 0)))}
"""
        return [all_results_content]
    
    elif search_type == "pakistan":
        results = data.get('results', [])
        if not results:
            return ["❌ No Pakistan number data found"]

        # Create a single formatted string containing all results
        all_results_content = f"🔍 ZeroCyph OSINT Results\n\n"

        # Add raw JSON section
        all_results_content += "```json\n"
        all_results_content += json.dumps(data, indent=1)
        all_results_content += "\n```\n\n"

        # Add all individual results to the single content
        for i, result in enumerate(results, 1):
            formatted = f"""
🔍 **Pakistan Number Result {i}/{len(results)}**

📱 **Mobile:** {escape_markdown(str(result.get('Mobile', 'N/A')))}
👤 **Name:** {escape_markdown(str(result.get('Name', 'N/A')))}
🆔 **CNIC:** {escape_markdown(str(result.get('CNIC', 'N/A')))}
🏠 **Address:** {escape_markdown(str(result.get('Address', 'N/A')))}
"""
            all_results_content += formatted

        return [all_results_content]
    
    elif search_type == "vehicle":
        if not isinstance(data, dict) or not data.get("success"):
            return ["❌ No vehicle RC data found"]

        try:
            # Create a single formatted string containing all results
            all_results_content = f"🔍 ZeroCyph OSINT Results\n\n"

            # Create formatted response with raw JSON section
            all_results_content += f"🚗 **Vehicle Details for {escape_markdown(str(data.get('registrationnumber', 'N/A')))}**\n\n"
            all_results_content += "```json\n"
            # Safely handle JSON serialization
            try:
                all_results_content += json.dumps(data, indent=1, ensure_ascii=False)
            except (TypeError, ValueError) as e:
                logger.warning(f"JSON serialization error: {e}")
                all_results_content += "Unable to display raw JSON data"
            all_results_content += "\n```\n\n"

            all_results_content += f"📝 **Vehicle Details for {escape_markdown(str(data.get('registrationnumber', 'N/A')))}**:\n\n"

            # Format all simple fields with proper escaping
            simple_fields = [
                ("registeredPlace", data.get("registeredplace")),
                ("pucUpTo", data.get("pucupto")),
                ("rcStatus", data.get("rcstatus")),
                ("unladenWt", data.get("unladenwt")),
                ("hypothecation", data.get("hypothecation")),
                ("financier", data.get("financier")),
                ("vehicleCategory", data.get("vehiclecategory")),
                ("fuelType", data.get("fueltype")),
                ("rawFuelType", data.get("rawfueltype")),
                ("registeredAt", data.get("registeredat")),
                ("color", data.get("color")),
                ("rcNormsDesc", data.get("rcnormsdesc")),
                ("engineNo", data.get("engineno")),
                ("chassisNo", data.get("chassisno")),
                ("chassisNoFull", data.get("chassisnofull")),
                ("insuranceCompany", data.get("insurancecompany")),
                ("insuranceUpTo", data.get("insuranceupto")),
                ("rtoNocIssued", data.get("rtonocissued")),
                ("manufacturingMonthYr", data.get("manufacturingmonthyr")),
                ("fitnessUpTo", data.get("fitnessupto")),
                ("taxUpTo", data.get("taxupto")),
                ("vehicleClassDesc", data.get("vehicleclassdesc")),
                ("registrationNumber", data.get("registrationnumber")),
                ("modelImageUrl", data.get("modelimageurl")),
                ("seatCap", data.get("seatcap")),
                ("insurancePolicyNo", data.get("insurancepolicyno")),
                ("isCommercial", data.get("iscommercial")),
                ("isCommercialFrachiseRegion", data.get("iscommercialfrachiseregion")),
                ("updatedAt", data.get("updatedat")),
                ("brand", data.get("brand")),
                ("model", data.get("model")),
                ("year", data.get("year")),
                ("regn_year", data.get("regn_year")),
                ("rc_model", data.get("rc_model")),
                ("full_details", data.get("full_details")),
                ("rc_owner_name", data.get("rc_owner_name")),
                ("rc_owner_name_masked", data.get("rc_owner_name_masked")),
                ("rc_vh_class_desc", data.get("rc_vh_class_desc")),
                ("rc_owner_sr", data.get("rc_owner_sr")),
                ("ds_details", data.get("ds_details"))
            ]

            for field_name, field_value in simple_fields:
                if field_value is not None:
                    # Convert to string and escape
                    safe_value = escape_markdown(str(field_value)) if field_value != "" else "N/A"
                    all_results_content += f"🔹 **{escape_markdown(field_name)}:** {safe_value}\n"

            # Format nested dictionaries safely
            if "states" in data and data["states"] and isinstance(data["states"], dict):
                all_results_content += f"\n🔹 **STATES:**\n"
                states = data["states"]
                for key, value in states.items():
                    if value is not None:
                        safe_key = escape_markdown(str(key))
                        safe_value = escape_markdown(str(value))
                        all_results_content += f"   🔸 **{safe_key}:** {safe_value}\n"

            if "rto" in data and data["rto"] and isinstance(data["rto"], dict):
                all_results_content += f"\n🔹 **RTO:**\n"
                rto = data["rto"]
                for key, value in rto.items():
                    if value is not None:
                        safe_key = escape_markdown(str(key))
                        safe_value = escape_markdown(str(value))
                        all_results_content += f"   🔸 **{safe_key}:** {safe_value}\n"

            all_results_content += "\n✅ **All available details fetched successfully!**"

            return [all_results_content]

        except Exception as e:
            logger.error(f"Error formatting vehicle data: {e}")
            return ["❌ Error formatting vehicle data"]
    
    elif search_type == "ip":
        if not data or 'ip' not in data:
            return ["❌ No IP information found"]

        # Create a single formatted string containing all results
        all_results_content = f"🔍 ZeroCyph OSINT Results\n\n"

        all_results_content += f"""
🌐 **IP Information**

🌍 **IP Address:** {escape_markdown(str(data.get('ip', 'N/A')))}
🗺️ **Continent:** {escape_markdown(str(data.get('continent_name', 'N/A')))} ({escape_markdown(str(data.get('continent_code', 'N/A')))})
🏳️ **Country:** {escape_markdown(str(data.get('country_name', 'N/A')))} ({escape_markdown(str(data.get('country_code2', 'N/A')))})
🏛️ **Official Name:** {escape_markdown(str(data.get('country_name_official', 'N/A')))}
🏙️ **Capital:** {escape_markdown(str(data.get('country_capital', 'N/A')))}
🗺️ **Region:** {escape_markdown(str(data.get('state_prov', 'N/A')))} ({escape_markdown(str(data.get('state_code', 'N/A')))})
🏘️ **District:** {escape_markdown(str(data.get('district', 'N/A')))}
🏙️ **City:** {escape_markdown(str(data.get('city', 'N/A')))}
📮 **Zip Code:** {escape_markdown(str(data.get('zipcode', 'N/A')))}
📍 **Coordinates:** {escape_markdown(str(data.get('latitude', 'N/A')))}, {escape_markdown(str(data.get('longitude', 'N/A')))}
🌐 **TLD:** {escape_markdown(str(data.get('country_tld', 'N/A')))}
🌍 **Languages:** {escape_markdown(str(data.get('languages', 'N/A')))}
📞 **Calling Code:** {escape_markdown(str(data.get('calling_code', 'N/A')))}
🌐 **ISP:** {escape_markdown(str(data.get('isp', 'N/A')))}
🔌 **Organization:** {escape_markdown(str(data.get('organization', 'N/A')))}
💱 **Currency:** {escape_markdown(str(data.get('currency', {}).get('name', 'N/A')))} ({escape_markdown(str(data.get('currency', {}).get('code', 'N/A')))}) {escape_markdown(str(data.get('currency', {}).get('symbol', 'N/A')))}
⏰ **Timezone:** {escape_markdown(str(data.get('time_zone', {}).get('name', 'N/A')))} (UTC{escape_markdown(str(data.get('time_zone', {}).get('offset', 'N/A')))})
🕐 **Current Time:** {escape_markdown(str(data.get('time_zone', {}).get('current_time', 'N/A')))}
🏳️ **Country Flag:** {escape_markdown(str(data.get('country_emoji', 'N/A')))}
"""
        # Add raw JSON section
        all_results_content += "\n```json\n"
        all_results_content += json.dumps(data, indent=1)
        all_results_content += "\n```\n\n"

        return [all_results_content]
    
    elif search_type == "upi":
        if not data or 'bank_details_raw' not in data:
            return ["❌ No UPI information found"]

        bank_details = data.get('bank_details_raw', {})
        vpa_details = data.get('vpa_details', {})

        # Create a single formatted string containing all results
        all_results_content = f"🔍 ZeroCyph OSINT Results\n\n"

        all_results_content += f"""
🔍 **UPI Information**

💳 **VPA:** {escape_markdown(str(vpa_details.get('vpa', 'N/A')))}
👤 **Name:** {escape_markdown(str(vpa_details.get('name', 'N/A')))}
🏦 **Bank:** {escape_markdown(str(bank_details.get('BANK', 'N/A')))}
🏛️ **Branch:** {escape_markdown(str(bank_details.get('BRANCH', 'N/A')))}
🆔 **IFSC:** {escape_markdown(str(bank_details.get('IFSC', 'N/A')))}
📞 **Contact:** {escape_markdown(str(bank_details.get('CONTACT', 'Not found'))) if bank_details.get('CONTACT') else 'Not found'}
📍 **Address:** {escape_markdown(str(bank_details.get('ADDRESS', 'N/A')))}
🏙️ **City:** {escape_markdown(str(bank_details.get('CITY', 'N/A')))}
🗺️ **District:** {escape_markdown(str(bank_details.get('DISTRICT', 'N/A')))}
🌐 **State:** {escape_markdown(str(bank_details.get('STATE', 'N/A')))}
🏛️ **Centre:** {escape_markdown(str(bank_details.get('CENTRE', 'N/A')))}
📋 **Bank Code:** {escape_markdown(str(bank_details.get('BANKCODE', 'N/A')))}
🌍 **ISO Code:** {escape_markdown(str(bank_details.get('ISO3166', 'N/A')))}
💳 **MICR:** {escape_markdown(str(bank_details.get('MICR', 'Not found'))) if bank_details.get('MICR') else 'Not found'}
🌐 **SWIFT:** {escape_markdown(str(bank_details.get('SWIFT', 'Not found'))) if bank_details.get('SWIFT') else 'Not found'}
💳 **UPI:** {'Yes' if bank_details.get('UPI') else 'No'}
💸 **IMPS:** {'Yes' if bank_details.get('IMPS') else 'No'}
💸 **NEFT:** {'Yes' if bank_details.get('NEFT') else 'No'}
💸 **RTGS:** {'Yes' if bank_details.get('RTGS') else 'No'}
"""
        # Add raw JSON section
        all_results_content += "\n```json\n"
        all_results_content += json.dumps(data, indent=1)
        all_results_content += "\n```\n\n"

        return [all_results_content]
    
    elif search_type == "ifsc":
        if not data or 'IFSC' not in data:
            return ["❌ No IFSC information found"]

        # Create a single formatted string containing all results
        all_results_content = f"🔍 ZeroCyph OSINT Results\n\n"

        all_results_content += f"""
🔍 **IFSC Code Information**

🏦 **IFSC:** {escape_markdown(str(data.get('IFSC', 'N/A')))}
🏛️ **Bank:** {escape_markdown(str(data.get('BANK', 'N/A')))}
📋 **Bank Code:** {escape_markdown(str(data.get('BANKCODE', 'N/A')))}
🏛️ **Branch:** {escape_markdown(str(data.get('BRANCH', 'N/A')))}
📍 **Address:** {escape_markdown(str(data.get('ADDRESS', 'N/A')))}
🏙️ **City:** {escape_markdown(str(data.get('CITY', 'N/A')))}
🗺️ **District:** {escape_markdown(str(data.get('DISTRICT', 'N/A')))}
🌐 **State:** {escape_markdown(str(data.get('STATE', 'N/A')))}
🏛️ **Centre:** {escape_markdown(str(data.get('CENTRE', 'N/A')))}
📞 **Contact:** {escape_markdown(str(data.get('CONTACT', 'Not found'))) if data.get('CONTACT') else 'Not found'}
💳 **MICR:** {escape_markdown(str(data.get('MICR', 'Not found'))) if data.get('MICR') else 'Not found'}
🌐 **SWIFT:** {escape_markdown(str(data.get('SWIFT', 'Not found'))) if data.get('SWIFT') else 'Not found'}
🌍 **ISO Code:** {escape_markdown(str(data.get('ISO3166', 'N/A')))}
💳 **UPI:** {'Yes' if data.get('UPI') else 'No'}
💸 **IMPS:** {'Yes' if data.get('IMPS') else 'No'}
💸 **NEFT:** {'Yes' if data.get('NEFT') else 'No'}
💸 **RTGS:** {'Yes' if data.get('RTGS') else 'No'}
"""
        # Add raw JSON section
        all_results_content += "\n```json\n"
        all_results_content += json.dumps(data, indent=1)
        all_results_content += "\n```\n\n"

        return [all_results_content]
    
    elif search_type == "freefire":
        # Check if it's an error response
        if isinstance(data, dict) and data.get("success") is False:
            error_msg = data.get('error', 'Unknown error')
            # Check if it's a 404 error or similar which means user not found
            if "404" in str(error_msg) or "NOT FOUND" in str(error_msg).upper() or "not found" in str(error_msg).lower():
                return ["❌ **Free Fire Search Failed**\n\nData bot found"]
            else:
                # Hide the URL in the error message
                clean_error = str(error_msg)
                if "http" in clean_error:
                    # Extract just the error description without the URL
                    parts = clean_error.split("http")
                    clean_error = parts[0].strip()
                    if not clean_error:
                        clean_error = "Request failed"
                return [f"❌ **Free Fire Search Failed**\n\nError: {clean_error}"]

        if not data or 'basicInfo' not in data:
            return ["❌ **Free Fire Search Failed**\n\nData bot found"]

        # Create a single formatted string containing all results
        all_results_content = f"🔍 ZeroCyph OSINT Results\n\n"

        # Create formatted response with raw JSON section
        all_results_content += f"🔫 **Free Fire Account Information**\n\n"
        try:
            all_results_content += "```json\n"
            all_results_content += json.dumps(data, indent=1)
            all_results_content += "\n```\n\n"
        except:
            all_results_content += "```json\n"
            all_results_content += str(data)
            all_results_content += "\n```\n\n"

        # Format basic info
        basic_info = data.get('basicInfo', {})
        all_results_content += f"👤 **Free Fire Account Information**:\n\n"
        all_results_content += f"🆔 **Account ID:** {escape_markdown(str(basic_info.get('accountId', 'N/A')))}\n"
        all_results_content += f"📛 **Nickname:** {escape_markdown(str(basic_info.get('nickname', 'N/A')))}\n"
        all_results_content += f"📊 **Level:** {escape_markdown(str(basic_info.get('level', 'N/A')))}\n"
        all_results_content += f"🎖️ **Rank:** {escape_markdown(str(basic_info.get('rank', 'N/A')))}\n"
        all_results_content += f"🏆 **Max Rank:** {escape_markdown(str(basic_info.get('maxRank', 'N/A')))}\n"
        all_results_content += f"🎯 **Ranking Points:** {escape_markdown(str(basic_info.get('rankingPoints', 'N/A')))}\n"
        all_results_content += f"🌐 **Region:** {escape_markdown(str(basic_info.get('region', 'N/A')))}\n"
        all_results_content += f"🌍 **Resolved Region:** {escape_markdown(str(data.get('_resolved_region', 'N/A')))}\n"
        all_results_content += f"💎 **Diamond Cost:** {escape_markdown(str(data.get('diamondCostRes', {}).get('diamondCost', 'N/A')))}\n"

        # Add clan info if available
        clan_info = data.get('clanBasicInfo', {})
        if clan_info:
            all_results_content += f"\n🎪 **Clan Information**:\n"
            all_results_content += f"🎪 **Clan Name:** {escape_markdown(str(clan_info.get('clanName', 'N/A')))}\n"
            all_results_content += f"👥 **Clan Members:** {escape_markdown(str(clan_info.get('memberNum', 'N/A')))} / {escape_markdown(str(clan_info.get('capacity', 'N/A')))}\n"
            all_results_content += f"🏰 **Clan Level:** {escape_markdown(str(clan_info.get('clanLevel', 'N/A')))}\n"

        # Add social info
        social_info = data.get('socialInfo', {})
        if social_info:
            all_results_content += f"\n💬 **Social Information**:\n"
            all_results_content += f"👨‍👩‍👧‍👦 **Gender:** {escape_markdown(str(social_info.get('gender', 'N/A')))}\n"
            all_results_content += f"🌐 **Language:** {escape_markdown(str(social_info.get('language', 'N/A')))}\n"
            all_results_content += f"📜 **Signature:** {escape_markdown(str(social_info.get('signature', 'N/A')))}\n"

        # Add credit score info
        credit_score_info = data.get('creditScoreInfo', {})
        if credit_score_info:
            all_results_content += f"\n✅ **Credit Score**:\n"
            all_results_content += f"💯 **Score:** {escape_markdown(str(credit_score_info.get('creditScore', 'N/A')))}\n"

        # Add pet info if available\n        pet_info = data.get('petInfo', {})\n        if pet_info:\n            all_results_content += f\"\\n🐾 **Pet Information**:\\n\"\n            all_results_content += f\"🐾 **Pet Level:** {escape_markdown(str(pet_info.get('level', 'N/A')))}\\n\"\n            all_results_content += f\"🐾 **Pet XP:** {escape_markdown(str(pet_info.get('exp', 'N/A')))}\\n\"

        # Add release version and season info
        all_results_content += f"\n🏷️ **Game Info**:\n"
        all_results_content += f"🎮 **Release Version:** {escape_markdown(str(basic_info.get('releaseVersion', 'N/A')))}\n"
        all_results_content += f"📅 **Season ID:** {escape_markdown(str(basic_info.get('seasonId', 'N/A')))}\n"

        return [all_results_content]
    
    elif search_type == "cnic":
        if not data.get('exists', False):
            return ["❌ No CNIC family data found"]

        family_data = data.get('familyData', {})

        # Create a single formatted string containing all results
        all_results_content = f"🔍 ZeroCyph OSINT Results\n\n"

        # Create formatted response with raw JSON section
        all_results_content += f"👨‍👩‍👧‍👦 <b>CNIC Family Information</b>\n\n"
        all_results_content += "<pre>"
        all_results_content += json.dumps(data, indent=1, ensure_ascii=False)
        all_results_content += "</pre>\n\n"

        all_results_content += f"👨‍👩‍👧‍👦 <b>Family Information:</b>\n\n"

        # Father information
        if 'father' in family_data:
            father = family_data['father']
            all_results_content += f"👨 <b>Father:</b>\n"
            all_results_content += f"• <b>Name:</b> {html.escape(str(father.get('name', 'N/A')))}\n"
            all_results_content += f"• <b>DOB:</b> {html.escape(str(father.get('dob', 'N/A')))}\n"
            all_results_content += f"• <b>CNIC:</b> <code>{father.get('cnic', 'N/A')}</code>\n"
            all_results_content += f"• <b>Address:</b> {html.escape(str(father.get('address', 'N/A')))}\n\n"

        # Mother information
        if 'mother' in family_data:
            mother = family_data['mother']
            all_results_content += f"👩 <b>Mother:</b>\n"
            all_results_content += f"• <b>Name:</b> {html.escape(str(mother.get('name', 'N/A')))}\n"
            all_results_content += f"• <b>DOB:</b> {html.escape(str(mother.get('dob', 'N/A')))}\n"
            all_results_content += f"• <b>CNIC:</b> <code>{mother.get('cnic', 'N/A')}</code>\n"
            all_results_content += f"• <b>Address:</b> {html.escape(str(mother.get('address', 'N/A')))}\n\n"

        # Children information
        if 'children' in family_data and family_data['children']:
            all_results_content += f"👶 <b>Children ({len(family_data['children'])}):</b>\n"
            for i, child in enumerate(family_data['children'], 1):
                all_results_content += f"\n<b>Child {i}:</b>\n"
                all_results_content += f"• <b>Name:</b> {html.escape(str(child.get('name', 'N/A')))}\n"
                all_results_content += f"• <b>DOB:</b> {html.escape(str(child.get('dob', 'N/A')))}\n"
                all_results_content += f"• <b>CNIC:</b> <code>{child.get('cnic', 'N/A')}</code>\n"
                all_results_content += f"• <b>Gender:</b> {html.escape(str(child.get('gender', 'N/A')))}\n"
                all_results_content += f"• <b>Role:</b> {html.escape(str(child.get('role', 'N/A')))}\n"

        return [all_results_content]
    
    return ["❌ No results found"]


def escape_markdown(text):
    """
    Escape markdown special characters in text to prevent Telegram parsing errors
    """
    if text is None:
        return "N/A"
    
    # Convert to string first
    text = str(text)
    
    # Characters that need to be escaped in Telegram MarkdownV2
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    # Escape each character
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

# Helper to handle anonymous users
def is_anonymous(message):
    return message.from_user is None

# Helper function to check if user is verified and in channel
def check_user_verification(user_id, message):
    """Check if user is verified and in channel. If not, send appropriate message and return False."""
    # Skip check for admins and super groups
    if user_id in ADMIN_IDS:
        return True
        
    if message.chat.type != 'private' and message.chat.id in SUPER_GROUP_IDS:
        return True
    
    # Check if user is in channel
    if not is_user_in_channel(user_id):
        # User is not in channel
        bot.reply_to(message, 
            "❌ **You are not in our channel!**\n\n"
            "Please join our channel and use /start again to verify.\n\n"
            "⚠️ **Note:** Even if it says verified, you still need to join the channel to use the bot.",
            reply_markup=create_verification_keyboard(), parse_mode='Markdown')
        return False
    
    # Check if user is verified in database
    if not is_user_verified(user_id):
        # User is in channel but not verified in database, verify now
        verify_user(user_id)
    
    return True

# Bot handlers
@bot.message_handler(commands=['start'])
def handle_start(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user = message.from_user
        
        # Add user to database
        executor.submit(add_user, user.id, user.username, user.first_name, user.last_name)
        
        if message.chat.type == 'private':
            # Check if user is admin
            if user.id in ADMIN_IDS:
                welcome_text = f"""
🔥 <b>Welcome Admin {html.escape(user.first_name)}!</b>

You have admin privileges and can use the bot in private.

🤖 <b>ZeroVenom OSINT Bot</b>
━━━━━━━━━━━━━━━━━━━━
🔍 Advanced OSINT capabilities
📱 Mobile number lookup
🆔 Aadhar information search
👤 Telegram user info
🔫 Free Fire account lookup
🇵🇰 Pakistan number lookup
🚗 Vehicle RC lookup
🌐 IP address lookup
💳 UPI information lookup
🏦 IFSC code lookup
📧 Email to number lookup
🏥 ICMR information lookup
🆔 CNIC family info lookup
⚡ Fast and reliable

<b>Commands:</b>
/num [mobile] - Mobile lookup
/adh [aadhar] - Aadhar lookup
/tg [user_id] - Telegram user info
/ff [uid] - Free Fire account lookup
/pak [number] - Pakistan number lookup
/rc [rc_number] - Vehicle RC lookup
/ip [ip_address] - IP address lookup
/upi [upi_id] - UPI information lookup
/ifsc [ifsc_code] - IFSC code lookup
/email [email] - Email to number lookup
/imcr [phone] - ICMR information lookup
/cnic [cnic_number] - CNIC family info lookup
/approve [user_id] - Approve user for private use
/demote [user_id] - Demote user from private use
/remlimit [group_id] - Remove member limit for group
/help - Show all commands
/status - Bot statistics
/groups - List all groups
/broadcast [count] - Broadcast message
/fetch - Backup database
/logs - Get bot logs

<b>Note:</b> For regular users, this bot only works in groups with 25+ members.
"""
                keyboard = create_main_keyboard()
                send_safe_message(message.chat.id, welcome_text, reply_markup=keyboard, reply_to_message_id=message.message_id)
            else:
                # Check if user is approved for private use
                if is_user_approved_private(user.id):
                    # User is approved for private use
                    welcome_text = f"""✅ <b>Welcome {html.escape(user.first_name)}!</b>

You are approved to use the bot in private chat.

🤖 <b>ZeroVenom OSINT Bot</b>
━━━━━━━━━━━━━━━━━━━━
🔍 Advanced OSINT capabilities
📱 Mobile number lookup
🆔 Aadhar information search
👤 Telegram user info
🇵🇰 Pakistan number lookup
🚗 Vehicle RC lookup
🌐 IP address lookup
💳 UPI information lookup
🏦 IFSC code lookup
⚡ Fast and reliable

<b>Commands:</b>
/num &lt;mobile&gt; - Mobile lookup
/adh &lt;aadhar&gt; - Aadhar lookup
/tg &lt;user_id&gt; - Telegram user info
/pak &lt;number&gt; - Pakistan number lookup
/rc &lt;rc_number&gt; - Vehicle RC lookup
/ip &lt;ip_address&gt; - IP address lookup
/upi &lt;upi_id&gt; - UPI information lookup
/ifsc &lt;ifsc_code&gt; - IFSC code lookup
/cnic &lt;cnic_number&gt; - CNIC family info lookup
/help - Show all commands

Enjoy using the bot! 🚀"""
                    keyboard = create_main_keyboard()
                    bot.send_message(message.chat.id, welcome_text, reply_markup=keyboard, parse_mode='HTML', reply_to_message_id=message.message_id)
                else:
                    # Check if user is in channel
                    if is_user_in_channel(user.id):
                        # User is in channel, verify if not already
                        if not is_user_verified(user.id):
                            verify_user(user.id)
                        
                        # User is already verified, show welcome message
                        verification_text = f"""✅ <b>Verification Complete!</b>

Welcome <b>{html.escape(user.first_name)}</b>! You're now verified.

🤖 <b>Remember:</b> This bot only works in groups with 25+ members.

🔍 <b>Search Commands:</b>
• /num &lt;mobile&gt; - Mobile number lookup
• /adh &lt;aadhar&gt; - Aadhar information search
• /tg &lt;user_id&gt; - Telegram user info
• /pak &lt;number&gt; - Pakistan number lookup
• /rc &lt;rc_number&gt; - Vehicle RC lookup
• /ip &lt;ip_address&gt; - IP address lookup
• /upi &lt;upi_id&gt; - UPI information lookup
• /ifsc &lt;ifsc_code&gt; - IFSC code lookup
• /email &lt;email&gt; - Email to number lookup
• /imcr &lt;phone&gt; - ICMR information lookup
• /cnic &lt;cnic_number&gt; - CNIC family info lookup

📋 <b>Usage Examples:</b>
• /num 9876543210
• /adh 123456789012
• /tg 5838583388
• /pak 923041234567
• /rc MH01AB1234
• /ip 8.8.8.8
• /upi rahul@upi
• /ifsc BKID0006313
• /email support@gmail.com
• /imcr 9876543210
• /cnic 15601-6938749-3

Please add me to your group to start using OSINT features!
Use /help to see detailed information.

⚠️ <b>Note:</b> Even if it says verified, you still need to join the channel to use the bot."""
                        keyboard = create_main_keyboard()
                        bot.send_message(message.chat.id, verification_text, reply_markup=keyboard, parse_mode='HTML', reply_to_message_id=message.message_id)
                    else:
                        # User needs to join channel first
                        welcome_text = f"""🔥 <b>Welcome to ZeroVenom OSINT Bot!</b>

<b>⚠️ This bot only works in groups!</b>

Please add me to your group to use OSINT features.

🤖 <b>Features:</b>
━━━━━━━━━━━━━━━━━━━━
🔍 Advanced OSINT capabilities
📱 Mobile number lookup  
🆔 Aadhar information search
👤 Telegram user info
🇵🇰 Pakistan number lookup
🚗 Vehicle RC lookup
🌐 IP address lookup
💳 UPI information lookup
🏦 IFSC code lookup
⚡ Fast and reliable

<b>First, join our channel to verify:</b>

⚠️ <b>Note:</b> Even if it says verified, you still need to join the channel to use the bot."""
                        keyboard = create_verification_keyboard()
                        bot.send_message(message.chat.id, welcome_text, reply_markup=keyboard, parse_mode='HTML', reply_to_message_id=message.message_id)
        
        else:  # Group chat
            # Check member count in a background thread
            def check_group():
                try:
                    member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                    # Skip member count check for super groups or groups with member limit removed
                    if member_count < MIN_GROUP_MEMBERS and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
                        bot.reply_to(message, 
                            f"⚠️ **Group Requirements Not Met**\n\n"
                            f"This bot requires groups with **{MIN_GROUP_MEMBERS}+ members**.\n"
                            f"Current members: **{member_count}**\n\n"
                            f"Please invite more members to use this bot.",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
                        return
                    
                    # Add group to database
                    add_group(message.chat.id, message.chat.title, member_count)
                    
                    # For verified users or super groups, show menu directly
                    if is_user_in_channel(user.id) or message.chat.id in SUPER_GROUP_IDS:
                        if not is_user_verified(user.id):
                            verify_user(user.id)
                            
                        if message.chat.id in SUPER_GROUP_IDS:
                            welcome_text = f"""🎉 <b>ZeroVenom OSINT Bot Ready in Official Group!</b>

🤖 <b>All features available without verification!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>Bot successfully added to the official group!</b>

🔍 <b>Available Commands:</b>
• /num &lt;mobile&gt; - Mobile number lookup
• /adh &lt;aadhar&gt; - Aadhar information search
• /tg &lt;user_id&gt; - Telegram user info
• /pak &lt;number&gt; - Pakistan number lookup
• /rc &lt;rc_number&gt; - Vehicle RC lookup
• /ip &lt;ip_address&gt; - IP address lookup
• /upi &lt;upi_id&gt; - UPI information lookup
• /ifsc &lt;ifsc_code&gt; - IFSC code lookup
• /help - Show all commands

⚡ <b>Features:</b>
• Fast API responses
• Daily limit: {DAILY_LIMIT} searches per user
• Detailed information display
• No verification required!

Enjoy using the bot! 🚀"""
                        else:
                            welcome_text = f"""🎉 <b>ZeroVenom OSINT Bot Ready!</b>

🤖 <b>Advanced OSINT capabilities at your service</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>Bot successfully added to your group!</b>

⚠️ <b>Verification Required</b>: All users must join our channel and verify before using the bot.

🔍 <b>Available Commands:</b>
• /num &lt;mobile&gt; - Mobile number lookup
• /adh &lt;aadhar&gt; - Aadhar information search
• /tg &lt;user_id&gt; - Telegram user info
• /pak &lt;number&gt; - Pakistan number lookup
• /rc &lt;rc_number&gt; - Vehicle RC lookup
• /ip &lt;ip_address&gt; - IP address lookup
• /upi &lt;upi_id&gt; - UPI information lookup
• /ifsc &lt;ifsc_code&gt; - IFSC code lookup
• /help - Show all commands

⚡ <b>Features:</b>
• Fast API responses
• Daily limit: {DAILY_LIMIT} searches per user
• Detailed information display

<b>Join our channel for updates and support!</b>

⚠️ <b>Note:</b> Even if it says verified, you still need to join the channel to use the bot."""
                        
                        bot.send_message(message.chat.id, welcome_text, 
                                        reply_markup=create_main_keyboard(), parse_mode='HTML', reply_to_message_id=message.message_id)
                    else:
                        verification_text = f"""
⚠️ **Verification Required**

Hi **{user.first_name}**! Before using the bot, you need to:
1️⃣ Join our channel 
2️⃣ Verify your account

Please click the button below to proceed:

⚠️ **Note:** Even if it says verified, you still need to join the channel to use the bot.
"""
                        bot.reply_to(message, verification_text,
                                       reply_markup=create_verification_keyboard(),
                                       parse_mode='Markdown')
                    
                except Exception as e:
                    logger.error(f"Error in group start: {e}")
            
            # Run in background thread
            executor.submit(check_group)
    except Exception as e:
        logger.error(f"Error in start handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.callback_query_handler(func=lambda call: call.data == "verify")
def handle_verify(call):
    try:
        user = call.from_user
        user_id = user.id
        
        # Check if user is already verified first
        if is_user_verified(user_id):
            bot.edit_message_text(
                "✅ **You are already verified!**\n\n"
                "You can now use the bot in any group with 25+ members.\n\n"
                "⚠️ **Note:** Even if it says verified, you still need to join the channel to use the bot.",
                call.message.chat.id, call.message.message_id,
                reply_markup=create_main_keyboard(), parse_mode='Markdown'
            )
            return
        
        # Check if user has joined the channel
        if is_user_in_channel(user_id):
            # Mark user as verified
            verify_user(user_id)
            
            verification_text = f"""
✅ **Verification Complete!**

Welcome **{user.first_name}**! You're now verified.

🤖 **Remember:** This bot only works in groups with 25+ members.

🔍 **Search Commands:**
• `/num <mobile>` - Mobile number lookup
• `/adh <aadhar>` - Aadhar information search
• `/tg <user_id>` - Telegram user info
• `/pak <number>` - Pakistan number lookup
• `/rc <rc_number>` - Vehicle RC lookup
• `/ip <ip_address>` - IP address lookup
• `/upi <upi_id>` - UPI information lookup
• `/ifsc <ifsc_code>` - IFSC code lookup
• `/email <email>` - Email to number lookup
• `/cnic <cnic_number>` - CNIC family info lookup
• `/imcr <phone>` - ICMR information lookup

📋 **Usage Examples:**
• `/num 9876543210`
• `/adh 123456789012`
• `/tg 5838583388`
• `/pak 923041234567`
• `/rc MH01AB1234`
• `/ip 8.8.8.8`
• `/upi rahul@upi`
• `/ifsc BKID0006313`
• `/email support@gmail.com`
• `/imcr 9876543210`
• `/cnic 15601-6938749-3`

Please add me to your group to start using OSINT features!
Use `/help` to see detailed information.

⚠️ **Note:** Even if it says verified, you still need to join the channel to use the bot.
"""
            
            bot.edit_message_text(verification_text, call.message.chat.id, call.message.message_id,
                                 reply_markup=create_main_keyboard(), parse_mode='Markdown')
        else:
            bot.answer_callback_query(call.id, "⚠️ Please join the channel first before verifying! Even if it says verified, you still need to join the channel to use the bot.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in verify handler: {e}")
        bot.answer_callback_query(call.id, "❌ An error occurred. Please try again.", show_alert=True)

# Handle make admin callback
@bot.callback_query_handler(func=lambda call: call.data == "make_admin")
def handle_make_admin(call):
    try:
        bot.answer_callback_query(call.id, "Please make the bot admin in this group to use all features.", show_alert=True)
    except Exception as e:
        logger.error(f"Error in make admin handler: {e}")

@bot.message_handler(commands=['help'])
def handle_help(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        is_admin = user_id in ADMIN_IDS
        
        # Basic help for all users
        help_text = f"""🤖 <b>ZeroVenom OSINT Bot - Commands</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 <b>Search Commands:</b>
• /num &lt;mobile&gt; - Mobile number lookup
• /adh &lt;aadhar&gt; - Aadhar information search
• /tg &lt;user_id&gt; - Telegram user info
• /pak &lt;number&gt; - Pakistan number lookup
• /rc &lt;rc_number&gt; - Vehicle RC lookup
• /ip &lt;ip_address&gt; - IP address lookup
• /upi &lt;upi_id&gt; - UPI information lookup
• /ifsc &lt;ifsc_code&gt; - IFSC code lookup
• /email &lt;email&gt; - Email to number lookup
• /imcr &lt;phone&gt; - ICMR information lookup
• /cnic &lt;cnic_number&gt; - CNIC family info lookup
• /ff &lt;uid&gt; - Free Fire account lookup

🔧 <b>Utility Commands:</b>
• /delete &lt;message_link&gt; - Delete any message by link (Admin only, works in private)

📊 <b>Info Commands:</b>
• /help - Show this help menu

📋 <b>Usage Examples:</b>
• /num 9876543210
• /num +91 9876543210
• /adh 123456789012
• /tg 5838583388
• /pak 923041234567
• /rc MH01AB1234
• /ip 8.8.8.8
• /upi rahul@upi
• /ifsc BKID0006313
• /email support@gmail.com
• /imcr 9876543210
• /cnic 15601-6938749-3
• /ff 123456789

⚡ <b>Limits:</b>
• Daily limit: {DAILY_LIMIT} searches per user
• Minimum group members: {MIN_GROUP_MEMBERS}

<b>Note:</b> Bot only works in groups (except for admins)"""
        
        # Add admin commands only for admins
        if is_admin:
            admin_help = f"""

⚙️ <b>Admin Commands:</b>
• /status - Bot statistics
• /groups - List all groups
• /broadcast &lt;count&gt; - Broadcast message
• /ban &lt;group_id&gt; - Ban a group
• /fetch - Backup database file
• /fetchall - Backup all bot files (send to all admins)
• /backup - Backup all bot files (admin only)
• /logs - Get bot logs
• /approve &lt;user_id&gt; - Approve user for private use
• /demote &lt;user_id&gt; - Demote user from private use
• /remlimit &lt;group_id&gt; - Remove member limit for group
• /delete &lt;message_link&gt; - Delete any message by link (Works in private)

🔧 <b>Admin Privileges:</b>
• Can use bot in private chat
• Access to all statistics
• Group management capabilities
• Database backup
• Complete file backup
• Log viewing
• User approval/demotion
• Message deletion utility"""
            help_text += admin_help
        
        keyboard = create_main_keyboard()
        bot.reply_to(message, help_text, 
                        reply_markup=keyboard, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error in help handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")
@bot.message_handler(commands=['num'])
def handle_mobile_search(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        
        # Check if user is verified and in channel
        if not check_user_verification(user_id, message):
            return
        
        # Check if in private and not admin
        if message.chat.type == 'private' and user_id not in ADMIN_IDS and not is_user_approved_private(user_id):
            bot.reply_to(message, 
                "⚠️ **This bot only works in groups!**\n\n"
                "Please add me to your group with 25+ members.",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check if group and group requirements (skip for super groups or groups with member limit removed)
        if message.chat.type != 'private' and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
            if is_group_banned(message.chat.id):
                bot.reply_to(message, "❌ This group is banned from using the bot.")
                return
                
            try:
                member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                if member_count < MIN_GROUP_MEMBERS:
                    bot.reply_to(message, 
                        f"⚠️ Group needs **{MIN_GROUP_MEMBERS}+ members** to use this bot.\n"
                        f"Current: **{member_count} members**",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                    return
            except:
                pass
        
        # Extract mobile number
        try:
            args = message.text.split(None, 1)[1]
            mobile = clean_phone_number(args)
            
            if len(mobile) != 10:
                bot.reply_to(message, 
                    "❌ **Invalid mobile number format**\n\n"
                    "Please provide a valid 10-digit mobile number.\n"
                    "Example: `/num 9876543210`",
                    reply_markup=create_main_keyboard(), parse_mode='Markdown')
                return
        except IndexError:
            bot.reply_to(message, 
                "❌ **Missing mobile number**\n\n"
                "Usage: `/num <mobile_number>`\n"
                "Example: `/num 9876543210`",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check daily limit
        can_search, message_text = check_daily_limit(user_id)
        if not can_search:
            bot.reply_to(message, f"⏳ **Search Limit Reached**\n\n{message_text}",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Send processing message
        processing_msg = bot.reply_to(message, 
            f"🔍 **Processing your request...**\n\n"
            f"📱 Searching for: **{mobile}**\n"
            f"⏳ Please wait...",
            reply_markup=create_main_keyboard(), parse_mode='Markdown')
        
        def search_and_respond():
            try:
                # Perform search
                result = search_mobile(mobile)
                
                # Debug logging
                logger.info(f"Mobile API Response: {json.dumps(result)}")
                
                # Update search stats
                update_search_stats(user_id, "mobile", mobile)
                
                # Format results
                formatted_results = format_response(result, "mobile")

                # Delete processing message
                try:
                    bot.delete_message(message.chat.id, processing_msg.message_id)
                except:
                    pass

                # Check if we have more than 5 results to decide whether to send as file
                if len(formatted_results) > 5:
                    # Send results as a single file with minimum required information
                    all_results_text = ""
                    for result_text in formatted_results:
                        all_results_text += result_text + "\n\n"

                    # Create a temporary file with all results
                    import tempfile
                    import os

                    # Create a temporary file
                    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
                        temp_file.write(all_results_text)
                        temp_file_path = temp_file.name

                    try:
                        # Send the file
                        with open(temp_file_path, 'rb') as file:
                            bot.send_document(message.chat.id, file,
                                          caption="🔍 ZeroCyph OSINT Results",
                                          reply_markup=create_main_keyboard(),
                                          reply_to_message_id=message.message_id)
                    finally:
                        # Clean up the temporary file
                        if os.path.exists(temp_file_path):
                            os.remove(temp_file_path)
                else:
                    # Send results normally
                    for i, result_text in enumerate(formatted_results):
                        # Split if too long
                        if len(result_text) > 4096:
                            chunks = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
                            for chunk in chunks:
                                bot.send_message(message.chat.id, chunk,
                                              reply_markup=create_main_keyboard(),
                                              parse_mode='Markdown', reply_to_message_id=message.message_id)
                        else:
                            bot.send_message(message.chat.id, result_text,
                                          reply_markup=create_main_keyboard(),
                                          parse_mode='Markdown', reply_to_message_id=message.message_id)
                    
            except Exception as e:
                logger.error(f"Mobile search error: {e}")
                try:
                    edit_message_with_tracking(
                        message.chat.id, processing_msg.message_id,
                        f"❌ **Search Failed**\n\n"
                        f"An error occurred while processing your request.\n"
                        f"Please try again later.",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                except:
                    pass
        
        # Run search in thread
        executor.submit(search_and_respond)
    except Exception as e:
        logger.error(f"Error in mobile search handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.message_handler(commands=['adh'])
def handle_aadhar_search(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        
        # Check if user is verified and in channel
        if not check_user_verification(user_id, message):
            return
        
        # Check if in private and not admin
        if message.chat.type == 'private' and user_id not in ADMIN_IDS and not is_user_approved_private(user_id):
            bot.reply_to(message, 
                "⚠️ **This bot only works in groups!**\n\n"
                "Please add me to your group with 25+ members.",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check if group and group requirements (skip for super groups or groups with member limit removed)
        if message.chat.type != 'private' and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
            if is_group_banned(message.chat.id):
                bot.reply_to(message, "❌ This group is banned from using the bot.")
                return
                
            try:
                member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                if member_count < MIN_GROUP_MEMBERS:
                    bot.reply_to(message, 
                        f"⚠️ Group needs **{MIN_GROUP_MEMBERS}+ members** to use this bot.\n"
                        f"Current: **{member_count} members**",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                    return
            except:
                pass
        
        # Extract aadhar number
        try:
            args = message.text.split(None, 1)[1]
            aadhar = re.sub(r'[^\d]', '', args)
            
            if len(aadhar) != 12:
                bot.reply_to(message, 
                    "❌ **Invalid Aadhar number format**\n\n"
                    "Please provide a valid 12-digit Aadhar number.\n"
                    "Example: `/adh 123456789012`",
                    reply_markup=create_main_keyboard(), parse_mode='Markdown')
                return
        except IndexError:
            bot.reply_to(message, 
                "❌ **Missing Aadhar number**\n\n"
                "Usage: `/adh <aadhar_number>`\n"
                "Example: `/adh 123456789012`",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check daily limit
        can_search, message_text = check_daily_limit(user_id)
        if not can_search:
            bot.reply_to(message, f"⏳ **Search Limit Reached**\n\n{message_text}",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Send processing message
        processing_msg = bot.reply_to(message, 
            f"🔍 **Processing your request...**\n\n"
            f"🆔 Searching for: **{aadhar}**\n"
            f"⏳ Please wait...",
            reply_markup=create_main_keyboard(), parse_mode='Markdown')
        
        def search_and_respond():
            try:
                # Perform search with retry logic built in
                result = search_aadhar(aadhar)
                
                # Debug logging
                logger.info(f"Aadhar API Response: {json.dumps(result)}")
                
                # Update search stats
                update_search_stats(user_id, "aadhar", aadhar)
                
                # Format results
                formatted_results = format_response(result, "aadhar")

                # Delete processing message
                try:
                    bot.delete_message(message.chat.id, processing_msg.message_id)
                except:
                    pass

                # Send results normally with raw and filtered data
                for i, result_text in enumerate(formatted_results):
                    # Split if too long
                    if len(result_text) > 4096:
                        chunks = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
                        for chunk in chunks:
                            bot.send_message(message.chat.id, chunk,
                                          reply_markup=create_main_keyboard(),
                                          parse_mode='Markdown', reply_to_message_id=message.message_id)
                    else:
                        bot.send_message(message.chat.id, result_text,
                                      reply_markup=create_main_keyboard(),
                                      parse_mode='Markdown', reply_to_message_id=message.message_id)
                    
            except Exception as e:
                logger.error(f"Aadhar search error: {e}")
                try:
                    edit_message_with_tracking(
                        message.chat.id, processing_msg.message_id,
                        f"❌ **Search Failed**\n\n"
                        f"An error occurred while processing your request.\n"
                        f"Please try again later.",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                except:
                    pass
        
        # Run search in thread
        executor.submit(search_and_respond)
    except Exception as e:
        logger.error(f"Error in aadhar search handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.message_handler(commands=['tg'])
def handle_telegram_search(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        
        # Check if user is verified and in channel
        if not check_user_verification(user_id, message):
            return
        
        # Check if in private and not admin
        if message.chat.type == 'private' and user_id not in ADMIN_IDS and not is_user_approved_private(user_id):
            bot.reply_to(message, 
                "⚠️ **This bot only works in groups!**\n\n"
                "Please add me to your group with 25+ members.",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check if group and group requirements (skip for super groups or groups with member limit removed)
        if message.chat.type != 'private' and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
            if is_group_banned(message.chat.id):
                bot.reply_to(message, "❌ This group is banned from using the bot.")
                return
                
            try:
                member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                if member_count < MIN_GROUP_MEMBERS:
                    bot.reply_to(message, 
                        f"⚠️ Group needs **{MIN_GROUP_MEMBERS}+ members** to use this bot.\n"
                        f"Current: **{member_count} members**",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                    return
            except:
                pass
        
        # Extract user ID
        try:
            args = message.text.split(None, 1)[1]
            tg_user_id = re.sub(r'[^\d]', '', args)
            
            if not tg_user_id:
                bot.reply_to(message, 
                    "❌ **Invalid Telegram user ID format**\n\n"
                    "Please provide a valid Telegram user ID.\n"
                    "Example: `/tg 5838583388`",
                    reply_markup=create_main_keyboard(), parse_mode='Markdown')
                return
        except IndexError:
            bot.reply_to(message, 
                "❌ **Missing Telegram user ID**\n\n"
                "Usage: `/tg <user_id>`\n"
                "Example: `/tg 5838583388`",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check daily limit
        can_search, message_text = check_daily_limit(user_id)
        if not can_search:
            bot.reply_to(message, f"⏳ **Search Limit Reached**\n\n{message_text}",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Send processing message
        processing_msg = bot.reply_to(message, 
            f"🔍 **Processing your request...**\n\n"
            f"👤 Searching for Telegram user ID: **{tg_user_id}**\n"
            f"⏳ Please wait...",
            reply_markup=create_main_keyboard(), parse_mode='Markdown')
        
        def search_and_respond():
            try:
                # Perform search
                result = search_telegram(tg_user_id)
                
                # Update search stats
                update_search_stats(user_id, "telegram", tg_user_id)
                
                # Format results
                formatted_results = format_response(result, "telegram")
                
                # Delete processing message
                try:
                    bot.delete_message(message.chat.id, processing_msg.message_id)
                except:
                    pass
                
                # Send results
                for i, result_text in enumerate(formatted_results):
                    # Add JSON summary for the first batch
                    if i == 0 and result.get('success', False):
                        user_data = result.get('data', {})
                        compact_data = {
                            "id": user_data.get('id', 'N/A'),
                            "first_name": user_data.get('first_name', 'N/A'),
                            "is_bot": user_data.get('is_bot', False),
                            "is_active": user_data.get('is_active', False)
                        }
                        
                        json_text = f"```json\n{json.dumps(compact_data, indent=1)}\n```\n\n"
                        result_text = f"👤 **Telegram User Information**\n\n{json_text}" + result_text
                    
                    # Split if too long
                    if len(result_text) > 4096:
                        chunks = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
                        for chunk in chunks:
                            bot.send_message(message.chat.id, chunk, 
                                          reply_markup=create_main_keyboard(), 
                                          parse_mode='Markdown', reply_to_message_id=message.message_id)
                    else:
                        bot.send_message(message.chat.id, result_text,
                                      reply_markup=create_main_keyboard(), 
                                      parse_mode='Markdown', reply_to_message_id=message.message_id)
                    
            except Exception as e:
                logger.error(f"Telegram search error: {e}")
                try:
                    bot.edit_message_text(
                        f"❌ **Search Failed**\n\n"
                        f"An error occurred while processing your request.\n"
                        f"Please try again later.",
                        message.chat.id, processing_msg.message_id,
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                except:
                    pass
        
        # Run search in thread
        executor.submit(search_and_respond)
    except Exception as e:
        logger.error(f"Error in telegram search handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.message_handler(commands=['pak'])
def handle_pakistan_search(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        
        # Check if user is verified and in channel
        if not check_user_verification(user_id, message):
            return
        
        # Check if in private and not admin
        if message.chat.type == 'private' and user_id not in ADMIN_IDS and not is_user_approved_private(user_id):
            bot.reply_to(message, 
                "⚠️ **This bot only works in groups!**\n\n"
                "Please add me to your group with 25+ members.",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check if group and group requirements (skip for super groups or groups with member limit removed)
        if message.chat.type != 'private' and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
            if is_group_banned(message.chat.id):
                bot.reply_to(message, "❌ This group is banned from using the bot.")
                return
                
            try:
                member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                if member_count < MIN_GROUP_MEMBERS:
                    bot.reply_to(message, 
                        f"⚠️ Group needs **{MIN_GROUP_MEMBERS}+ members** to use this bot.\n"
                        f"Current: **{member_count} members**",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                    return
            except:
                pass
        
        # Extract Pakistan number
        try:
            args = message.text.split(None, 1)[1]
            pak_number = re.sub(r'[^\d]', '', args)
            
            if not pak_number or len(pak_number) < 10:
                bot.reply_to(message, 
                    "❌ **Invalid Pakistan number format**\n\n"
                    "Please provide a valid Pakistan mobile number.\n"
                    "Example: `/pak 923041234567`",
                    reply_markup=create_main_keyboard(), parse_mode='Markdown')
                return
        except IndexError:
            bot.reply_to(message, 
                "❌ **Missing Pakistan number**\n\n"
                "Usage: `/pak <number>`\n"
                "Example: `/pak 923041234567`",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check daily limit
        can_search, message_text = check_daily_limit(user_id)
        if not can_search:
            bot.reply_to(message, f"⏳ **Search Limit Reached**\n\n{message_text}",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Send processing message
        processing_msg = bot.reply_to(message, 
            f"🔍 **Processing your request...**\n\n"
            f"🇵🇰 Searching for Pakistan number: **{pak_number}**\n"
            f"⏳ Please wait...",
            reply_markup=create_main_keyboard(), parse_mode='Markdown')
        
        def search_and_respond():
            try:
                # Perform search
                result = search_pakistan_number(pak_number)
                
                # Update search stats
                update_search_stats(user_id, "pakistan", pak_number)
                
                # Format results
                formatted_results = format_response(result, "pakistan")
                
                # Delete processing message
                try:
                    bot.delete_message(message.chat.id, processing_msg.message_id)
                except:
                    pass
                
                # Send summary message first for multiple results
                if len(formatted_results) > 1:
                    bot.send_message(message.chat.id, 
                        f"🇵🇰 **Found {len(result.get('results', []))} results for {pak_number}**\n\n"
                        f"Sending results in {len(formatted_results)} messages...",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown', reply_to_message_id=message.message_id)
                
                # Send each result
                for i, result_text in enumerate(formatted_results):
                    # Add JSON summary for each result
                    if result.get('success', False) and i < len(result.get('results', [])):
                        item = result.get('results', [])[i]
                        compact_data = {
                            "Mobile": item.get('Mobile', 'N/A'),
                            "Name": item.get('Name', 'N/A'),
                            "CNIC": item.get('CNIC', 'N/A')
                        }
                        
                        json_text = f"```json\n{json.dumps(compact_data, indent=1)}\n```\n\n"
                        result_text = f"🇵🇰 **Pakistan Number Result {i+1}/{len(formatted_results)}**\n\n{json_text}" + result_text
                    
                    # Split if too long
                    if len(result_text) > 4096:
                        chunks = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
                        for chunk in chunks:
                            bot.send_message(message.chat.id, chunk, 
                                          reply_markup=create_main_keyboard(), 
                                          parse_mode='Markdown', reply_to_message_id=message.message_id)
                    else:
                        bot.send_message(message.chat.id, result_text,
                                      reply_markup=create_main_keyboard(), 
                                      parse_mode='Markdown', reply_to_message_id=message.message_id)
                    
            except Exception as e:
                logger.error(f"Pakistan search error: {e}")
                try:
                    bot.edit_message_text(
                        f"❌ **Search Failed**\n\n"
                        f"An error occurred while processing your request.\n"
                        f"Please try again later.",
                        message.chat.id, processing_msg.message_id,
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                except:
                    pass
        
        # Run search in thread
        executor.submit(search_and_respond)
    except Exception as e:
        logger.error(f"Error in pakistan search handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.message_handler(commands=['rc'])
def handle_vehicle_search(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        
        # Check if user is verified and in channel
        if not check_user_verification(user_id, message):
            return
        
        # Check if in private and not admin
        if message.chat.type == 'private' and user_id not in ADMIN_IDS and not is_user_approved_private(user_id):
            bot.reply_to(message, 
                "⚠️ **This bot only works in groups!**\n\n"
                "Please add me to your group with 25+ members.",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check if group and group requirements (skip for super groups or groups with member limit removed)
        if message.chat.type != 'private' and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
            if is_group_banned(message.chat.id):
                bot.reply_to(message, "❌ This group is banned from using the bot.")
                return
                
            try:
                member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                if member_count < MIN_GROUP_MEMBERS:
                    bot.reply_to(message, 
                        f"⚠️ Group needs **{MIN_GROUP_MEMBERS}+ members** to use this bot.\n"
                        f"Current: **{member_count} members**",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                    return
            except:
                pass
        
        # Extract RC number
        try:
            args = message.text.split(None, 1)[1]
            rc_number = args.strip()
            
            if not rc_number:
                bot.reply_to(message, 
                    "❌ **Invalid RC number format**\n\n"
                    "Please provide a valid vehicle RC number.\n"
                    "Example: `/rc MH01AB1234`",
                    reply_markup=create_main_keyboard(), parse_mode='Markdown')
                return
        except IndexError:
            bot.reply_to(message, 
                "❌ **Missing RC number**\n\n"
                "Usage: `/rc <rc_number>`\n"
                "Example: `/rc MH01AB1234`",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check daily limit
        can_search, message_text = check_daily_limit(user_id)
        if not can_search:
            bot.reply_to(message, f"⏳ **Search Limit Reached**\n\n{message_text}",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Send processing message
        processing_msg = bot.reply_to(message, 
            f"🔍 **Processing your request...**\n\n"
            f"🚗 Searching for vehicle RC: **{rc_number}**\n"
            f"⏳ Please wait...",
            reply_markup=create_main_keyboard(), parse_mode='Markdown')
        
        def search_and_respond():
            try:
                # Perform search
                result = search_vehicle_rc(rc_number)
                
                # Update search stats
                update_search_stats(user_id, "vehicle", rc_number)
                
                # Format results
                formatted_results = format_response(result, "vehicle")
                
                # Delete processing message
                try:
                    bot.delete_message(message.chat.id, processing_msg.message_id)
                except:
                    pass
                
                # Send results
                for i, result_text in enumerate(formatted_results):
                    # Add JSON summary for the first batch
                    if i == 0 and isinstance(result, dict) and 'rc_number' in result:
                        compact_data = {
                            "rc_number": result.get('rc_number', 'N/A'),
                            "owner_name": result.get('owner_name', 'N/A'),
                            "maker_model": result.get('maker_model', 'N/A'),
                            "fuel_type": result.get('fuel_type', 'N/A')
                        }
                        
                        json_text = f"```json\n{json.dumps(compact_data, indent=1)}\n```\n\n"
                        result_text = f"🚗 **Vehicle RC Information**\n\n{json_text}" + result_text
                    
                    # Split if too long
                    if len(result_text) > 4096:
                        chunks = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
                        for chunk in chunks:
                            bot.send_message(message.chat.id, chunk, 
                                          reply_markup=create_main_keyboard(), 
                                          parse_mode='Markdown', reply_to_message_id=message.message_id)
                    else:
                        bot.send_message(message.chat.id, result_text,
                                      reply_markup=create_main_keyboard(), 
                                      parse_mode='Markdown', reply_to_message_id=message.message_id)
                    
            except Exception as e:
                logger.error(f"Vehicle RC search error: {e}")
                try:
                    bot.edit_message_text(
                        f"❌ **Search Failed**\n\n"
                        f"An error occurred while processing your request.\n"
                        f"Please try again later.",
                        message.chat.id, processing_msg.message_id,
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                except:
                    pass
        
        # Run search in thread
        executor.submit(search_and_respond)
    except Exception as e:
        logger.error(f"Error in vehicle search handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.message_handler(commands=['ip'])
def handle_ip_search(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        
        # Check if user is verified and in channel
        if not check_user_verification(user_id, message):
            return
        
        # Check if in private and not admin
        if message.chat.type == 'private' and user_id not in ADMIN_IDS and not is_user_approved_private(user_id):
            bot.reply_to(message, 
                "⚠️ **This bot only works in groups!**\n\n"
                "Please add me to your group with 25+ members.",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check if group and group requirements (skip for super groups or groups with member limit removed)
        if message.chat.type != 'private' and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
            if is_group_banned(message.chat.id):
                bot.reply_to(message, "❌ This group is banned from using the bot.")
                return
                
            try:
                member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                if member_count < MIN_GROUP_MEMBERS:
                    bot.reply_to(message, 
                        f"⚠️ Group needs **{MIN_GROUP_MEMBERS}+ members** to use this bot.\n"
                        f"Current: **{member_count} members**",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                    return
            except:
                pass
        
        # Extract IP address
        try:
            args = message.text.split(None, 1)[1]
            ip_address = args.strip()
            
            if not ip_address:
                bot.reply_to(message, 
                    "❌ **Invalid IP address format**\n\n"
                    "Please provide a valid IP address.\n"
                    "Example: `/ip 8.8.8.8`",
                    reply_markup=create_main_keyboard(), parse_mode='Markdown')
                return
        except IndexError:
            bot.reply_to(message, 
                "❌ **Missing IP address**\n\n"
                "Usage: `/ip <ip_address>`\n"
                "Example: `/ip 8.8.8.8`",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check daily limit
        can_search, message_text = check_daily_limit(user_id)
        if not can_search:
            bot.reply_to(message, f"⏳ **Search Limit Reached**\n\n{message_text}",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Send processing message
        processing_msg = bot.reply_to(message, 
            f"🔍 **Processing your request...**\n\n"
            f"🌐 Searching for IP address: **{ip_address}**\n"
            f"⏳ Please wait...",
            reply_markup=create_main_keyboard(), parse_mode='Markdown')
        
        def search_and_respond():
            try:
                # Perform search
                result = search_ip_info(ip_address)
                
                # Update search stats
                update_search_stats(user_id, "ip", ip_address)
                
                # Format results
                formatted_results = format_response(result, "ip")
                
                # Delete processing message
                try:
                    bot.delete_message(message.chat.id, processing_msg.message_id)
                except:
                    pass
                
                # Send results
                for i, result_text in enumerate(formatted_results):
                    # Add JSON summary for the first batch
                    if i == 0 and isinstance(result, dict) and 'ip' in result:
                        # Create a compact representation
                        compact_data = {
                            "ip": result.get('ip', 'N/A'),
                            "country_name": result.get('country_name', 'N/A'),
                            "city": result.get('city', 'N/A'),
                            "isp": result.get('isp', 'N/A')
                        }
                        
                        json_text = f"```json\n{json.dumps(compact_data, indent=1)}\n```\n\n"
                        result_text = f"🌐 **IP Information**\n\n{json_text}" + result_text
                    
                    # Split if too long
                    if len(result_text) > 4096:
                        chunks = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
                        for chunk in chunks:
                            bot.send_message(message.chat.id, chunk, 
                                          reply_markup=create_main_keyboard(), 
                                          parse_mode='Markdown', reply_to_message_id=message.message_id)
                    else:
                        bot.send_message(message.chat.id, result_text,
                                      reply_markup=create_main_keyboard(), 
                                      parse_mode='Markdown', reply_to_message_id=message.message_id)
                    
            except Exception as e:
                logger.error(f"IP search error: {e}")
                try:
                    bot.edit_message_text(
                        f"❌ **Search Failed**\n\n"
                        f"An error occurred while processing your request.\n"
                        f"Please try again later.",
                        message.chat.id, processing_msg.message_id,
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                except:
                    pass
        
        # Run search in thread
        executor.submit(search_and_respond)
    except Exception as e:
        logger.error(f"Error in IP search handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.message_handler(commands=['upi'])
def handle_upi_search(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        
        # Check if user is verified and in channel
        if not check_user_verification(user_id, message):
            return
        
        # Check if in private and not admin
        if message.chat.type == 'private' and user_id not in ADMIN_IDS and not is_user_approved_private(user_id):
            bot.reply_to(message, 
                "⚠️ **This bot only works in groups!**\n\n"
                "Please add me to your group with 25+ members.",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check if group and group requirements (skip for super groups or groups with member limit removed)
        if message.chat.type != 'private' and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
            if is_group_banned(message.chat.id):
                bot.reply_to(message, "❌ This group is banned from using the bot.")
                return
                
            try:
                member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                if member_count < MIN_GROUP_MEMBERS:
                    bot.reply_to(message, 
                        f"⚠️ Group needs **{MIN_GROUP_MEMBERS}+ members** to use this bot.\n"
                        f"Current: **{member_count} members**",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                    return
            except:
                pass
        
        # Extract UPI ID
        try:
            args = message.text.split(None, 1)[1]
            upi_id = args.strip()
            
            if not upi_id or '@' not in upi_id:
                bot.reply_to(message, 
                    "❌ **Invalid UPI ID format**\n\n"
                    "Please provide a valid UPI ID.\n"
                    "Example: `/upi rahul@upi`",
                    reply_markup=create_main_keyboard(), parse_mode='Markdown')
                return
        except IndexError:
            bot.reply_to(message, 
                "❌ **Missing UPI ID**\n\n"
                "Usage: `/upi <upi_id>`\n"
                "Example: `/upi rahul@upi`",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check daily limit
        can_search, message_text = check_daily_limit(user_id)
        if not can_search:
            bot.reply_to(message, f"⏳ **Search Limit Reached**\n\n{message_text}",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Send processing message
        processing_msg = bot.reply_to(message, 
            f"🔍 **Processing your request...**\n\n"
            f"💳 Searching for UPI ID: **{upi_id}**\n"
            f"⏳ Please wait...",
            reply_markup=create_main_keyboard(), parse_mode='Markdown')
        
        def search_and_respond():
            try:
                # Perform search
                result = search_upi_info(upi_id)
                
                # Update search stats
                update_search_stats(user_id, "upi", upi_id)
                
                # Format results
                formatted_results = format_response(result, "upi")
                
                # Delete processing message
                try:
                    bot.delete_message(message.chat.id, processing_msg.message_id)
                except:
                    pass
                
                # Send results
                for i, result_text in enumerate(formatted_results):
                    # Add JSON summary for the first batch
                    if i == 0 and isinstance(result, dict) and 'bank_details_raw' in result:
                        bank_details = result.get('bank_details_raw', {})
                        vpa_details = result.get('vpa_details', {})
                        
                        compact_data = {
                            "vpa": vpa_details.get('vpa', 'N/A'),
                            "name": vpa_details.get('name', 'N/A'),
                            "bank": bank_details.get('BANK', 'N/A'),
                            "ifsc": bank_details.get('IFSC', 'N/A')
                        }
                        
                        json_text = f"```json\n{json.dumps(compact_data, indent=1)}\n```\n\n"
                        result_text = f"💳 **UPI Information**\n\n{json_text}" + result_text
                    
                    # Split if too long
                    if len(result_text) > 4096:
                        chunks = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
                        for chunk in chunks:
                            bot.send_message(message.chat.id, chunk, 
                                          reply_markup=create_main_keyboard(), 
                                          parse_mode='Markdown', reply_to_message_id=message.message_id)
                    else:
                        bot.send_message(message.chat.id, result_text,
                                      reply_markup=create_main_keyboard(), 
                                      parse_mode='Markdown', reply_to_message_id=message.message_id)
                    
            except Exception as e:
                logger.error(f"UPI search error: {e}")
                try:
                    bot.edit_message_text(
                        f"❌ **Search Failed**\n\n"
                        f"An error occurred while processing your request.\n"
                        f"Please try again later.",
                        message.chat.id, processing_msg.message_id,
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                except:
                    pass
        
        # Run search in thread
        executor.submit(search_and_respond)
    except Exception as e:
        logger.error(f"Error in UPI search handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.message_handler(commands=['ifsc'])
def handle_ifsc_search(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        
        # Check if user is verified and in channel
        if not check_user_verification(user_id, message):
            return
        
        # Check if in private and not admin
        if message.chat.type == 'private' and user_id not in ADMIN_IDS and not is_user_approved_private(user_id):
            bot.reply_to(message, 
                "⚠️ **This bot only works in groups!**\n\n"
                "Please add me to your group with 25+ members.",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check if group and group requirements (skip for super groups or groups with member limit removed)
        if message.chat.type != 'private' and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
            if is_group_banned(message.chat.id):
                bot.reply_to(message, "❌ This group is banned from using the bot.")
                return
                
            try:
                member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                if member_count < MIN_GROUP_MEMBERS:
                    bot.reply_to(message, 
                        f"⚠️ Group needs **{MIN_GROUP_MEMBERS}+ members** to use this bot.\n"
                        f"Current: **{member_count} members**",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                    return
            except:
                pass
        
        # Extract IFSC code
        try:
            args = message.text.split(None, 1)[1]
            ifsc_code = args.strip().upper()
            
            if not ifsc_code or len(ifsc_code) != 11:
                bot.reply_to(message, 
                    "❌ **Invalid IFSC code format**\n\n"
                    "Please provide a valid 11-character IFSC code.\n"
                    "Example: `/ifsc BKID0006313`",
                    reply_markup=create_main_keyboard(), parse_mode='Markdown')
                return
        except IndexError:
            bot.reply_to(message, 
                "❌ **Missing IFSC code**\n\n"
                "Usage: `/ifsc <ifsc_code>`\n"
                "Example: `/ifsc BKID0006313`",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check daily limit
        can_search, message_text = check_daily_limit(user_id)
        if not can_search:
            bot.reply_to(message, f"⏳ **Search Limit Reached**\n\n{message_text}",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Send processing message
        processing_msg = bot.reply_to(message, 
            f"🔍 **Processing your request...**\n\n"
            f"🏦 Searching for IFSC code: **{ifsc_code}**\n"
            f"⏳ Please wait...",
            reply_markup=create_main_keyboard(), parse_mode='Markdown')
        
        def search_and_respond():
            try:
                # Perform search
                result = search_ifsc_info(ifsc_code)
                
                # Update search stats
                update_search_stats(user_id, "ifsc", ifsc_code)
                
                # Format results
                formatted_results = format_response(result, "ifsc")
                
                # Delete processing message
                try:
                    bot.delete_message(message.chat.id, processing_msg.message_id)
                except:
                    pass
                
                # Send results
                for i, result_text in enumerate(formatted_results):
                    # Add JSON summary for the first batch
                    if i == 0 and isinstance(result, dict) and 'IFSC' in result:
                        compact_data = {
                            "IFSC": result.get('IFSC', 'N/A'),
                            "BANK": result.get('BANK', 'N/A'),
                            "BRANCH": result.get('BRANCH', 'N/A'),
                            "ADDRESS": result.get('ADDRESS', 'N/A')
                        }
                        
                        json_text = f"```json\n{json.dumps(compact_data, indent=1)}\n```\n\n"
                        result_text = f"🏦 **IFSC Code Information**\n\n{json_text}" + result_text
                    
                    # Split if too long
                    if len(result_text) > 4096:
                        chunks = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
                        for chunk in chunks:
                            bot.send_message(message.chat.id, chunk, 
                                          reply_markup=create_main_keyboard(), 
                                          parse_mode='Markdown', reply_to_message_id=message.message_id)
                    else:
                        bot.send_message(message.chat.id, result_text,
                                      reply_markup=create_main_keyboard(), 
                                      parse_mode='Markdown', reply_to_message_id=message.message_id)
                    
            except Exception as e:
                logger.error(f"IFSC search error: {e}")
                try:
                    bot.edit_message_text(
                        f"❌ **Search Failed**\n\n"
                        f"An error occurred while processing your request.\n"
                        f"Please try again later.",
                        message.chat.id, processing_msg.message_id,
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                except:
                    pass
        
        # Run search in thread
        executor.submit(search_and_respond)
    except Exception as e:
        logger.error(f"Error in IFSC search handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.message_handler(commands=['email'])
def handle_email_search(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        
        # Check if user is verified and in channel
        if not check_user_verification(user_id, message):
            return
        
        # Check if in private and not admin
        if message.chat.type == 'private' and user_id not in ADMIN_IDS and not is_user_approved_private(user_id):
            bot.reply_to(message, 
                "⚠️ **This bot only works in groups!**\n\n"
                "Please add me to your group with 25+ members.",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check if group and group requirements (skip for super groups or groups with member limit removed)
        if message.chat.type != 'private' and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
            if is_group_banned(message.chat.id):
                bot.reply_to(message, "❌ This group is banned from using the bot.")
                return

        # Extract email from message
        command_parts = message.text.split()
        if len(command_parts) < 2:
            bot.reply_to(message, 
                "❌ **Invalid Format**\n\n"
                "Please provide an email address.\n\n"
                "**Usage:** `/email <email_address>`\n"
                "**Example:** `/email support@gmail.com`",
                parse_mode='Markdown')
            return

        email = command_parts[1].strip()
        
        # Basic email validation
        if '@' not in email or '.' not in email.split('@')[1]:
            bot.reply_to(message, 
                "❌ **Invalid Email Format**\n\n"
                "Please provide a valid email address.\n\n"
                "**Example:** `/email support@gmail.com`",
                parse_mode='Markdown')
            return

        # Check daily limit
        can_search, message_text = check_daily_limit(user_id)
        if not can_search:
            bot.reply_to(message, f"⏳ **Search Limit Reached**\n\n{message_text}",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return

        # Send processing message
        processing_msg = bot.reply_to(message, 
            f"🔍 **Processing your request...**\n\n"
            f"📧 Searching for: **{email}**\n"
            f"⏳ Please wait...",
            reply_markup=create_main_keyboard(), parse_mode='Markdown')

        def search_and_respond():
            try:
                # Perform email search
                result = search_email_info(email)
                
                # Debug logging
                logger.info(f"Email API Response: {json.dumps(result)}")
                
                # Update search stats
                update_search_stats(user_id, "email", email)
                
                # Format results
                formatted_results = format_response(result, "email")

                # Delete processing message
                try:
                    bot.delete_message(message.chat.id, processing_msg.message_id)
                except:
                    pass

                # Send results normally with raw and filtered data
                for i, result_text in enumerate(formatted_results):
                    # Split if too long
                    if len(result_text) > 4096:
                        chunks = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
                        for chunk in chunks:
                            bot.send_message(message.chat.id, chunk,
                                          reply_markup=create_main_keyboard(),
                                          parse_mode='Markdown', reply_to_message_id=message.message_id)
                    else:
                        bot.send_message(message.chat.id, result_text,
                                      reply_markup=create_main_keyboard(),
                                      parse_mode='Markdown', reply_to_message_id=message.message_id)
                    
            except Exception as e:
                logger.error(f"Email search error: {e}")
                try:
                    edit_message_with_tracking(
                        message.chat.id, processing_msg.message_id,
                        f"❌ **Search Failed**\n\n"
                        f"An error occurred while processing your request.\n"
                        f"Please try again later.",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                except:
                    pass
        
        # Run search in thread
        executor.submit(search_and_respond)
    except Exception as e:
        logger.error(f"Error in email search handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.message_handler(commands=['imcr'])
def handle_imcr_search(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        
        # Check if user is verified and in channel
        if not check_user_verification(user_id, message):
            return
        
        # Check if in private and not admin
        if message.chat.type == 'private' and user_id not in ADMIN_IDS and not is_user_approved_private(user_id):
            bot.reply_to(message, 
                "⚠️ **This bot only works in groups!**\n\n"
                "Please add me to your group with 25+ members.",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check if group and group requirements (skip for super groups or groups with member limit removed)
        if message.chat.type != 'private' and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
            if is_group_banned(message.chat.id):
                bot.reply_to(message, "❌ This group is banned from using the bot.")
                return
                
            try:
                member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                if member_count < MIN_GROUP_MEMBERS:
                    bot.reply_to(message, 
                        f"⚠️ Group needs **{MIN_GROUP_MEMBERS}+ members** to use this bot.\n"
                        f"Current: **{member_count} members**",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                    return
            except:
                pass
        
        # Extract phone number
        try:
            args = message.text.split(None, 1)[1]
            phone = clean_phone_number(args)
            
            if len(phone) != 10:
                bot.reply_to(message, 
                    "❌ **Invalid phone number format**\n\n"
                    "Please provide a valid 10-digit phone number.\n"
                    "Example: `/imcr 9876543210`",
                    reply_markup=create_main_keyboard(), parse_mode='Markdown')
                return
        except IndexError:
            bot.reply_to(message, 
                "❌ **Missing phone number**\n\n"
                "Usage: `/imcr <phone_number>`\n"
                "Example: `/imcr 9876543210`",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check daily limit
        can_search, message_text = check_daily_limit(user_id)
        if not can_search:
            bot.reply_to(message, f"⏳ **Search Limit Reached**\n\n{message_text}",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Send processing message
        processing_msg = bot.reply_to(message, 
            f"🔍 **Processing your request...**\n\n"
            f"📱 Searching for: **{phone}**\n"
            f"⏳ Please wait...",
            reply_markup=create_main_keyboard(), parse_mode='Markdown')
        
        def search_and_respond():
            try:
                # Perform search
                result = search_imcr(phone)
                
                # Debug logging
                logger.info(f"IMCR API Response: {json.dumps(result)}")
                
                # Update search stats
                update_search_stats(user_id, "imcr", phone)
                
                # Format results
                formatted_results = format_response(result, "imcr")

                # Delete processing message
                try:
                    bot.delete_message(message.chat.id, processing_msg.message_id)
                except:
                    pass

                # Send results normally with raw and filtered data
                for i, result_text in enumerate(formatted_results):
                    # Split if too long
                    if len(result_text) > 4096:
                        chunks = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
                        for chunk in chunks:
                            bot.send_message(message.chat.id, chunk,
                                          reply_markup=create_main_keyboard(),
                                          parse_mode='Markdown', reply_to_message_id=message.message_id)
                    else:
                        bot.send_message(message.chat.id, result_text,
                                      reply_markup=create_main_keyboard(),
                                      parse_mode='Markdown', reply_to_message_id=message.message_id)
                    
            except Exception as e:
                logger.error(f"IMCR search error: {e}")
                try:
                    edit_message_with_tracking(
                        message.chat.id, processing_msg.message_id,
                        f"❌ **Search Failed**\n\n"
                        f"An error occurred while processing your request.\n"
                        f"Please try again later.",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                except:
                    pass
        
        # Run search in thread
        executor.submit(search_and_respond)
    except Exception as e:
        logger.error(f"Error in IMCR search handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.message_handler(commands=['ff'])
def handle_freefire_search(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        
        # Check if user is verified and in channel
        if not check_user_verification(user_id, message):
            return
        
        # Check if in private and not admin
        if message.chat.type == 'private' and user_id not in ADMIN_IDS and not is_user_approved_private(user_id):
            bot.reply_to(message, 
                "⚠️ **This bot only works in groups!**\n\n"
                "Please add me to your group with 25+ members.",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check if group and group requirements (skip for super groups or groups with member limit removed)
        if message.chat.type != 'private' and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
            if is_group_banned(message.chat.id):
                bot.reply_to(message, "❌ This group is banned from using the bot.")
                return
                
            try:
                member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                if member_count < MIN_GROUP_MEMBERS:
                    bot.reply_to(message, 
                        f"⚠️ Group needs **{MIN_GROUP_MEMBERS}+ members** to use this bot.\n"
                        f"Current: **{member_count} members**",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                    return
            except:
                pass
        
        # Extract Free Fire UID
        try:
            args = message.text.split(None, 1)[1]
            uid = re.sub(r'[^\d]', '', args)
            
            if not uid:
                bot.reply_to(message, 
                    "❌ **Invalid Free Fire UID format**\n\n"
                    "Please provide a valid Free Fire UID.\n"
                    "Example: `/ff <uid>`",
                    reply_markup=create_main_keyboard(), parse_mode='Markdown')
                return
        except IndexError:
            bot.reply_to(message, 
                "❌ **Missing Free Fire UID**\n\n"
                "Usage: `/ff <uid>`\n"
                "Example: `/ff <uid>`",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check daily limit
        can_search, message_text = check_daily_limit(user_id)
        if not can_search:
            bot.reply_to(message, f"⏳ **Search Limit Reached**\n\n{message_text}",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Send processing message
        processing_msg = bot.reply_to(message, 
            f"🔍 **Processing your request...**\n\n"
            f"🔫 Searching for Free Fire UID: **{uid}**\n"
            f"⏳ Please wait...",
            reply_markup=create_main_keyboard(), parse_mode='Markdown')
        
        def search_and_respond():
            try:
                # Perform search
                result = search_freefire(uid)
                
                # Update search stats
                update_search_stats(user_id, "freefire", uid)
                
                # Format results
                formatted_results = format_response(result, "freefire")
                
                # Delete processing message
                try:
                    bot.delete_message(message.chat.id, processing_msg.message_id)
                except:
                    pass
                
                # Send results
                for i, result_text in enumerate(formatted_results):
                    # Split if too long
                    if len(result_text) > 4096:
                        chunks = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
                        for chunk in chunks:
                            bot.send_message(message.chat.id, chunk, 
                                          reply_markup=create_main_keyboard(), 
                                          parse_mode='Markdown', reply_to_message_id=message.message_id)
                    else:
                        bot.send_message(message.chat.id, result_text,
                                      reply_markup=create_main_keyboard(), 
                                      parse_mode='Markdown', reply_to_message_id=message.message_id)
                    
            except Exception as e:
                logger.error(f"Free Fire search error: {e}")
                try:
                    bot.edit_message_text(
                        f"❌ **Search Failed**\n\n"
                        f"An error occurred while processing your request.\n"
                        f"Please try again later.",
                        message.chat.id, processing_msg.message_id,
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                except:
                    pass
        
        # Run search in thread
        executor.submit(search_and_respond)
    except Exception as e:
        logger.error(f"Error in Free Fire search handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.message_handler(commands=['cnic'])
def handle_cnic_search(message):
    try:
        if is_anonymous(message):
            bot.reply_to(message, 
                "⚠️ **Anonymous Mode Not Supported**\n\n"
                "Please use the bot as an identified user. Start in private chat to verify.",
                parse_mode='Markdown')
            return

        user_id = message.from_user.id
        
        # Check if user is verified and in channel
        if not check_user_verification(user_id, message):
            return
        
        # Check if in private and not admin
        if message.chat.type == 'private' and user_id not in ADMIN_IDS and not is_user_approved_private(user_id):
            bot.reply_to(message, 
                "⚠️ **This bot only works in groups!**\n\n"
                "Please add me to your group with 25+ members.",
                reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return
        
        # Check if group and group requirements (skip for super groups or groups with member limit removed)
        if message.chat.type != 'private' and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
            if is_group_banned(message.chat.id):
                bot.reply_to(message, "❌ This group is banned from using the bot.")
                return
                
            try:
                member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                if member_count < MIN_GROUP_MEMBERS:
                    bot.reply_to(message, 
                        f"⚠️ Group needs **{MIN_GROUP_MEMBERS}+ members** to use this bot.\n"
                        f"Current: **{member_count} members**",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
                    return
            except:
                pass

        # Extract CNIC from message
        command_parts = message.text.split()
        if len(command_parts) < 2:
            bot.reply_to(message, 
                "❌ **Invalid Format**\n\n"
                "Please provide a CNIC number.\n\n"
                "**Usage:** `/cnic <cnic_number>`\n"
                "**Examples:** \n"
                "• `/cnic 15601-6938749-3`\n"
                "• `/cnic 156016938749３` (without dashes)",
                parse_mode='Markdown')
            return

        cnic_input = command_parts[1].strip()
        
        # Format CNIC correctly
        formatted_cnic = format_cnic(cnic_input)
        
        # Basic CNIC validation (13 digits)
        clean_cnic = re.sub(r'[^\d]', '', cnic_input)
        if len(clean_cnic) != 13:
            bot.reply_to(message, 
                "❌ **Invalid CNIC Format**\n\n"
                "Please provide a valid 13-digit CNIC number.\n\n"
                "**Examples:** \n"
                "• `/cnic 15601-6938749-3`\n"
                "• `/cnic 156016938749３` (without dashes)",
                parse_mode='Markdown')
            return

        # Check daily limit
        can_search, message_text = check_daily_limit(user_id)
        if not can_search:
            bot.reply_to(message, f"⏳ **Search Limit Reached**\n\n{message_text}",
                            reply_markup=create_main_keyboard(), parse_mode='Markdown')
            return

        # Send processing message
        processing_msg = bot.reply_to(message, 
            f"🔍 **Processing your request...**\n\n"
            f"🆔 Searching for CNIC: **{formatted_cnic}**\n"
            f"⏳ Please wait...",
            reply_markup=create_main_keyboard(), parse_mode='Markdown')

        def search_and_respond():
            try:
                # Perform CNIC search
                result = search_cnic_info(formatted_cnic)
                
                # Debug logging
                logger.info(f"CNIC API Response: {json.dumps(result)}")
                
                # Update search stats
                update_search_stats(user_id, "cnic", formatted_cnic)
                
                # Format results
                formatted_results = format_response(result, "cnic")
                
                # Delete processing message
                try:
                    bot.delete_message(message.chat.id, processing_msg.message_id)
                except:
                    pass
                
                # Send results
                for i, result_text in enumerate(formatted_results):
                    send_safe_message(message.chat.id, result_text,
                                      reply_markup=create_main_keyboard(), 
                                      reply_to_message_id=message.message_id)
                    
            except Exception as e:
                logger.error(f"CNIC search error: {e}")
                try:
                    edit_message_with_tracking(
                        message.chat.id, processing_msg.message_id,
                        f"❌ <b>Search Failed</b>\n\n"
                        f"An error occurred while processing your request.\n"
                        f"Please try again later.",
                        reply_markup=create_main_keyboard(), parse_mode='HTML')
                except:
                    pass
        
        # Run search in thread
        executor.submit(search_and_respond)
    except Exception as e:
        logger.error(f"Error in CNIC search handler: {e}")
        bot.reply_to(message, "❌ An error occurred. Please try again later.")

@bot.message_handler(commands=['delete'])
def handle_delete_command(message):
    try:
        # Only allow for admins
        if is_anonymous(message) or message.from_user.id not in ADMIN_IDS:
            return

        # Allow in private chat for admins
        if message.chat.type == 'private' and message.from_user.id not in ADMIN_IDS:
            bot.reply_to(message, 
                "❌ **Access Denied**\n\n"
                "Only admins can use this command.",
                parse_mode='Markdown', reply_to_message_id=message.message_id)
            return

        # Check if message has arguments
        try:
            args = message.text.split(None, 1)[1]
        except IndexError:
            bot.reply_to(message, 
                "❌ **Missing Message Link**\n\n"
                "Usage: `/delete <message_link>`\n"
                "Example: `/delete https://t.me/c/2765600677/3277`",
                parse_mode='Markdown', reply_to_message_id=message.message_id)
            return

        # Parse message link
        msg_link = args.strip()
        
        # Parse the message link to extract chat_id and message_id
        # Support both formats: https://t.me/c/2765600677/3277 or https://t.me/groupusername/3277
        import urllib.parse
        
        try:
            # Check if it's a group/channel link with ID (like t.me/c/...)
            if '/c/' in msg_link or 'chat' in msg_link:
                # For links like https://t.me/c/2765600677/3277
                parts = msg_link.split('/')
                if len(parts) >= 2:
                    chat_id = parts[-2]
                    message_id = int(parts[-1])
                    
                    # Convert to proper negative chat_id format if needed
                    if chat_id.isdigit():
                        chat_id = int(chat_id)
                        # For supergroups, we need to convert to negative ID
                        if chat_id > 1000000000000:  # This is a supergroup ID in positive format
                            chat_id = -(chat_id - 1000000000000)  # Convert to negative format
                        else:
                            chat_id = -int(chat_id)
                    else:
                        chat_id = int(chat_id)
                        
            elif msg_link.startswith('http'):
                # For links like https://t.me/groupusername/3277
                parsed = urllib.parse.urlparse(msg_link)
                path_parts = parsed.path.strip('/').split('/')
                if len(path_parts) >= 2:
                    # username is path_parts[0], message_id is path_parts[1]
                    username = path_parts[0]
                    message_id = int(path_parts[1])
                    
                    # Get chat_id from username
                    try:
                        chat = telegram_api_retry(bot.get_chat, f"@{username}")
                        chat_id = chat.id
                    except:
                        # If we can't get by username, try to use the username directly in the call
                        # In this case, we'll pass the username as-is
                        bot.reply_to(message, 
                            "❌ **Cannot process this link**\n\n"
                            "Please use the numeric chat ID format: `/delete https://t.me/c/2765600677/3277`",
                            parse_mode='Markdown', reply_to_message_id=message.message_id)
                        return
            else:
                bot.reply_to(message, 
                    "❌ **Invalid Message Link Format**\n\n"
                    "Please provide a valid message link.\n"
                    "Example: `/delete https://t.me/c/2765600677/3277`",
                    parse_mode='Markdown', reply_to_message_id=message.message_id)
                return
                
            # Try to get chat info to verify it exists and bot has access
            try:
                target_chat = telegram_api_retry(bot.get_chat, chat_id)
            except Exception as e:
                error_str = str(e)
                if "chat not found" in error_str.lower() or "group_deactivated" in error_str.lower():
                    bot.reply_to(message, 
                        "❌ **Chat Not Found**\n\n"
                        "The specified chat does not exist or has been deactivated.",
                        parse_mode='Markdown', reply_to_message_id=message.message_id)
                    return
                elif "bot was kicked" in error_str.lower() or "bot was blocked" in error_str.lower():
                    bot.reply_to(message, 
                        "❌ **Bot Kicked/Banned**\n\n"
                        "The bot has been kicked or banned from the target chat.",
                        parse_mode='Markdown', reply_to_message_id=message.message_id)
                    return
                # For other errors, continue and try to delete anyway
            
            # Check if the bot has permission to delete messages
            try:
                bot_admins = telegram_api_retry(bot.get_chat_administrators, chat_id)
                is_bot_admin = any(admin.user.id == bot.get_me().id for admin in bot_admins)
                
                if not is_bot_admin:
                    # Check if it's a supergroup or channel where bot might have different permissions
                    # For regular deletion, we'll still try to delete and handle the error appropriately
                    pass
            except:
                # If we can't check admin status, try to delete anyway
                # This handles cases like channels or if the bot is restricted
                pass
            
            # Try to delete the message
            try:
                telegram_api_retry(bot.delete_message, chat_id, message_id)
                bot.reply_to(message, 
                    f"✅ **Message Deleted**\n\n"
                    f"Successfully deleted message ID: `{message_id}`\n"
                    f"From chat ID: `{chat_id}`",
                    parse_mode='Markdown', reply_to_message_id=message.message_id)
            except Exception as e:
                # Check if it was a message not found error
                error_str = str(e)
                if "message to delete not found" in error_str.lower():
                    bot.reply_to(message, 
                        "❌ **Message Not Found**\n\n"
                        "The specified message could not be found or has already been deleted.",
                        parse_mode='Markdown', reply_to_message_id=message.message_id)
                else:
                    # Check if it's a permissions error
                    if "not enough rights" in error_str.lower() or "admin rights" in error_str.lower():
                        bot.reply_to(message, 
                            "❌ **Insufficient Permissions**\n\n"
                            "The bot doesn't have enough rights to delete messages in this group.",
                            parse_mode='Markdown', reply_to_message_id=message.message_id)
                    else:
                        bot.reply_to(message, 
                            f"❌ **Could Not Delete Message**\n\n"
                            f"An error occurred: `{str(e)}`",
                            parse_mode='Markdown', reply_to_message_id=message.message_id)
                
        except ValueError:
            bot.reply_to(message, 
                "❌ **Invalid Message ID**\n\n"
                "The message ID in the link is not valid. Please provide a valid message link.\n"
                "Example: `/delete https://t.me/c/2765600677/3277`",
                parse_mode='Markdown', reply_to_message_id=message.message_id)
        except Exception as e:
            logger.error(f"Error parsing message link: {e}")
            bot.reply_to(message, 
                "❌ **Invalid Message Link Format**\n\n"
                "Please provide a valid message link in the format:\n"
                "`/delete https://t.me/c/2765600677/3277`",
                parse_mode='Markdown', reply_to_message_id=message.message_id)
            
    except Exception as e:
        logger.error(f"Error in delete command: {e}")
        bot.reply_to(message, "❌ An error occurred while processing the delete command.")

# Admin commands
@bot.message_handler(commands=['approve'])
def handle_approve_user(message):
    try:
        if is_anonymous(message) or message.from_user.id not in ADMIN_IDS:
            return
        
        try:
            args = message.text.split(None, 1)[1]
            user_id = int(args)
            
            # Approve user for private use
            if approve_user_private(user_id):
                # Send confirmation to admin
                bot.reply_to(message, 
                    f"✅ **User Approved**\n\n"
                    f"User ID: `{user_id}`\n"
                    f"The user has been approved to use the bot in private chat.",
                    parse_mode='Markdown')
                
                # Send notification to user
                try:
                    bot.send_message(user_id, 
                        "🎉 **Congratulations you are approved by admin!**\n\n"
                        "You can now use the bot in private chat without needing to be in a group.\n\n"
                        "Use /help to see all available commands.",
                        parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"Error sending approval message to user {user_id}: {e}")
            else:
                bot.reply_to(message, 
                    f"❌ **Failed to Approve User**\n\n"
                    f"User ID: `{user_id}`\n"
                    f"An error occurred while approving the user.",
                    parse_mode='Markdown')
            
        except (IndexError, ValueError):
            bot.reply_to(message, 
                "❌ **Invalid format**\n\n"
                "Usage: `/approve <user_id>`\n"
                "Example: `/approve 123456789`",
                parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in approve command: {e}")
        bot.reply_to(message, f"❌ **Error approving user**\n\n{str(e)}")

@bot.message_handler(commands=['demote'])
def handle_demote_user(message):
    try:
        if is_anonymous(message) or message.from_user.id not in ADMIN_IDS:
            return
        
        try:
            args = message.text.split(None, 1)[1]
            user_id = int(args)
            
            # Demote user from private use
            if demote_user_private(user_id):
                # Send confirmation to admin
                bot.reply_to(message, 
                    f"🚫 **User Demoted**\n\n"
                    f"User ID: `{user_id}`\n"
                    f"The user has been demoted and can no longer use the bot in private chat.",
                    parse_mode='Markdown')
                
                # Send notification to user
                try:
                    bot.send_message(user_id, 
                        "😢 **Sad you are demoted by admin**\n\n"
                        "You can no longer use the bot in private chat. You need to be in a group with 25+ members to use the bot.",
                        parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"Error sending demotion message to user {user_id}: {e}")
            else:
                bot.reply_to(message, 
                    f"❌ **Failed to Demote User**\n\n"
                    f"User ID: `{user_id}`\n"
                    f"An error occurred while demoting the user.",
                    parse_mode='Markdown')
            
        except (IndexError, ValueError):
            bot.reply_to(message, 
                "❌ **Invalid format**\n\n"
                "Usage: `/demote <user_id>`\n"
                "Example: `/demote 123456789`",
                parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in demote command: {e}")
        bot.reply_to(message, f"❌ **Error demoting user**\n\n{str(e)}")

@bot.message_handler(commands=['remlimit'])
def handle_remove_member_limit(message):
    try:
        if is_anonymous(message) or message.from_user.id not in ADMIN_IDS:
            return
        
        try:
            args = message.text.split(None, 1)[1]
            group_id = int(args)
            
            # Don't allow modifying super groups
            if group_id in SUPER_GROUP_IDS:
                bot.reply_to(message, 
                    "❌ **Cannot modify super group**\n\n"
                    "This group is an official super group and cannot be modified.",
                    parse_mode='Markdown')
                return
            
            # Remove member limit for group
            if remove_group_member_limit(group_id):
                bot.reply_to(message, 
                    f"✅ **Member Limit Removed**\n\n"
                    f"Group ID: `{group_id}`\n"
                    f"The group can now use the bot without needing 25+ members.",
                    parse_mode='Markdown')
            else:
                bot.reply_to(message, 
                    f"❌ **Failed to Remove Member Limit**\n\n"
                    f"Group ID: `{group_id}`\n"
                    f"An error occurred while removing the member limit.",
                    parse_mode='Markdown')
            
        except (IndexError, ValueError):
            bot.reply_to(message, 
                "❌ **Invalid format**\n\n"
                "Usage: `/remlimit <group_id>`\n"
                "Example: `/remlimit -1001234567890`",
                parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in remlimit command: {e}")
        bot.reply_to(message, f"❌ **Error removing member limit**\n\n{str(e)}")

@bot.message_handler(commands=['fetch'])
def handle_fetch_db(message):
    try:
        if is_anonymous(message) or message.from_user.id not in ADMIN_IDS:
            return

        # Send DB file
        with open('zerovenom_bot.db', 'rb') as db_file:
            bot.send_document(
                message.chat.id,
                db_file,
                caption="📊 **ZeroVenom Bot Database Backup**\n\n"
                        f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        "🔐 Keep this file secure!",
                parse_mode='Markdown', reply_to_message_id=message.message_id
            )

        # Send statistics
        users = execute_db_query('SELECT COUNT(*) FROM users', fetch_one=True)
        searches = execute_db_query('SELECT COUNT(*) FROM searches', fetch_one=True)
        groups = execute_db_query('SELECT COUNT(*) FROM groups WHERE is_banned = 0', fetch_one=True)

        user_count = users[0] if users else 0
        search_count = searches[0] if searches else 0
        group_count = groups[0] if groups else 0

        db_size = os.path.getsize('zerovenom_bot.db') / (1024 * 1024)  # in MB

        stats_text = f"""
📊 **Database Statistics:**

👥 Users: {user_count}
🔍 Searches: {search_count}
👥 Groups: {group_count}
💾 Size: {db_size:.2f} MB
"""

        bot.send_message(message.chat.id, stats_text, parse_mode='Markdown', reply_to_message_id=message.message_id)

    except Exception as e:
        logger.error(f"Error in fetch command: {e}")
        bot.reply_to(message, f"❌ **Error fetching database**\n\n{str(e)}")


def cleanup_old_backups(days=1):
    try:
        cutoff_ts = time.time() - (days * 86400)
        for fname in os.listdir('.'):
            if fname.startswith('bot_backup_') and fname.endswith('.zip'):
                fpath = os.path.join('.', fname)
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff_ts:
                    os.remove(fpath)
    except Exception as e:
        logger.error(f"Error cleaning old backups: {e}")


def create_full_backup_zip():
    import zipfile
    import os

    zip_filename = f"bot_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk('.'):
            dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', 'venv', 'env', '.vscode', '.idea', 'node_modules', 'telbot']]
            for file in files:
                if not (file.endswith('.pyc') or file.endswith('.pyo') or
                        file == zip_filename or file.startswith('.') or
                        file.endswith('.zip') or file in ['bot.log']):
                    file_path = os.path.join(root, file)
                    zipf.write(file_path, os.path.relpath(file_path, '.'))

    # Stats
    users = execute_db_query('SELECT COUNT(*) FROM users', fetch_one=True)
    searches = execute_db_query('SELECT COUNT(*) FROM searches', fetch_one=True)
    groups = execute_db_query('SELECT COUNT(*) FROM groups WHERE is_banned = 0', fetch_one=True)

    user_count = users[0] if users else 0
    search_count = searches[0] if searches else 0
    group_count = groups[0] if groups else 0

    total_size = 0
    for dirpath, dirnames, filenames in os.walk('.'):
        dirnames[:] = [d for d in dirnames if d not in ['__pycache__', '.git', 'venv', 'env', '.vscode', '.idea', 'node_modules', 'telbot']]
        for f in filenames:
            if not (f.endswith('.pyc') or f.endswith('.pyo') or
                    f == zip_filename or f.startswith('.') or
                    f.endswith('.zip') or f in ['bot.log']):
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)

    size_mb = total_size / (1024 * 1024)

    stats_text = f"""
📊 **Backup Statistics:**

👥 Users: {user_count}
🔍 Searches: {search_count}
👥 Groups: {group_count}
💾 Total Size: {size_mb:.2f} MB
"""

    return zip_filename, stats_text


def send_full_backup_to_admins(zip_filename, caption, origin_chat_id=None, reply_to_message_id=None):
    with open(zip_filename, 'rb') as zip_file:
        for admin_id in ADMIN_IDS:
            try:
                bot.send_document(
                    admin_id,
                    zip_file,
                    caption=caption,
                    parse_mode='Markdown',
                    reply_to_message_id=reply_to_message_id if admin_id == origin_chat_id else None
                )
            except Exception as e:
                logger.error(f"Error sending backup to admin {admin_id}: {e}")
            finally:
                zip_file.seek(0)

def auto_backup_worker(start_time):
    while True:
        try:
            cleanup_old_backups(days=1)
            zip_filename, _stats_text = create_full_backup_zip()
            caption = (
                "📦 **ZeroVenom Bot Auto Backup**\n\n"
                f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🟢 Bot start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                "⏱️ Auto backup interval: 24 hours"
            )
            send_full_backup_to_admins(zip_filename, caption)
            os.remove(zip_filename)
        except Exception as e:
            logger.error(f"Error in auto backup worker: {e}")

        time.sleep(AUTO_BACKUP_INTERVAL_SECONDS)


@bot.message_handler(commands=['fetchall'])
def handle_fetch_all(message):
    try:
        if is_anonymous(message) or message.from_user.id not in ADMIN_IDS:
            return

        cleanup_old_backups(days=1)
        zip_filename, stats_text = create_full_backup_zip()

        caption = (
            "📦 **ZeroVenom Bot Complete Backup**\n\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "🔐 All bot files included in this backup!"
        )

        send_full_backup_to_admins(
            zip_filename,
            caption,
            origin_chat_id=message.chat.id,
            reply_to_message_id=message.message_id
        )

        os.remove(zip_filename)

        # Send statistics to the requester
        bot.send_message(message.chat.id, stats_text, parse_mode='Markdown', reply_to_message_id=message.message_id)

    except Exception as e:
        logger.error(f"Error in fetchall command: {e}")
        bot.reply_to(message, f"❌ **Error creating backup**\n\n{str(e)}")


@bot.message_handler(commands=['backup'])
def handle_backup(message):
    try:
        if is_anonymous(message) or message.from_user.id not in ADMIN_IDS:
            return

        cleanup_old_backups(days=1)
        zip_filename, stats_text = create_full_backup_zip()

        with open(zip_filename, 'rb') as zip_file:
            bot.send_document(
                message.chat.id,
                zip_file,
                caption=(
                    "📦 **ZeroVenom Bot Complete Backup**\n\n"
                    f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    "🔐 All bot files (including DB) included in this backup!"
                ),
                parse_mode='Markdown', reply_to_message_id=message.message_id
            )

        os.remove(zip_filename)
        bot.send_message(message.chat.id, stats_text, parse_mode='Markdown', reply_to_message_id=message.message_id)

    except Exception as e:
        logger.error(f"Error in backup command: {e}")
        bot.reply_to(message, f"❌ **Error creating backup**\n\n{str(e)}")

@bot.message_handler(commands=['status'])
def handle_status(message):
    try:
        if is_anonymous(message) or message.from_user.id not in ADMIN_IDS:
            return
        
        # Get statistics
        total_users = execute_db_query('SELECT COUNT(*) FROM users', fetch_one=True)
        verified_users = execute_db_query('SELECT COUNT(*) FROM users WHERE is_verified = 1', fetch_one=True)
        approved_private_users = execute_db_query('SELECT COUNT(*) FROM users WHERE is_approved_private = 1', fetch_one=True)
        total_groups = execute_db_query('SELECT COUNT(*) FROM groups WHERE is_banned = 0', fetch_one=True)
        banned_groups = execute_db_query('SELECT COUNT(*) FROM groups WHERE is_banned = 1', fetch_one=True)
        no_limit_groups = execute_db_query('SELECT COUNT(*) FROM groups WHERE no_member_limit = 1', fetch_one=True)
        today_searches = execute_db_query('SELECT COUNT(*) FROM searches WHERE timestamp >= date("now")', fetch_one=True)
        total_searches = execute_db_query('SELECT COUNT(*) FROM searches', fetch_one=True)
        mobile_searches = execute_db_query('SELECT COUNT(*) FROM searches WHERE search_type = "mobile"', fetch_one=True)
        aadhar_searches = execute_db_query('SELECT COUNT(*) FROM searches WHERE search_type = "aadhar"', fetch_one=True)
        telegram_searches = execute_db_query('SELECT COUNT(*) FROM searches WHERE search_type = "telegram"', fetch_one=True)
        pakistan_searches = execute_db_query('SELECT COUNT(*) FROM searches WHERE search_type = "pakistan"', fetch_one=True)
        vehicle_searches = execute_db_query('SELECT COUNT(*) FROM searches WHERE search_type = "vehicle"', fetch_one=True)
        ip_searches = execute_db_query('SELECT COUNT(*) FROM searches WHERE search_type = "ip"', fetch_one=True)
        upi_searches = execute_db_query('SELECT COUNT(*) FROM searches WHERE search_type = "upi"', fetch_one=True)
        ifsc_searches = execute_db_query('SELECT COUNT(*) FROM searches WHERE search_type = "ifsc"', fetch_one=True)
        
        # Calculate cache statistics
        cache_stats = f"Cache Size: {len(search_cache)}/{CACHE_SIZE}"
        
        status_text = f"""
📊 **ZeroVenom Bot Statistics**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👥 **Users:** {total_users[0] if total_users else 0}
✅ **Verified Users:** {verified_users[0] if verified_users else 0}
🔓 **Approved for Private:** {approved_private_users[0] if approved_private_users else 0}
👥 **Active Groups:** {total_groups[0] if total_groups else 0}
🚫 **Banned Groups:** {banned_groups[0] if banned_groups else 0}
⛔ **No Member Limit Groups:** {no_limit_groups[0] if no_limit_groups else 0}

🔍 **Search Statistics:**
• **Today's Searches:** {today_searches[0] if today_searches else 0}
• **Total Searches:** {total_searches[0] if total_searches else 0}
• **Mobile Searches:** {mobile_searches[0] if mobile_searches else 0}
• **Aadhar Searches:** {aadhar_searches[0] if aadhar_searches else 0}
• **Telegram Searches:** {telegram_searches[0] if telegram_searches else 0}
• **Pakistan Searches:** {pakistan_searches[0] if pakistan_searches else 0}
• **Vehicle Searches:** {vehicle_searches[0] if vehicle_searches else 0}
• **IP Searches:** {ip_searches[0] if ip_searches else 0}
• **UPI Searches:** {upi_searches[0] if upi_searches else 0}
• **IFSC Searches:** {ifsc_searches[0] if ifsc_searches else 0}
• **{cache_stats}**

⚡ **Bot Configuration:**
• **Bot Status:** Online
• **Daily Limit:** {DAILY_LIMIT}
• **Min Members:** {MIN_GROUP_MEMBERS}
• **Super Groups:** {len(SUPER_GROUP_IDS)}
• **Thread Pool:** {executor._max_workers} workers

**System:** Healthy ✅
"""
        
        bot.reply_to(message, status_text, 
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in status command: {e}")
        bot.reply_to(message, f"❌ **Error getting status**\n\n{str(e)}")

@bot.message_handler(commands=['groups'])
def handle_groups(message):
    try:
        if is_anonymous(message) or message.from_user.id not in ADMIN_IDS:
            return
        
        groups = execute_db_query(
            'SELECT group_id, group_title, member_count, is_banned, no_member_limit, group_username, group_invite_link FROM groups ORDER BY added_date DESC',
            fetch_all=True
        )
        
        if not groups:
            bot.reply_to(message, "📭 No groups found.")
            return
        
        # Send groups in batches of 15
        batch_size = 15
        total_groups = len(groups)
        
        for i in range(0, total_groups, batch_size):
            batch = groups[i:i+batch_size]
            batch_number = i // batch_size + 1
            total_batches = (total_groups + batch_size - 1) // batch_size
            
            groups_text = f"👥 **Bot Groups (Page {batch_number}/{total_batches}):**\n━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for group in batch:
                group_id, title, member_count, is_banned, no_member_limit, group_username, group_invite_link = group
                status = "🚫 BANNED" if is_banned else "✅ Active"
                if group_id in SUPER_GROUP_IDS:
                    status = "🌟 SUPER GROUP"
                elif no_member_limit:
                    status = "⛔ NO LIMIT"
                
                # Escape special characters in title to prevent markdown parsing issues
                safe_title = title.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')
                
                groups_text += f"**{safe_title}**\n"
                groups_text += f"ID: `{group_id}`\n"
                groups_text += f"Members: {member_count}\n"
                groups_text += f"Status: {status}\n"
                
                # Add group link if available
                if group_username:
                    groups_text += f"Link: [Click here](https://t.me/{group_username})\n"
                elif group_invite_link:
                    groups_text += f"Link: [Click here]({group_invite_link})\n"
                else:
                    groups_text += "Link: Not available\n"
                
                groups_text += "\n"
            
            # Send the batch
            bot.send_message(message.chat.id, groups_text, 
                           reply_markup=create_main_keyboard(), 
                           parse_mode='Markdown', reply_to_message_id=message.message_id)
    except Exception as e:
        logger.error(f"Error in groups command: {e}")
        bot.reply_to(message, f"❌ **Error getting groups**\n\n{str(e)}")

@bot.message_handler(commands=['ban'])
def handle_ban_group(message):
    try:
        if is_anonymous(message) or message.from_user.id not in ADMIN_IDS:
            return
        
        try:
            args = message.text.split(None, 1)[1]
            group_id = int(args)
            
            # Don't allow banning super groups
            if group_id in SUPER_GROUP_IDS:
                bot.reply_to(message, 
                    "❌ **Cannot ban super group**\n\n"
                    "This group is an official super group and cannot be banned.",
                    parse_mode='Markdown')
                return
            
            # Execute ban in background
            executor.submit(ban_group, group_id)
            
            bot.reply_to(message, 
                f"🚫 **Group Banned**\n\nGroup ID: `{group_id}`\n"
                f"The group has been banned from using the bot.",
                parse_mode='Markdown')
            
        except (IndexError, ValueError):
            bot.reply_to(message, 
                "❌ **Invalid format**\n\n"
                "Usage: `/ban <group_id>`\n"
                "Example: `/ban -1001234567890`",
                parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in ban command: {e}")
        bot.reply_to(message, f"❌ **Error banning group**\n\n{str(e)}")

@bot.message_handler(commands=['broadcast'])
def handle_broadcast(message):
    try:
        if is_anonymous(message) or message.from_user.id not in ADMIN_IDS:
            return

        if not message.reply_to_message:
            bot.reply_to(message,
                "❌ **Reply to a message to broadcast**\n\n"
                "Usage: Reply to a message and use `/broadcast <count>`\n"
                "Example: `/broadcast 5`")
            return

        try:
            args = message.text.split(None, 1)
            count = int(args[1]) if len(args) > 1 else 1

            if count > 10:
                bot.reply_to(message, "❌ Maximum broadcast count is 10")
                return

            # Get total counts before broadcasting
            total_users = execute_db_query('SELECT COUNT(*) FROM users', fetch_one=True)
            total_groups = execute_db_query('SELECT COUNT(*) FROM groups WHERE is_banned = 0', fetch_one=True)

            total_users_count = total_users[0] if total_users else 0
            total_groups_count = total_groups[0] if total_groups else 0
            total_targets = total_users_count + total_groups_count

            if total_targets == 0:
                bot.reply_to(message, "❌ No users or groups to broadcast to!")
                return

            broadcast_message = message.reply_to_message

            # Create a message to track broadcast progress (sent initially)
            progress_msg = bot.reply_to(message,
                f"🚀 **Broadcasting Started...**\n\n"
                f"📊 **Statistics:**\n"
                f"👥 Total Users: {total_users_count}\n"
                f"ParallelGroups: {total_groups_count}\n"
                f"🎯 Total Targets: {total_targets}\n"
                f"🔁 Broadcast Count: {count}\n\n"
                f"📤 **Sending in progress...**\n"
                f"✅ Sent: 0\n"
                f"❌ Failed: 0\n"
                f"⚡ Speed: Calculating...")

            # Shared variables to track progress using a thread-safe approach
            import threading
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import queue

            sent_count = 0
            failed_count = 0
            stats_lock = threading.Lock()

            def send_single_message(target_id):
                try:
                    if broadcast_message.text:
                        # Try sending with markdown first, then plain text if it fails
                        try:
                            bot.send_message(target_id, broadcast_message.text,
                                           reply_markup=create_main_keyboard(),
                                           parse_mode='Markdown')
                        except:
                            bot.send_message(target_id, broadcast_message.text,
                                           reply_markup=create_main_keyboard())
                    elif broadcast_message.photo:
                        bot.send_photo(target_id, broadcast_message.photo[-1].file_id,
                                     caption=broadcast_message.caption,
                                     reply_markup=create_main_keyboard())

                    # Update stats
                    with stats_lock:
                        nonlocal sent_count
                        sent_count += 1
                    return True
                except Exception as e:
                    with stats_lock:
                        nonlocal failed_count
                        failed_count += 1
                    return False

            def broadcast_worker():
                nonlocal sent_count, failed_count

                # Fetch all users and groups once
                user_ids = execute_db_query('SELECT user_id FROM users', fetch_all=True)
                user_ids = [user[0] for user in user_ids] if user_ids else []

                group_ids = execute_db_query('SELECT group_id FROM groups WHERE is_banned = 0', fetch_all=True)
                group_ids = [group[0] for group in group_ids] if group_ids else []

                # Create a list of all targets to broadcast to (users + groups for each count)
                all_targets = []
                for _ in range(count):
                    all_targets.extend(user_ids)
                    all_targets.extend(group_ids)

                # Update progress initially
                total_to_send = len(all_targets)
                if total_to_send == 0:
                    try:
                        bot.edit_message_text(
                            "❌ No targets to broadcast to!",
                            chat_id=progress_msg.chat.id,
                            message_id=progress_msg.message_id,
                            parse_mode='Markdown')
                    except:
                        pass
                    return

                # Use ThreadPoolExecutor for parallel sending with limited workers to avoid rate limiting
                max_workers = 20  # Adjust based on your needs
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # Submit all tasks
                    futures = [executor.submit(send_single_message, target_id) for target_id in all_targets]

                    # Update progress as tasks complete
                    completed = 0
                    update_interval = max(1, total_to_send // 20)  # Update ~20 times during broadcast

                    for i, future in enumerate(as_completed(futures)):
                        completed += 1

                        # Update progress periodically
                        if completed % update_interval == 0 or completed == total_to_send:
                            time.sleep(0.1)  # Small delay to avoid rate limiting
                            try:
                                with stats_lock:
                                    current_sent = sent_count
                                    current_failed = failed_count
                                    progress_percent = (completed / total_to_send) * 100
                                    progress_text = (
                                        f"🚀 **Broadcasting in Progress...**\n\n"
                                        f"📊 **Statistics:**\n"
                                        f"👥 Total Users: {total_users_count}\n"
                                        f"ParallelGroups: {total_groups_count}\n"
                                        f"🎯 Total Targets: {total_targets}\n"
                                        f"🔁 Broadcast Count: {count}\n\n"
                                        f"📤 **Sending Status:**\n"
                                        f"✅ Sent: {current_sent}\n"
                                        f"❌ Failed: {current_failed}\n"
                                        f"🎯 Progress: {progress_percent:.1f}% ({completed}/{total_to_send})")

                                bot.edit_message_text(
                                    progress_text,
                                    chat_id=progress_msg.chat.id,
                                    message_id=progress_msg.message_id,
                                    parse_mode='Markdown')
                            except:
                                pass  # If updating progress fails, continue anyway

                # Final update when done
                try:
                    with stats_lock:
                        final_sent = sent_count
                        final_failed = failed_count
                        success_rate = (final_sent / (final_sent + final_failed) * 100) if (final_sent + final_failed) > 0 else 0
                        final_text = (
                            f"✅ **Broadcast Completed!**\n\n"
                            f"📊 **Final Statistics:**\n"
                            f"👥 Total Users: {total_users_count}\n"
                            f"ParallelGroups: {total_groups_count}\n"
                            f"🎯 Total Targets: {total_targets}\n"
                            f"🔁 Broadcast Count: {count}\n\n"
                            f"📤 **Results:**\n"
                            f"✅ Successfully Sent: {final_sent}\n"
                            f"❌ Failed: {final_failed}\n"
                            f"🎯 Total Attempted: {final_sent + final_failed}\n"
                            f"⚡ Success Rate: {success_rate:.1f}%")

                    bot.edit_message_text(
                        final_text,
                        chat_id=progress_msg.chat.id,
                        message_id=progress_msg.message_id,
                        parse_mode='Markdown')
                except Exception as edit_error:
                    # If editing fails, send a new message with results
                    try:
                        bot.reply_to(message,
                            f"✅ **Broadcast Completed!**\n\n"
                            f"📊 **Final Statistics:**\n"
                            f"👥 Total Users: {total_users_count}\n"
                            f"ParallelGroups: {total_groups_count}\n"
                            f"🎯 Total Targets: {total_targets}\n"
                            f"🔁 Broadcast Count: {count}\n\n"
                            f"📤 **Results:**\n"
                            f"✅ Successfully Sent: {sent_count}\n"
                            f"❌ Failed: {failed_count}\n"
                            f"🎯 Total Attempted: {sent_count + failed_count}\n"
                            f"⚡ Success Rate: {(sent_count / (sent_count + failed_count) * 100):.1f}%"
                            if (sent_count + failed_count) > 0 else "⚡ Success Rate: 0%")
                    except:
                        pass

            # Start the broadcast in a separate thread
            executor.submit(broadcast_worker)

        except (IndexError, ValueError):
            bot.reply_to(message,
                "❌ **Invalid format**\n\n"
                "Usage: Reply to a message and use `/broadcast <count>`\n"
                "Example: `/broadcast 5`")
    except Exception as e:
        logger.error(f"Error in broadcast command: {e}")
        bot.reply_to(message, f"❌ **Error broadcasting**\n\n{str(e)}")

# New logs command for admins
@bot.message_handler(commands=['logs'])
def handle_logs(message):
    try:
        if is_anonymous(message) or message.from_user.id not in ADMIN_IDS:
            return
        
        try:
            # Read log file
            with open("bot.log", "r") as f:
                log_content = f.read()
            
            # If log is too large, send only the last part
            if len(log_content) > 4096:
                # Get the last 4096 characters
                log_content = log_content[-4096:]
            
            # Create a text file with the logs
            log_file = io.StringIO(log_content)
            log_file.name = f"bot_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            bot.send_document(
                message.chat.id,
                log_file,
                caption=f"📋 **Bot Logs**\n\n"
                        f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"📊 Log size: {len(log_content)} bytes",
                parse_mode='Markdown',
                reply_to_message_id=message.message_id
            )
            
            # Also send a preview of the last 20 lines
            lines = log_content.split('\n')
            preview = '\n'.join(lines[-20:]) if len(lines) > 20 else log_content
            
            bot.send_message(
                message.chat.id,
                f"🔍 **Last 20 log entries:**\n\n```\n{preview}\n```",
                parse_mode='Markdown',
                reply_to_message_id=message.message_id
            )
            
        except Exception as e:
            logger.error(f"Error reading logs: {e}")
            bot.reply_to(message, f"❌ **Error reading logs**\n\n{str(e)}")
    except Exception as e:
        logger.error(f"Error in logs command: {e}")
        bot.reply_to(message, f"❌ **Error getting logs**\n\n{str(e)}")

# Track welcomed groups to show welcome message only once
welcomed_groups = set()

# Welcome new members
@bot.message_handler(content_types=['new_chat_members'])
def handle_new_member(message):
    try:
        for new_member in message.new_chat_members:
            if new_member.id == bot.get_me().id:
                # Bot was added to group - show welcome message only once
                if message.chat.id not in welcomed_groups:
                    welcomed_groups.add(message.chat.id)
                    
                    # Run group checks in background
                    def process_new_group():
                        try:
                            member_count = telegram_api_retry(bot.get_chat_members_count, message.chat.id)
                            # Skip member count check for super groups or groups with member limit removed
                            if member_count < MIN_GROUP_MEMBERS and message.chat.id not in SUPER_GROUP_IDS and not is_group_member_limit_removed(message.chat.id):
                                bot.reply_to(message, 
                                    f"⚠️ **Group Requirements Not Met**\n\n"
                                    f"🚫 This bot requires groups with **{MIN_GROUP_MEMBERS}+ members**\n"
                                    f"👥 Current members: **{member_count}**\n\n"
                                    f"📈 Please invite more members to activate the bot.",
                                    reply_markup=create_main_keyboard(), parse_mode='Markdown')
                                return
                            
                            add_group(message.chat.id, message.chat.title, member_count)
                            
                            # Check if bot is admin
                            try:
                                bot_admins = telegram_api_retry(bot.get_chat_administrators, message.chat.id)
                                is_admin = any(admin.user.id == bot.get_me().id for admin in bot_admins)
                                
                                if not is_admin:
                                    # Bot is not admin, send message with button
                                    bot.reply_to(message, 
                                        f"⚠️ **Bot Admin Required**\n\n"
                                        f"👑 Please make this bot admin in this group to use all features.\n\n"
                                        f"Click the button below to promote the bot:",
                                        reply_markup=create_admin_keyboard(), parse_mode='Markdown')
                                else:
                                    # Bot is admin, proceed with normal welcome
                                    # Different welcome message for super groups
                                    if message.chat.id in SUPER_GROUP_IDS:
                                        welcome_text = f"""🔥 <b>ZeroVenom OSINT Bot Activated in Official Group!</b>

✨ <b>All features available without verification!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>Bot successfully added to the official group!</b>

🔍 <b>Available Commands:</b>
• /num &lt;mobile&gt; - Mobile number lookup
• /adh &lt;aadhar&gt; - Aadhar information search
• /tg &lt;user_id&gt; - Telegram user info
• /pak &lt;number&gt; - Pakistan number lookup
• /rc &lt;rc_number&gt; - Vehicle RC lookup
• /ip &lt;ip_address&gt; - IP address lookup
• /upi &lt;upi_id&gt; - UPI information lookup
• /ifsc &lt;ifsc_code&gt; - IFSC code lookup
• /help - Show all commands and features

⚡ <b>Quick Features:</b>
• Mobile number lookup
• Aadhar information search  
• Telegram user info
• Pakistan number lookup
• Vehicle RC lookup
• IP address lookup
• UPI information lookup
• IFSC code lookup
• Daily limit: {DAILY_LIMIT} searches per user
• Professional JSON responses
• No verification required!

<b>⚠️ Disclaimer:</b> Educational use only. Users responsible for ethical usage."""
                                    else:
                                        welcome_text = f"""🔥 <b>ZeroVenom OSINT Bot Activated!</b>

✨ <b>Ready to serve your OSINT needs</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>Bot successfully added to your group!</b>

⚠️ <b>Verification Required</b>: All users must join our channel and verify before using the bot.

🔍 <b>Available Commands:</b>
• /num &lt;mobile&gt; - Mobile number lookup
• /adh &lt;aadhar&gt; - Aadhar information search
• /tg &lt;user_id&gt; - Telegram user info
• /pak &lt;number&gt; - Pakistan number lookup
• /rc &lt;rc_number&gt; - Vehicle RC lookup
• /ip &lt;ip_address&gt; - IP address lookup
• /upi &lt;upi_id&gt; - UPI information lookup
• /ifsc &lt;ifsc_code&gt; - IFSC code lookup
• /help - Show all commands and features

⚡ <b>Quick Features:</b>
• Mobile number lookup
• Aadhar information search  
• Telegram user info
• Pakistan number lookup
• Vehicle RC lookup
• IP address lookup
• UPI information lookup
• IFSC code lookup
• Daily limit: {DAILY_LIMIT} searches per user
• Professional JSON responses

<b>⚠️ Disclaimer:</b> Educational use only. Users responsible for ethical usage.

⚠️ <b>Note:</b> Even if it says verified, you still need to join the channel to use the bot."""
                                    
                                    bot.reply_to(message, welcome_text, 
                                                   reply_markup=create_main_keyboard(), 
                                                   parse_mode='HTML')
                            except Exception as e:
                                logger.error(f"Error checking bot admin status: {e}")
                                # Fallback to normal welcome if admin check fails
                                welcome_text = f"""🔥 <b>ZeroVenom OSINT Bot Activated!</b>

✨ <b>Ready to serve your OSINT needs</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>Bot successfully added to your group!</b>

⚠️ <b>Verification Required</b>: All users must join our channel and verify before using the bot.

🔍 <b>Available Commands:</b>
• /num &lt;mobile&gt; - Mobile number lookup
• /adh &lt;aadhar&gt; - Aadhar information search
• /tg &lt;user_id&gt; - Telegram user info
• /pak &lt;number&gt; - Pakistan number lookup
• /rc &lt;rc_number&gt; - Vehicle RC lookup
• /ip &lt;ip_address&gt; - IP address lookup
• /upi &lt;upi_id&gt; - UPI information lookup
• /ifsc &lt;ifsc_code&gt; - IFSC code lookup
• /help - Show all commands and features

⚡ <b>Quick Features:</b>
• Mobile number lookup
• Aadhar information search  
• Telegram user info
• Pakistan number lookup
• Vehicle RC lookup
• IP address lookup
• UPI information lookup
• IFSC code lookup
• Daily limit: {DAILY_LIMIT} searches per user
• Professional JSON responses

<b>⚠️ Disclaimer:</b> Educational use only. Users responsible for ethical usage.

⚠️ <b>Note:</b> Even if it says verified, you still need to join the channel to use the bot."""
                                
                                bot.reply_to(message, welcome_text, 
                                               reply_markup=create_main_keyboard(), 
                                               parse_mode='HTML')
                        except Exception as e:
                            logger.error(f"Error handling new bot member: {e}")
                    
                    executor.submit(process_new_group)
                else:
                    # Bot already welcomed, just show simple message
                    bot.reply_to(message, 
                        f"🤖 **ZeroVenom OSINT Bot**\n\n"
                        f"Use `/help` to explore commands and features!\n\n"
                        f"⚠️ **Remember:** All users must join our channel and verify before using the bot.\n\n"
                        f"⚠️ **Note:** Even if it says verified, you still need to join the channel to use the bot.",
                        reply_markup=create_main_keyboard(), parse_mode='Markdown')
            else:
                # Regular user joined - welcome with verification requirement (unless in super group)
                if message.chat.id in SUPER_GROUP_IDS:
                    # In super group, no verification needed
                    welcome_text = f"""👋 <b>Welcome {html.escape(new_member.first_name)}!</b>

🤖 You've joined the official <b>ZeroVenom OSINT Bot</b> group!

✨ <b>You can use all bot features without verification!</b>

🔍 <b>Available Commands:</b>
• /num &lt;mobile&gt; - Mobile number lookup
• /adh &lt;aadhar&gt; - Aadhar information search
• /tg &lt;user_id&gt; - Telegram user info
• /pak &lt;number&gt; - Pakistan number lookup
• /rc &lt;rc_number&gt; - Vehicle RC lookup
• /ip &lt;ip_address&gt; - IP address lookup
• /upi &lt;upi_id&gt; - UPI information lookup
• /ifsc &lt;ifsc_code&gt; - IFSC code lookup
• /help - Show all commands

Enjoy using the bot! 🚀"""
                    bot.reply_to(message, welcome_text, parse_mode='HTML')
                else:
                    # Normal verification required
                    welcome_text = f"""👋 <b>Welcome {html.escape(new_member.first_name)}!</b>

🤖 You've joined a group with <b>ZeroVenom OSINT Bot</b>

⚠️ <b>Important</b>: You need to join our channel and verify your account before using the bot.

Click the button below to get started:

⚠️ <b>Note:</b> Even if it says verified, you still need to join the channel to use the bot."""
                    bot.reply_to(message, welcome_text, 
                                   reply_markup=create_verification_keyboard(), 
                                   parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error handling new member: {e}")

# Handle all other messages to show buttons
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    try:
        if is_anonymous(message):
            return

        # Only respond in private chat for non-admins with attractive messages
        if message.chat.type == 'private' and message.from_user.id not in ADMIN_IDS:
            # Check if user is approved for private use
            if is_user_approved_private(message.from_user.id):
                # User is approved, show help message
                bot.reply_to(message, 
                    f"🔥 <b>ZeroVenom OSINT Bot</b>\n\n"
                    f"✅ <b>You're approved for private use!</b>\n"
                    f"Use /help to see all available commands.\n\n"
                    f"🔍 <b>Available Searches:</b>\n"
                    f"• Mobile number lookup\n"
                    f"• Aadhar information search\n"
                    f"• Telegram user info\n"
                    f"• Pakistan number lookup\n"
                    f"• Vehicle RC lookup\n"
                    f"• IP address lookup\n"
                    f"• UPI information lookup\n"
                    f"• IFSC code lookup\n\n"
                    f"Enjoy using the bot! 🚀",
                    reply_markup=create_main_keyboard(), 
                    parse_mode='HTML')
            else:
                # Random helpful messages with better UI
                import random
                messages = [
                    f"🔥 <b>ZeroVenom OSINT Bot</b>\n\n"
                    f"🚀 <b>Unlock advanced OSINT capabilities!</b>\n"
                    f"Add me to your group with 25+ members to get started.\n\n"
                    f"💡 Use /help to explore all features!\n\n"
                    f"⚠️ <b>Note:</b> Even if it says verified, you still need to join the channel to use the bot.",
                    
                    f"⚡ <b>Ready for Professional OSINT?</b>\n\n"
                    f"🎯 <b>Mobile &amp; Aadhar Lookup</b>\n"
                    f"👤 Telegram User Info\n"
                    f"🇵🇰 Pakistan Number Lookup\n"
                    f"🚗 Vehicle RC Lookup\n"
                    f"🌐 IP Address Lookup\n"
                    f"💳 UPI Information Lookup\n"
                    f"🏦 IFSC Code Lookup\n"
                    f"📊 Detailed JSON Responses\n"
                    f"🛡️ Secure &amp; Reliable\n\n"
                    f"🎮 Ready to start? Add me to your group!\n\n"
                    f"⚠️ <b>Note:</b> Even if it says verified, you still need to join the channel to use the bot.",
                    
                    f"🔍 <b>Advanced Search Capabilities</b>\n\n"
                    f"✨ <b>What I can do:</b>\n"
                    f"• Mobile number OSINT\n"
                    f"• Aadhar information lookup\n"
                    f"• Telegram user info\n"
                    f"• Pakistan number lookup\n"
                    f"• Vehicle RC lookup\n"
                    f"• IP address lookup\n"
                    f"• UPI information lookup\n"
                    f"• IFSC code lookup\n"
                    f"• Professional data formatting\n\n"
                    f"🎮 Ready to start? Add me to your group!\n\n"
                    f"⚠️ <b>Note:</b> Even if it says verified, you still need to join the channel to use the bot.",
                    
                    f"🤖 <b>ZeroVenom OSINT Bot</b>\n\n"
                    f"🏆 <b>Premium Features:</b>\n"
                    f"• Lightning-fast searches\n"
                    f"• JSON formatted responses\n"
                    f"• Daily search limits\n"
                    f"• Multiple search types\n\n"
                    f"🚀 Invite me to your group now!\n\n"
                    f"⚠️ <b>Note:</b> Even if it says verified, you still need to join the channel to use the bot."
                ]
                
                bot.reply_to(message, random.choice(messages),
                                reply_markup=create_main_keyboard(), 
                                parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error handling all messages: {e}")

# Cleanup function to run on shutdown
def cleanup():
    logger.info("Bot shutting down, cleaning up resources...")
    # Close all database connections
    db_pool.close_all()
    # Shutdown thread pool
    executor.shutdown(wait=False)

# Main function
def main():
    """Main function to start the bot"""
    print("🚀 Starting ZeroVenom OSINT Bot...")
    start_time = datetime.now()
    
    # Initialize database
    if not init_db():
        print("❌ Failed to initialize database. Please check permissions.")
        return
    
    # Set bot commands
    commands = [
        telebot.types.BotCommand("help", "Show help menu"),
        telebot.types.BotCommand("num", "Mobile number search"),
        telebot.types.BotCommand("adh", "Aadhar number search"),
        telebot.types.BotCommand("tg", "Telegram user info"),
        telebot.types.BotCommand("pak", "Pakistan number lookup"),
        telebot.types.BotCommand("rc", "Vehicle RC lookup"),
        telebot.types.BotCommand("ip", "IP address lookup"),
        telebot.types.BotCommand("upi", "UPI information lookup"),
        telebot.types.BotCommand("ifsc", "IFSC code lookup"),
        telebot.types.BotCommand("email", "Email to number lookup"),
        telebot.types.BotCommand("imcr", "ICMR information lookup"),
        telebot.types.BotCommand("cnic", "CNIC family info lookup"),
        telebot.types.BotCommand("ff", "Free Fire account lookup"),
        telebot.types.BotCommand("fetchall", "Backup all bot files (Admin only)"),
        telebot.types.BotCommand("backup", "Backup all bot files (Admin only)"),
        telebot.types.BotCommand("delete", "Delete message by link (Admin only)"),
    ]
    
    try:
        bot.set_my_commands(commands)
        print("✅ Bot commands set")
    except Exception as e:
        logger.error(f"Error setting bot commands: {e}")
    
    print("🔥 ZeroVenom OSINT Bot is now online!")
    print(f"📊 Bot username: @{bot.get_me().username}")
    print(f"👥 Admin IDs: {ADMIN_IDS}")
    print(f"📅 Daily limit: {DAILY_LIMIT} searches")
    print(f"👥 Min group members: {MIN_GROUP_MEMBERS}")
    print(f"🌟 Super group IDs: {SUPER_GROUP_IDS}")
    
    # Start auto backup worker (send immediately and then every 24 hours)
    try:
        auto_backup_thread = threading.Thread(
            target=auto_backup_worker,
            args=(start_time,),
            daemon=True
        )
        auto_backup_thread.start()
        logger.info("Auto backup worker started")
    except Exception as e:
        logger.error(f"Failed to start auto backup worker: {e}")
    
    # Start bot with faster polling and proper error handling
    try:
        bot.infinity_polling(none_stop=True, interval=0.1, timeout=5)
    except KeyboardInterrupt:
        print("Bot stopped by user")
        cleanup()
    except Exception as e:
        logger.error(f"Bot error: {e}")
        cleanup()
        time.sleep(1)
        main()  # Restart on error

if __name__ == "__main__":
    main()
