import pytest
import os
from app.config import settings

@pytest.fixture(autouse=True)
def setup_test_env():
    """Configures environment for test execution."""
    settings.mock_mode = True
    settings.read_only_mode = True
