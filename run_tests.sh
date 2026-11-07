#!/bin/bash
# Install testing dependencies
pip install pytest pytest-flask

# Run tests
export FLASK_ENV=testing
export PYTHONPATH=.
pytest tests/ -v
