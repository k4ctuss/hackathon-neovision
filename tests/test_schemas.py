import pytest
from pydantic import ValidationError

from neorando.schemas import AgentAnswer


def test_AgentAnswer_multiple_fields_error():
    """Si l'agent remplit 2 champs, une ValidationError est levée."""
    with pytest.raises(ValidationError):
        AgentAnswer(answer="test", numeric=42.0)
