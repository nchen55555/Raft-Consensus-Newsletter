import bcrypt

class Writer:
    def __init__(self, email, name, password=None, hashed_password=None):
        self.email = email
        self.name = name
        if password:
            # Hash the password if a plain text password is provided
            salt = bcrypt.gensalt()
            self.password = bcrypt.hashpw(password.encode('utf-8'), salt)
        elif hashed_password:
            # Use the provided hash directly if loading from storage
            self.password = hashed_password.encode('utf-8') if isinstance(hashed_password, str) else hashed_password
        else:
            raise ValueError("Either password or hashed_password must be provided")

    def verify_password(self, password):
        """Verify a password against the stored hash"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), self.password)
        except Exception:
            return False

    def to_dict(self):
        """Convert writer to dictionary for storage"""
        return {
            'email': self.email,
            'name': self.name,
            'password': self.password.decode('utf-8')  # Store hash as string
        }