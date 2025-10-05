import os
import time
import threading
import requests
from datetime import timedelta
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, jsonify, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")
os.makedirs(DB_DIR, exist_ok=True)
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(DB_DIR, 'movies.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.permanent_session_lifetime = timedelta(days=7)

db = SQLAlchemy(app)

TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
TMDB_IMG_BASE_W500 = "https://image.tmdb.org/t/p/w500"
TMDB_IMG_BASE_W780 = "https://image.tmdb.org/t/p/w780"

# ---------------- Models ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="user")  # 'admin' or 'user'

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    year = db.Column(db.String(10), nullable=True)
    box_office = db.Column(db.String(50), nullable=True)
    director = db.Column(db.String(200), nullable=True)
    producer = db.Column(db.String(200), nullable=True)
    cast = db.Column(db.Text, nullable=True)
    poster_url = db.Column(db.String(500), nullable=True)
    tmdb_id = db.Column(db.String(50), nullable=True)

# ---------------- Helpers ----------------
def is_admin():
    return session.get("role") == "admin"

def poster_from_tmdb_path(path):
    if not path:
        return "/static/images/default_poster.png"
    return TMDB_IMG_BASE_W500 + path

# ---------------- DB & default admin ----------------
def create_default_admin():
    db.create_all()
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin = User(username="admin", email="admin@example.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)
    # ensure at least one sample movie exists with valid poster
    if Movie.query.count() == 0:
        sample = Movie(
            title="Inception",
            year="2010",
            box_office="$829,895,144",
            director="Christopher Nolan",
            producer="Emma Thomas",
            cast="Leonardo DiCaprio, Joseph Gordon-Levitt, Elliot Page",
            poster_url="/static/images/default_poster.png",
            tmdb_id=None
        )
        db.session.add(sample)
    db.session.commit()

# ---------------- TMDB import (safe, background) ----------------
_import_thread = None
_import_status = {"running": False, "inserted": 0, "last_error": None}

def fetch_and_insert_tmdb_top(limit=1000, delay=0.25, start_page=1):
    """
    Fetch 'discover' sorted by revenue.desc pages until we reach 'limit'.
    This function may take minutes — run in background thread.
    """
    try:
        if not TMDB_API_KEY:
            raise RuntimeError("TMDB_API_KEY not set in environment")

        inserted = 0
        page = start_page
        per_page = 20
        with app.app_context():
            while inserted < limit:
                params = {"api_key": TMDB_API_KEY, "sort_by": "revenue.desc", "page": page, "language": "en-US"}
                r = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=20)
                if not r.ok:
                    _import_status["last_error"] = f"TMDB error page {page}: {r.status_code}"
                    break
                data = r.json()
                results = data.get("results", [])
                if not results:
                    break
                for item in results:
                    tmdb_id = str(item.get("id"))
                    if Movie.query.filter_by(tmdb_id=tmdb_id).first():
                        continue
                    poster = poster_from_tmdb_path(item.get("poster_path"))
                    # try to get credits (best-effort)
                    director = producer = ""
                    cast_str = ""
                    try:
                        cr = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}/credits", params={"api_key": TMDB_API_KEY}, timeout=15)
                        if cr.ok:
                            creds = cr.json()
                            for crew in creds.get("crew", []):
                                if crew.get("job") == "Director":
                                    director = crew.get("name")
                                if crew.get("job") == "Producer" and not producer:
                                    producer = crew.get("name")
                            cast_list = [c.get("name") for c in creds.get("cast", [])[:6]]
                            cast_str = ", ".join(cast_list)
                    except Exception:
                        pass

                    movie = Movie(
                        title=item.get("title") or item.get("original_title"),
                        year=(item.get("release_date") or "")[:4],
                        box_office="",
                        director=director,
                        producer=producer,
                        cast=cast_str,
                        poster_url=poster,
                        tmdb_id=tmdb_id
                    )
                    db.session.add(movie)
                    inserted += 1
                    _import_status["inserted"] = inserted
                    if inserted % 20 == 0:
                        db.session.commit()
                    if inserted >= limit:
                        break
                    time.sleep(delay)
                page += 1
            db.session.commit()
        _import_status["running"] = False
        return inserted
    except Exception as e:
        _import_status["last_error"] = str(e)
        _import_status["running"] = False
        return 0

def start_import_background(limit=1000):
    global _import_thread
    if _import_thread and _import_thread.is_alive():
        return False
    _import_status.update({"running": True, "inserted": 0, "last_error": None})
    _import_thread = threading.Thread(target=fetch_and_insert_tmdb_top, kwargs={"limit": limit})
    _import_thread.start()
    return True

# ---------------- Routes ----------------
@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    page = max(int(request.args.get("page", 1)), 1)
    per_page = 24

    query = Movie.query
    if q:
        like = f"%{q}%"
        query = query.filter((Movie.title.ilike(like)) | (Movie.director.ilike(like)) | (Movie.cast.ilike(like)))

    movies = query.order_by(Movie.id.asc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template("index.html", movies=movies, q=q)

@app.route("/movie/<int:movie_id>")
def movie_detail(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    return render_template("movie_detail.html", movie=movie)

@app.route("/api/movie/<int:movie_id>")
def api_movie(movie_id):
    m = Movie.query.get_or_404(movie_id)
    return jsonify({
        "id": m.id,
        "title": m.title,
        "year": m.year,
        "box_office": m.box_office,
        "director": m.director,
        "producer": m.producer,
        "cast": m.cast,
        "poster_url": m.poster_url
    })

# Import status endpoint
@app.route("/admin/import_status")
def import_status():
    return jsonify(_import_status)

# Authentication routes
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        if User.query.filter((User.username==username)|(User.email==email)).first():
            flash("Username or email already exists", "danger")
            return redirect(url_for("signup"))
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Account created. Please login.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        identifier = request.form["identifier"].strip()
        password = request.form["password"]
        user = User.query.filter((User.username==identifier)|(User.email==identifier)).first()
        if user and user.check_password(password):
            session.permanent = True
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            flash("Logged in successfully", "success")
            return redirect(url_for("index"))
        flash("Invalid credentials", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("index"))

# Admin CRUD
@app.route("/admin")
def admin_dashboard():
    if not is_admin():
        flash("Admin access required", "danger")
        return redirect(url_for("login"))
    movies = Movie.query.order_by(Movie.id.desc()).all()
    return render_template("admin_dashboard.html", movies=movies)

@app.route("/admin/add", methods=["GET","POST"])
def add_movie():
    if not is_admin():
        flash("Admin access required", "danger")
        return redirect(url_for("login"))
    if request.method == "POST":
        title = request.form.get("title","").strip()
        year = request.form.get("year","").strip()
        box = request.form.get("box_office","").strip()
        director = request.form.get("director","").strip()
        producer = request.form.get("producer","").strip()
        cast = request.form.get("cast","").strip()
        tmdb_id = request.form.get("tmdb_id","").strip() or None

        poster_url = None
        file = request.files.get("poster_file")
        if file and file.filename:
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(save_path)
            poster_url = url_for("static", filename=f"uploads/{filename}")

        # if tmdb_id provided and no file, fetch from TMDB
        if not poster_url and tmdb_id and TMDB_API_KEY:
            try:
                r = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}", params={"api_key": TMDB_API_KEY}, timeout=15)
                if r.ok:
                    data = r.json()
                    if data.get("poster_path"):
                        poster_url = TMDB_IMG_BASE_W500 + data["poster_path"]
            except Exception as e:
                print("TMDB fetch error:", e)

        if not poster_url:
            poster_url = "/static/images/default_poster.png"

        movie = Movie(
            title=title, year=year, box_office=box, director=director,
            producer=producer, cast=cast, poster_url=poster_url, tmdb_id=tmdb_id
        )
        db.session.add(movie)
        db.session.commit()
        flash("Movie added", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("add_movie.html")

@app.route("/admin/edit/<int:id>", methods=["GET","POST"])
def edit_movie(id):
    if not is_admin():
        flash("Admin access required", "danger")
        return redirect(url_for("login"))
    movie = Movie.query.get_or_404(id)
    if request.method == "POST":
        movie.title = request.form.get("title","").strip()
        movie.year = request.form.get("year","").strip()
        movie.box_office = request.form.get("box_office","").strip()
        movie.director = request.form.get("director","").strip()
        movie.producer = request.form.get("producer","").strip()
        movie.cast = request.form.get("cast","").strip()
        file = request.files.get("poster_file")
        if file and file.filename:
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(save_path)
            movie.poster_url = url_for("static", filename=f"uploads/{filename}")
        db.session.commit()
        flash("Movie updated", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("add_movie.html", movie=movie)

@app.route("/admin/delete/<int:id>", methods=["POST"])
def delete_movie(id):
    if not is_admin():
        return "forbidden", 403
    movie = Movie.query.get_or_404(id)
    db.session.delete(movie)
    db.session.commit()
    flash("Movie deleted", "info")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/import_tmdb", methods=["POST"])
def admin_import_tmdb():
    if not is_admin():
        return "forbidden", 403
    try:
        limit = int(request.form.get("limit", 1000))
    except:
        limit = 1000
    started = start_import_background(limit=limit)
    if started:
        flash("TMDB import started in background. Check Admin Dashboard later for results.", "info")
    else:
        flash("Import already running.", "warning")
    return redirect(url_for("admin_dashboard"))

# Serve uploads
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ---------------- Run ----------------
if __name__ == "__main__":
    with app.app_context():
        create_default_admin()
    app.run(debug=True)
