"""Start the API server:  python run.py"""
import os

from backend.app import create_app

app = create_app()

if __name__ == "__main__":
    # Debug mode is off unless you explicitly turn it on for development:
    #   FLASK_DEBUG=1 python run.py
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
