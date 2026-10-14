"""
Security utilities — encryption for secrets stored in the database.

When a business connects their Amazon Seller Central account, we receive
an OAuth refresh token. That token grants access to their Amazon data.
If our database is ever breached, we don't want attackers to get working
Amazon tokens.

Solution: encrypt tokens before storing them, decrypt when needed.

Fernet encryption (symmetric, from the cryptography library):
- Same key encrypts and decrypts
- Includes a timestamp — you can check when a value was encrypted
- Tamper-proof — any modification to the ciphertext is detected
- The key is loaded from ENCRYPTION_KEY in your .env file

Generate a key once:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Store it in .env and NEVER commit it to git.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

# Initialize the cipher once at startup.
# settings.encryption_key is a base64-encoded 32-byte key.
_fernet = Fernet(settings.encryption_key.encode())


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a string (like an OAuth refresh token) for database storage.

    Returns a base64-encoded string that can go in a TEXT column.
    The same plaintext encrypted twice produces different ciphertexts
    (Fernet includes a random IV), so you can't compare encrypted
    values directly — which is a security feature, not a bug.
    """
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypt a value retrieved from the database.

    Raises InvalidToken if:
    - The ciphertext was tampered with
    - The wrong encryption key is being used
    - The data is corrupted

    In production, catch InvalidToken and treat it as "credential
    needs to be re-authorized" rather than crashing.
    """
    return _fernet.decrypt(ciphertext.encode()).decode()
