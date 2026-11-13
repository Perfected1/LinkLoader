import os

from flask import Flask
from flask_cors import CORS

# When a production build exists (LinkLoad/dist), Flask serves it directly so
# the whole app runs on a single origin behind one process manager.
DIST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))),
    "dist",
)


def create_app(test_config=None):
    if os.path.isfile(os.path.join(DIST_DIR, "index.html")):
        app = Flask(__name__, static_folder=DIST_DIR, static_url_path="")
    else:
        app = Flask(__name__)

    if app.static_folder == DIST_DIR:

        @app.route("/")
        def index():
            return app.send_static_file("index.html")
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "development-only-change-me"),
        DEBUG=os.environ.get("FLASK_DEBUG", "false").lower() == "true",
    )
    if test_config:
        app.config.update(test_config)

    from . import main
    app.register_blueprint(main.bp)

    return app
