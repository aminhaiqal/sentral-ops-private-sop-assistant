"""Authenticated encryption with a private key independent of the database."""

import json
import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.studio.safety import StudioError


class TokenVault:
    def __init__(self, tasks, settings):
        self.tasks, self.settings = tasks, settings

    def cipher(self):
        value = self.settings.google_drive_token_encryption_key
        if value:
            try:
                return Fernet(value.encode())
            except (ValueError, UnicodeError) as exc:
                raise StudioError(
                    "configuration_error",
                    "The Google Drive encryption key is invalid. Ask the administrator to restore it.",
                ) from exc
        path = Path(self.tasks.path).parent / "google-drive.key"
        if not path.exists():
            with self.tasks.connection() as db:
                encrypted = db.execute("SELECT count(*) FROM google_drive_credentials").fetchone()[
                    0
                ]
                pending = db.execute(
                    "SELECT count(*) FROM google_drive_oauth WHERE secrets IS NOT NULL"
                ).fetchone()[0]
            if (encrypted or pending) and not path.exists():
                raise StudioError(
                    "configuration_error",
                    "The Google Drive encryption key is missing. Restore the server key backup before reconnecting.",
                )
            fd, temporary = tempfile.mkstemp(prefix=".drive-key-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(Fernet.generate_key())
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(temporary, path)
                    directory = os.open(path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                except FileExistsError:
                    pass
            finally:
                os.unlink(temporary)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as handle:
                if os.fstat(handle.fileno()).st_mode & 0o077:
                    raise ValueError("Private file permissions required")
                key = handle.read(128)
            return Fernet(key)
        except (OSError, ValueError) as exc:
            raise StudioError(
                "configuration_error",
                "The Google Drive encryption key cannot be used. Ask the administrator to check the private server key file.",
            ) from exc

    def encrypt(self, data, binding):
        payload = json.dumps({"binding": binding, "data": data}, separators=(",", ":")).encode()
        return self.cipher().encrypt(payload).decode()

    def decrypt(self, value, binding):
        try:
            payload = json.loads(self.cipher().decrypt(value.encode()))
            if payload["binding"] != binding:
                raise ValueError("Credential binding mismatch")
            return payload["data"]
        except StudioError:
            raise
        except (InvalidToken, ValueError, KeyError, TypeError) as exc:
            raise StudioError(
                "configuration_error",
                "Google Drive credentials could not be decrypted. Restore the correct server key; credentials were not sent anywhere.",
            ) from exc
