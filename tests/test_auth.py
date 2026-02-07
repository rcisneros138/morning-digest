import uuid
from unittest.mock import patch

import pytest

from digest.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "mysecretpass"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("wrongpass", hashed) is False


class TestTokenCreation:
    def test_create_and_decode_access_token(self):
        user_id = uuid.uuid4()
        with patch("digest.auth.settings") as mock_settings:
            mock_settings.jwt_secret_key = "test-secret"
            mock_settings.jwt_algorithm = "HS256"
            mock_settings.jwt_access_token_expire_minutes = 30
            token = create_access_token(user_id)
            decoded_id = decode_token(token, expected_type="access")
        assert decoded_id == user_id

    def test_create_and_decode_refresh_token(self):
        user_id = uuid.uuid4()
        with patch("digest.auth.settings") as mock_settings:
            mock_settings.jwt_secret_key = "test-secret"
            mock_settings.jwt_algorithm = "HS256"
            mock_settings.jwt_refresh_token_expire_days = 30
            token, expires = create_refresh_token(user_id)
            decoded_id = decode_token(token, expected_type="refresh")
        assert decoded_id == user_id

    def test_wrong_token_type_raises(self):
        from fastapi import HTTPException

        user_id = uuid.uuid4()
        with patch("digest.auth.settings") as mock_settings:
            mock_settings.jwt_secret_key = "test-secret"
            mock_settings.jwt_algorithm = "HS256"
            mock_settings.jwt_access_token_expire_minutes = 30
            token = create_access_token(user_id)
            with pytest.raises(HTTPException) as exc_info:
                decode_token(token, expected_type="refresh")
            assert exc_info.value.status_code == 401


class TestTokenHashing:
    def test_hash_token_deterministic(self):
        token = "some-jwt-token"
        assert hash_token(token) == hash_token(token)
        assert hash_token(token) != hash_token("different-token")
