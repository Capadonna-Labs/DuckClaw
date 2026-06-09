"""Uvicorn entry: duckclaw_sensory_node.main:app"""

from duckclaw_sensory_node.app import create_app

app = create_app()
