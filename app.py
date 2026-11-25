import os
import re
import time
import threading
from functools import wraps
from urllib.parse import quote
import requests
from flask import Flask, jsonify, make_response, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-in-production")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

SERVER_ID = os.environ.get("SERVER_ID", "Local-Dev")
API_BASE_URL = os.environ.get("COUNTRIES_API_URL", "https://api.restcountries.com/countries/v5")
COUNTRIES_API_KEY = os.environ.get("COUNTRIES_API_KEY", "").strip()
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))

DEMO_USERS = {
    "analyst": {
        "password": os.environ.get("DEMO_USER_PASSWORD", "Explore2026!"),
        "role": "Analyst",
    }
}

_CACHE_LOCK = threading.Lock()
_CACHE_STORE = {"data": None, "expires_at": 0.0}
_USER_PREFS = {
    "analyst": {"favorites": ["Rwanda", "Kenya", "Japan"], "sort_by": "name"}
}

def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login_page"))
        return view_func(*args, **kwargs)
    return wrapped_view


def sanitize_text(value, max_len=80):
    if not isinstance(value, str):
        return ""
    cleaned = "".join(ch for ch in value.strip() if ch.isprintable())
    return cleaned[:max_len]


def fetch_countries_cached():
    now = time.time()
    with _CACHE_LOCK:
        if _CACHE_STORE["data"] is not None and now < _CACHE_STORE["expires_at"]:
            return _CACHE_STORE["data"], True, None
        
    api_key = os.environ.get("COUNTRIES_API_KEY", "").strip() or COUNTRIES_API_KEY
    if not api_key:
        return [], False, "Unable to retrieve country data right now: Missing COUNTRIES_API_KEY environment variable."

    url = API_BASE_URL.rstrip("/")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        raw_items = []
        offset = 0
        page_size = 100

        while True:
            resp = requests.get(
                url,
                headers=headers,
                params={"limit": page_size, "offset": offset},
                timeout=8
            )
            resp.raise_for_status()
            payload = resp.json()

            if isinstance(payload, list):
                page_items = payload
                has_more = len(page_items) == page_size
            elif isinstance(payload, dict):
                data_obj = payload.get("data")
                if isinstance(data_obj, dict) and isinstance(data_obj.get("objects"), list):
                    page_items = data_obj["objects"]
                    pag = data_obj.get("pagination") or payload.get("pagination") or {}
                    if isinstance(pag, dict) and "has_more" in pag:
                        has_more = bool(pag["has_more"])
                    elif isinstance(pag, dict) and "next_offset" in pag and pag["next_offset"] is not None:
                        has_more = True
                    else:
                        has_more = len(page_items) == page_size
                elif isinstance(data_obj, list):
                    page_items = data_obj
                    has_more = len(page_items) == page_size
                else:
                    detail = f": {payload.get('message')}" if payload.get("message") else ""
                    raise ValueError(f"Unexpected API response format ({type(payload).__name__}){detail}")
            else:
                raise ValueError(f"Unexpected API response format ({type(payload).__name__})")

            raw_items.extend([x for x in page_items if isinstance(x, dict)])

            if not has_more or not page_items or offset >= 1000:
                break
            offset += len(page_items)

        normalized = []
        for item in raw_items:
            name_obj = item.get("name") or item.get("names") or {}
            if isinstance(name_obj, dict):
                common_name = sanitize_text(
                    name_obj.get("common") or name_obj.get("official") or "Unknown", 100
                )
            else:
                common_name = sanitize_text(str(name_obj or "Unknown"), 100)

            codes_obj = item.get("codes") if isinstance(item.get("codes"), dict) else {}
            raw_code = (
                item.get("cca2")
                or codes_obj.get("alpha_2")
                or codes_obj.get("alpha_3")
                or ""
            )

            capitals = item.get("capital") or item.get("capitals") or []
            if isinstance(capitals, list) and capitals:
                first_cap = capitals[0]
                cap_raw = first_cap.get("name", "") if isinstance(first_cap, dict) else str(first_cap)
                capital_str = sanitize_text(cap_raw, 80) or "N/A"
            elif isinstance(capitals, str) and capitals.strip():
                capital_str = sanitize_text(capitals, 80)
            else:
                capital_str = "N/A"

            flag_obj = item.get("flag") if isinstance(item.get("flag"), dict) else {}
            flags_obj = item.get("flags") if isinstance(item.get("flags"), dict) else {}
            if flag_obj or flags_obj:
                flag_val = (
                    flag_obj.get("url_png")
                    or flag_obj.get("png")
                    or flags_obj.get("png")
                    or flag_obj.get("url_svg")
                    or flags_obj.get("svg")
                    or flag_obj.get("emoji")
                    or flags_obj.get("emoji")
                    or ""
                )
            else:
                raw_flag = item.get("flag") or item.get("flags") or ""
                flag_val = str(raw_flag) if not isinstance(raw_flag, (dict, list)) else ""

            pop_raw = item.get("population")
            if isinstance(pop_raw, dict):
                pop_val = pop_raw.get("total") or 0
            else:
                pop_val = pop_raw or 0

            area_raw = item.get("area")
            if isinstance(area_raw, dict):
                area_val = (
                    area_raw.get("kilometers")
                    or area_raw.get("kilometres")
                    or area_raw.get("km2")
                    or 0.0
                )
            else:
                area_val = area_raw or 0.0

            normalized.append({
                "code": sanitize_text(str(raw_code), 4),
                "name": common_name,
                "region": sanitize_text(str(item.get("region") or "Other"), 40) or "Other",
                "subregion": sanitize_text(str(item.get("subregion") or ""), 60),
                "population": int(pop_val),
                "area": float(area_val),
                "capital": capital_str,
                "flag": sanitize_text(flag_val, 250),
            })

        with _CACHE_LOCK:
            _CACHE_STORE["data"] = normalized
            _CACHE_STORE["expires_at"] = time.time() + CACHE_TTL_SECONDS

        return normalized, False, None

    except (requests.RequestException, ValueError, KeyError) as exc:
        with _CACHE_LOCK:
            if _CACHE_STORE["data"] is not None:
                return _CACHE_STORE["data"], True, f"Live API issue ({exc}); serving cached data."
        return [], False, f"Unable to retrieve country data right now: {exc}"

def filter_and_sort_countries(countries, query="", region="All", sort_by="name", order="asc"):
    q_lower = query.lower()
    filtered = []
    for c in countries:
        matches_query = (
            not q_lower
            or q_lower in c["name"].lower()
            or q_lower in c["capital"].lower()
            or q_lower in c["code"].lower()
        )
        matches_region = (region == "All") or (c["region"].lower() == region.lower())
        if matches_query and matches_region:
            filtered.append(c)

    valid_sorts = {"name", "population", "area"}
    sort_key = sort_by if sort_by in valid_sorts else "name"
    reverse = (order == "desc")

    if sort_key == "name":
        filtered.sort(key=lambda x: x["name"].lower(), reverse=reverse)
    else:
        filtered.sort(key=lambda x: x[sort_key], reverse=reverse)

    return filtered

@app.route("/health")
def health_check():
    resp = make_response(jsonify({"status": "ok", "server": SERVER_ID}), 200)
    resp.headers["X-Served-By"] = SERVER_ID
    return resp

@app.route("/login", methods=["GET", "POST"])
def login_page():
    error = None
    if request.method == "POST":
        username = sanitize_text(request.form.get("username", ""), 40)
        password = request.form.get("password", "")
        user_record = DEMO_USERS.get(username)
        if user_record and user_record["password"] == password:
            session["user"] = username
            _USER_PREFS.setdefault(username, {"favorites": [], "sort_by": "name"})
            return redirect(url_for("dashboard"))
        error = "Invalid username or password."
    return render_template("index.html", mode="login", error=error, server_id=SERVER_ID)

@app.route("/logout", methods=["POST"])
def logout_user():
    session.pop("user", None)
    return redirect(url_for("login_page"))

@app.route("/")
@login_required
def dashboard():
    username = session["user"]
    prefs = _USER_PREFS.setdefault(username, {"favorites": [], "sort_by": "name"})

    query = sanitize_text(request.args.get("q", ""), 80)
    region = sanitize_text(request.args.get("region", "All"), 40) or "All"
    sort_by = sanitize_text(request.args.get("sort", prefs.get("sort_by", "name")), 20)
    order = sanitize_text(request.args.get("order", "asc"), 10)
    if order not in ("asc", "desc"):
        order = "asc"

    prefs["sort_by"] = sort_by if sort_by in {"name", "population", "area"} else "name"

    countries, cache_hit, warning_msg = fetch_countries_cached()
    regions = sorted({c["region"] for c in countries if c.get("region")})
    if "All" not in regions:
        regions.insert(0, "All")

    results = filter_and_sort_countries(countries, query=query, region=region, sort_by=sort_by, order=order)

    resp = make_response(render_template(
        "index.html",
        mode="dashboard",
        user=username,
        role=DEMO_USERS.get(username, {}).get("role", "User"),
        countries=results,
        total_count=len(countries),
        shown_count=len(results),
        regions=regions,
        query=query,
        selected_region=region,
        sort_by=sort_by,
        order=order,
        favorites=set(prefs.get("favorites", [])),
        cache_hit=cache_hit,
        warning_msg=warning_msg,
        server_id=SERVER_ID,
    ))
    resp.headers["X-Served-By"] = SERVER_ID
    return resp


@app.route("/api/favorites/toggle", methods=["POST"])
@login_required
def toggle_favorite():
    username = session["user"]
    payload = request.get_json(silent=True) or {}
    country_name = sanitize_text(payload.get("country", ""), 100)
    if not country_name:
        return jsonify({"error": "Country name is required."}), 400

    prefs = _USER_PREFS.setdefault(username, {"favorites": [], "sort_by": "name"})
    favs = prefs["favorites"]
    if country_name in favs:
        favs.remove(country_name)
        saved = False
    else:
        favs.append(country_name)
        saved = True

    return jsonify({"country": country_name, "saved": saved, "favorites": favs})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
