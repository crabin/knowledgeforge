import os

from knowledgeforge.api import create_app


app = create_app()


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5001"))
    app.run(host=host, port=port, debug=True)
