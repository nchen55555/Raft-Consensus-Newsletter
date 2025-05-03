import threading
import os
import logging
import smtplib
import json
import time
import uuid
import redis
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

class EmailWorker:
    """
    Distributed email worker that uses Redis as a backend queue.
    This is a drop-in replacement for the original EmailWorker.
    """
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.username = os.getenv("SMTP_USERNAME")
        self.password = os.getenv("SMTP_PASSWORD")

        if not (self.username and self.password):
            raise RuntimeError("SMTP_USERNAME and SMTP_PASSWORD must be set as environment variables")

        # Redis connection for the distributed queue
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_password = os.getenv("REDIS_PASSWORD", "")  # Empty string means no password
        self.redis_db = int(os.getenv("REDIS_DB", "0"))
        self.logger = logging.getLogger("EmailWorker")
        
        # Connect to Redis
        self._connect_to_redis()
        
        # Generate a unique worker ID
        self.worker_id = f"worker-{os.getpid()}-{str(uuid.uuid4())[:8]}"
        
        # Queue configuration
        self.email_queue_key = "email_queue"
        self.processing_queue_key = f"email_processing:{self.worker_id}"
        self.dead_letter_queue_key = "email_dead_letter"
        
        # Worker state
        self.running = False
        self.thread = None
        self.health_check_thread = None
        
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _connect_to_redis(self):
        """Connect to Redis with appropriate error handling."""
        try:
            # Only use password if it's actually set
            if self.redis_password:
                self.redis = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    password=self.redis_password,
                    db=self.redis_db,
                    decode_responses=True,
                    socket_timeout=5.0,
                    socket_connect_timeout=5.0
                )
            else:
                self.redis = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    db=self.redis_db,
                    decode_responses=True,
                    socket_timeout=5.0,
                    socket_connect_timeout=5.0
                )
            
            # Test connection
            self.redis.ping()
            self.logger.info("Successfully connected to Redis")
        except redis.RedisError as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            # Initialize a dummy Redis client that will be retried later
            self.redis = None

    def start(self):
        """Start the email worker threads (compatible with original interface)."""
        self.running = True
        
        # Start the main processing thread
        self.thread = threading.Thread(target=self._process_queue, daemon=True)
        self.thread.start()
        
        # Start the health check thread
        self.health_check_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self.health_check_thread.start()
        
        self.logger.info(f"Email worker {self.worker_id} started")

    def stop(self):
        """Stop the email worker threads (compatible with original interface)."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
        if self.health_check_thread:
            self.health_check_thread.join(timeout=2.0)
        self.logger.info(f"Email worker {self.worker_id} stopped")

    def _health_check_loop(self):
        """Periodically run health checks on the queue."""
        while self.running:
            try:
                # Wait for 5 minutes between checks
                for _ in range(300):
                    if not self.running:
                        return
                    time.sleep(1)
                
                self._check_queue_health()
            except Exception as e:
                self.logger.error(f"Error in health check: {e}")
                time.sleep(60)  # Back off on errors

    def _process_queue(self):
        """Process emails from the distributed queue."""
        reconnect_delay = 1.0  # Start with 1 second delay
        max_reconnect_delay = 60.0  # Maximum delay is 1 minute
        
        while self.running:
            try:
                # Make sure we have a Redis connection
                if self.redis is None:
                    self.logger.info(f"Attempting to reconnect to Redis in {reconnect_delay} seconds...")
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                    self._connect_to_redis()
                    continue
                
                # reset reconnect delay on successful operations
                reconnect_delay = 1.0

                # use BRPOPLPUSH to atomically move an item from the queue to processing list
                # this ensures that if a worker crashes, the item isn't lost
                raw_task = self.redis.brpoplpush(
                    self.email_queue_key,
                    self.processing_queue_key,
                    timeout=1
                )
                
                if not raw_task:
                    continue
                    
                # Process the email
                task = json.loads(raw_task)
                sender = task.get('sender')
                recipient = task.get('recipient')
                subject = task.get('subject')
                content = task.get('content')
                
                self.logger.info(f"Processing email to {recipient}")
                success = self._send_email(sender, recipient, subject, content)
                
                # Remove from processing queue once completed
                if success:
                    self.redis.lrem(self.processing_queue_key, 1, raw_task)
                else:
                    # If failed, put back in queue with retry count or move to dead letter queue
                    task['retries'] = task.get('retries', 0) + 1
                    if task['retries'] < 3:  # Max retries
                        self.logger.info(f"Requeuing email to {recipient} (attempt {task['retries']})")
                        self.queue_email(sender, recipient, subject, content, retries=task['retries'])
                    else:
                        # Move to dead letter queue for later inspection
                        self.redis.lpush(self.dead_letter_queue_key, raw_task)
                        self.logger.warning(f"Email to {recipient} failed after {task['retries']} retries, moved to dead letter queue")
                    
                    self.redis.lrem(self.processing_queue_key, 1, raw_task)
                    
            except redis.RedisError as e:
                self.logger.error(f"Redis error in email queue: {e}")
                self.redis = None  # Force reconnection
                time.sleep(5)  # Back off on Redis errors
            except Exception as e:
                self.logger.error(f"Error processing email queue: {e}")
                time.sleep(1)  # Avoid spinning in case of persistent errors

    def _send_email(self, sender, recipient, subject, content):
        """Send an email using the configured SMTP server."""
        # Construct the email
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(content, "plain"))
        try:
            with smtplib.SMTP(self.smtp_server, self.port, timeout=10) as server:
                server.ehlo()
                # Use STARTTLS if available
                if server.has_extn('starttls'):
                    server.starttls()
                    server.ehlo()
                # Perform login only if server supports AUTH
                if self.username and self.password and server.has_extn('auth'):
                    server.login(self.username, self.password)
                
                server.send_message(msg)
                self.logger.info(f"Email sent to {recipient}")
                return True
        except Exception as e:
            self.logger.error(f"Failed to send email to {recipient}: {e}")
            return False

    def queue_email(self, sender, recipient, subject, content, retries=0):
        """
        Queue an email for delivery. `sender` is the "From:" header, `recipient` is the destination.
        This matches the original interface.
        """
        # make sure we have a Redis connection
        if self.redis is None:
            try:
                self._connect_to_redis()
            except Exception as e:
                self.logger.error(f"Failed to reconnect to Redis while queuing email: {e}")
                return False
                
        task = {
            'sender': sender,
            'recipient': recipient,
            'subject': subject,
            'content': content,
            'retries': retries,
            'timestamp': time.time(),
            'id': str(uuid.uuid4())
        }
        try:
            self.redis.lpush(self.email_queue_key, json.dumps(task))
            self.logger.info(f"Email to {recipient} queued successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to queue email: {e}")
            return False

    def _check_queue_health(self):
        """Check for stuck emails and requeue them."""
        if self.redis is None:
            self.logger.warning("Cannot check queue health - Redis connection not available")
            return False
            
        try:
            # Get all processing queue keys
            processing_keys = self.redis.keys("email_processing:*")
            for key in processing_keys:
                processing = self.redis.lrange(key, 0, -1)
                for raw_task in processing:
                    try:
                        task = json.loads(raw_task)
                        timestamp = task.get('timestamp', 0)
                        # If task has been processing for more than 10 minutes, requeue it
                        if time.time() - timestamp > 600:
                            worker_id = key.split(":")[-1]
                            self.logger.warning(f"Found stuck email to {task.get('recipient')} in worker {worker_id}, requeuing")
                            self.redis.lrem(key, 1, raw_task)
                            task['retries'] = task.get('retries', 0) + 1
                            if task['retries'] < 3:
                                self.queue_email(
                                    task.get('sender', ''),
                                    task.get('recipient', ''),
                                    task.get('subject', ''),
                                    task.get('content', ''),
                                    retries=task['retries']
                                )
                            else:
                                # Move to dead letter queue
                                self.redis.lpush(self.dead_letter_queue_key, raw_task)
                    except json.JSONDecodeError:
                        self.logger.error(f"Invalid JSON in processing queue: {raw_task}")
                        # Remove the invalid entry
                        self.redis.lrem(key, 1, raw_task)
            return True
        except Exception as e:
            self.logger.error(f"Failed to check queue health: {e}")
            return False

    def get_queue_stats(self):
        """Get statistics about the email queues."""
        if self.redis is None:
            return {'status': 'disconnected'}
            
        try:
            stats = {
                'status': 'connected',
                'pending': self.redis.llen(self.email_queue_key),
                'dead_letter': self.redis.llen(self.dead_letter_queue_key),
                'processing': {}
            }
            
            # Get processing counts for all workers
            processing_keys = self.redis.keys("email_processing:*")
            for key in processing_keys:
                worker_id = key.split(":")[-1]
                stats['processing'][worker_id] = self.redis.llen(key)
                
            return stats
        except Exception as e:
            self.logger.error(f"Failed to get queue stats: {e}")
            return {'status': 'error', 'message': str(e)}

email_worker = EmailWorker()