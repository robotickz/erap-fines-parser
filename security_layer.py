from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic_settings import BaseSettings
from functools import lru_cache
import secrets
import logging

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """
    Environment configuration with validation
    """
    API_TOKEN: str
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": True
    }

@lru_cache()
def get_settings() -> Settings:
    """Cached settings loader - singleton pattern"""
    return Settings()

# Security scheme
security = HTTPBearer()

class TokenValidator:
    """
    Constant-time token validation strategy
    
    Security Considerations:
    - Timing attack prevention via secrets.compare_digest
    - No token logging to prevent exposure
    - Explicit error messages for debugging (dev) vs security (prod)
    """
    
    def __init__(self, settings: Settings):
        self.valid_token = settings.API_TOKEN
        self._validate_token_strength()
    
    def _validate_token_strength(self):
        """Validate token meets security requirements"""
        if len(self.valid_token) < 32:
            logger.warning("API token length < 32 characters - consider using stronger token")
        
        # Check for common weak patterns
        if self.valid_token.lower() in ['test', 'dev', 'admin', 'password']:
            raise ValueError("Insecure API token detected. Please use a cryptographically random token.")
    
    def validate(self, token: str) -> bool:
        """
        Constant-time token comparison
        
        Args:
            token: Bearer token from request
            
        Returns:
            True if valid, False otherwise
            
        Note:
            Uses secrets.compare_digest to prevent timing attacks
        """
        return secrets.compare_digest(token, self.valid_token)

# Global validator instance
_validator = None

def get_validator() -> TokenValidator:
    """Lazy initialization of token validator"""
    global _validator
    if _validator is None:
        _validator = TokenValidator(get_settings())
    return _validator

async def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> str:
    """
    FastAPI dependency for token verification
    
    Architectural Pattern:
    - Dependency injection for authentication
    - Explicit HTTP 401 on failure
    - Token extraction and validation separation
    
    Usage:
        @app.get("/protected", dependencies=[Depends(verify_token)])
        def protected_route():
            ...
    
    Returns:
        token: Valid token string
        
    Raises:
        HTTPException: 401 if token invalid
    """
    token = credentials.credentials
    validator = get_validator()
    
    if not validator.validate(token):
        logger.warning("Invalid authentication attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token

def generate_secure_token(length: int = 32) -> str:
    """
    Generate cryptographically secure random token
    
    Usage:
        # Generate and save to .env file
        token = generate_secure_token()
        print(f"API_TOKEN={token}")
    
    Args:
        length: Token length in bytes (default 32 = 256 bits)
        
    Returns:
        Hex-encoded secure random token
    """
    return secrets.token_hex(length)

# Token generation utility
if __name__ == "__main__":
    print("Generated secure token for .env file:")
    print(f"API_TOKEN={generate_secure_token()}")
