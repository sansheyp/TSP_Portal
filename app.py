from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
import os
import configparser
from functools import wraps
from datetime import datetime

# Auto-load from config.ini
_cfg = configparser.ConfigParser()
_cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "snipeit_tool", "config.ini")
_cfg.read(_cfg_path)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tsp-portal-secret-2024")

SNIPEIT_URL = os.environ.get("SNIPEIT_URL") or _cfg.get("snipeit", "url", fallback="https://assets.theschoolphotographer.com.au")
SNIPEIT_TOKEN = os.environ.get("SNIPEIT_TOKEN") or _cfg.get("snipeit", "token", fallback="")

def snipe_headers():
    return {"Authorization": f"Bearer {SNIPEIT_TOKEN}", "Content-Type": "application/json", "Accept": "application/json"}

def snipe_get(endpoint, params=None):
    r = requests.get(f"{SNIPEIT_URL}/api/v1{endpoint}", headers=snipe_headers(), params=params, timeout=15)
    r.raise_for_status(); return r.json()

def snipe_post(endpoint, data):
    r = requests.post(f"{SNIPEIT_URL}/api/v1{endpoint}", headers=snipe_headers(), json=data, timeout=15)
    r.raise_for_status(); return r.json()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def get_user_by_credentials(username, password):
    try:
        data = snipe_get("/users", {"search": username, "limit": 10})
        for u in data.get("rows", []):
            if u.get("username", "").lower() == username.lower():
                return u
    except Exception as e:
        print(f"Login error: {e}")
    return None

def get_assets_for_user(user_id):
    try:
        data = snipe_get("/hardware", {"limit": 500})
        return [a for a in data.get("rows", [])
                if isinstance(a.get("assigned_to"), dict) and a["assigned_to"].get("id") == user_id]
    except Exception as e:
        print(f"get_assets_for_user error: {e}")
        return []

def get_available_kits():
    try:
        data = snipe_get("/hardware", {"limit": 500})
        kits = []
        for a in data.get("rows", []):
            tag = a.get("asset_tag", "")
            if tag.startswith("KIT-"):
                assigned = a.get("assigned_to")
                if not assigned or not isinstance(assigned, dict) or not assigned.get("id"):
                    kits.append(a)
        return sorted(kits, key=lambda x: x.get("asset_tag", ""))
    except: return []

def get_kit_structure(kit_tag):
    """Get full kit structure — bags and their contents"""
    kit_prefix = kit_tag.replace("KIT-", "")
    try:
        all_assets = snipe_get("/hardware", {"limit": 500}).get("rows", [])
        l2_bags = sorted(
            [a for a in all_assets if a.get("asset_tag", "").startswith(f"BAG-{kit_prefix}-")],
            key=lambda x: x.get("asset_tag", "")
        )
        l3_all = [a for a in all_assets if (
            kit_prefix in a.get("asset_tag", "") and
            not a.get("asset_tag", "").startswith("BAG-") and
            a.get("asset_tag", "") != kit_tag
        )]

        bags = []
        for l2 in l2_bags:
            l2_tag = l2.get("asset_tag", "")
            bag_suffix = l2_tag.replace(f"BAG-{kit_prefix}-", "")
            bag_assets = []
            remaining = []
            for asset in l3_all:
                tag = asset.get("asset_tag", "")
                matched = False
                if bag_suffix == "CAM" and any(x in tag for x in ["CAM-", "LENS-", "LAP-", "SCNR-", "TIMESTN-", "BAT-"]):
                    matched = True
                elif bag_suffix == "LGT1" and any(x in tag for x in ["LIGHT-", "LPC-", "EXT-", "PWR-"]) and ("-1" in tag.split("-")[-1] or tag.endswith("-1")):
                    matched = True
                elif bag_suffix == "LGT2" and any(x in tag for x in ["LIGHT-", "LPC-", "EXT-", "PWR-"]) and ("-2" in tag.split("-")[-1] or tag.endswith("-2")):
                    matched = True
                elif bag_suffix not in ["CAM", "LGT1", "LGT2"] and bag_suffix.lower() in tag.lower():
                    matched = True
                if matched:
                    bag_assets.append(asset)
                else:
                    remaining.append(asset)

            bags.append({
                "id":    l2["id"],
                "name":  l2.get("name") or l2_tag,
                "tag":   l2_tag,
                "assets": bag_assets,
            })

        # Any unplaced L3 assets go into first bag
        placed_tags = {a.get("asset_tag") for bag in bags for a in bag["assets"]}
        unplaced = [a for a in l3_all if a.get("asset_tag") not in placed_tags]
        if unplaced and bags:
            bags[0]["assets"].extend(unplaced)

        return bags
    except Exception as e:
        print(f"get_kit_structure error: {e}")
        return []

def checkout_to_user(asset_id, user_id, note=""):
    try:
        res = snipe_post(f"/hardware/{asset_id}/checkout", {
            "checkout_to_type": "user",
            "assigned_user": user_id,
            "note": note
        })
        return res.get("status") == "success"
    except: return False

def checkin_asset(asset_id, note=""):
    try:
        res = snipe_post(f"/hardware/{asset_id}/checkin", {"note": note})
        return res.get("status") == "success"
    except: return False


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if not username or not password:
            error = "Please enter your username and password"
        else:
            user = get_user_by_credentials(username, password)
            if user:
                session["user_id"]   = user["id"]
                session["username"]  = user.get("username")
                session["user_name"] = user.get("name")
                return redirect(url_for("dashboard"))
            else:
                error = "Username not found — contact your admin"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    assets  = get_assets_for_user(user_id)
    my_kits_raw = sorted([a for a in assets if a.get("asset_tag", "").startswith("KIT-")],
                     key=lambda x: x.get("asset_tag", ""))

    # For each kit, find which bags are assigned to this user
    my_bags = [a for a in assets if a.get("asset_tag", "").startswith("BAG-")]

    my_kits = []
    for kit in my_kits_raw:
        kit_prefix = kit.get("asset_tag", "").replace("KIT-", "")
        # Find bags from this kit assigned to user
        kit_bags = [b for b in my_bags if kit_prefix in b.get("asset_tag", "")]
        bag_names = []
        for bag in sorted(kit_bags, key=lambda x: x.get("asset_tag", "")):
            name = bag.get("name") or bag.get("asset_tag", "")
            # Clean up name — remove tag prefix for readability
            if not name or name == bag.get("asset_tag"):
                tag = bag.get("asset_tag", "")
                suffix = tag.split("-")[-1]
                name_map = {
                    "CAM": "Camera Bag", "LGT1": "Light Bag 1", "LGT2": "Light Bag 2",
                    "STD": "Stand Bag", "TOTE": "Tote Bag", "TBL": "Table",
                    "BDT": "Backdrop Tube", "WBD": "White Backdrop Bag",
                    "CAR": "Loose in Car"
                }
                name = name_map.get(suffix, suffix)
            bag_names.append(name)

        kit["checked_out_bags"] = bag_names
        kit["full_kit"] = len(kit_bags) >= 9  # 9 bags = full portrait kit
        my_kits.append(kit)

    available_kits = get_available_kits()
    return render_template("dashboard.html",
        user_name=session["user_name"],
        my_kits=my_kits,
        available_kits=available_kits
    )

@app.route("/kit/<kit_tag>")
@login_required
def kit_detail(kit_tag):
    try:
        kit  = snipe_get(f"/hardware/bytag/{kit_tag}")
        if kit.get("status") == "error":
            return redirect(url_for("dashboard"))
        bags = get_kit_structure(kit_tag)
        # Check if this kit is assigned to current user
        assigned = kit.get("assigned_to", {})
        is_mine  = isinstance(assigned, dict) and assigned.get("id") == session["user_id"]
        return render_template("kit_detail.html",
            kit=kit, kit_tag=kit_tag, bags=bags, is_mine=is_mine)
    except Exception as e:
        print(f"kit_detail error: {e}")
        return redirect(url_for("dashboard"))

@app.route("/checkout/<int:kit_id>", methods=["POST"])
@login_required
def checkout_kit(kit_id):
    user_id = session["user_id"]
    note    = f"Checked out via TSP Portal {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    # Get kit tag
    kit = snipe_get(f"/hardware/{kit_id}")
    kit_tag = kit.get("asset_tag", "")
    bags = get_kit_structure(kit_tag)
    done = 0; failed = 0
    # Checkout all L3 assets
    for bag in bags:
        for asset in bag["assets"]:
            if checkout_to_user(asset["id"], user_id, note): done += 1
            else: failed += 1
    # Checkout all L2 bags
    for bag in bags:
        if checkout_to_user(bag["id"], user_id, note): done += 1
        else: failed += 1
    # Checkout kit itself
    if checkout_to_user(kit_id, user_id, note): done += 1
    else: failed += 1
    return jsonify({"status": "success", "done": done, "failed": failed})

@app.route("/checkout-bag/<int:bag_id>", methods=["POST"])
@login_required
def checkout_bag(bag_id):
    """Checkout a single bag and its contents — also checks out parent kit"""
    user_id = session["user_id"]
    note    = f"Checked out via TSP Portal {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    bag     = snipe_get(f"/hardware/{bag_id}")
    bag_tag = bag.get("asset_tag", "")
    done = 0; failed = 0

    # Checkout bag itself
    if checkout_to_user(bag_id, user_id, note): done += 1
    else: failed += 1

    # Checkout L3 assets belonging to this bag by tag prefix
    if bag_tag.startswith("BAG-"):
        kit_prefix = bag_tag.replace("BAG-", "").rsplit("-", 1)[0]  # e.g. P01
        bag_suffix = bag_tag.split("-")[-1]  # e.g. CAM, LGT1
        all_assets = snipe_get("/hardware", {"limit": 500}).get("rows", [])
        for asset in all_assets:
            tag = asset.get("asset_tag", "")
            if kit_prefix in tag and not tag.startswith("BAG-") and not tag.startswith("KIT-"):
                if checkout_to_user(asset["id"], user_id, note): done += 1

        # Also checkout the parent kit so it shows on dashboard
        kit_tag = f"KIT-{kit_prefix}"
        kit = snipe_get(f"/hardware/bytag/{kit_tag}")
        if kit and kit.get("status") != "error":
            assigned = kit.get("assigned_to", {})
            # Only checkout kit if not already assigned to someone
            if not isinstance(assigned, dict) or not assigned.get("id"):
                if checkout_to_user(kit["id"], user_id, note): done += 1

    return jsonify({"status": "success", "done": done, "failed": failed})

@app.route("/checkin/<int:kit_id>", methods=["POST"])
@login_required
def checkin_kit_route(kit_id):
    note    = f"Checked in via TSP Portal {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    kit     = snipe_get(f"/hardware/{kit_id}")
    kit_tag = kit.get("asset_tag", "")
    bags    = get_kit_structure(kit_tag)
    done = 0; failed = 0
    for bag in bags:
        for asset in bag["assets"]:
            if checkin_asset(asset["id"], note): done += 1
            else: failed += 1
    for bag in bags:
        if checkin_asset(bag["id"], note): done += 1
        else: failed += 1
    if checkin_asset(kit_id, note): done += 1
    else: failed += 1
    return jsonify({"status": "success", "done": done, "failed": failed})

@app.route("/fault", methods=["GET", "POST"])
@login_required
def fault_report():
    # Pre-fill from query params (when clicking Report on a specific asset)
    asset_id  = request.args.get("asset_id", "")
    asset_tag = request.args.get("asset_tag", "")
    kit_tag   = request.args.get("kit_tag", "")
    asset_name= request.args.get("asset_name", "")
    make      = request.args.get("make", "")
    model     = request.args.get("model", "")
    serial    = request.args.get("serial", "")

    if request.method == "POST":
        f_asset_id   = request.form.get("asset_id", "")
        f_kit        = request.form.get("kit_tag", "")
        f_make       = request.form.get("make", "")
        f_model      = request.form.get("model", "")
        f_serial     = request.form.get("serial", "")
        f_desc       = request.form.get("description", "").strip()
        f_replacement= request.form.get("replacement_required", "No")
        f_photog     = session["user_name"]
        f_date       = datetime.now().strftime("%Y-%m-%d")

        if f_asset_id and f_desc:
            try:
                title = f"Fault: {f_make} {f_model} ({f_kit}) — reported by {f_photog}"
                notes = (
                    f"Kit #: {f_kit}\n"
                    f"Date: {f_date}\n"
                    f"Make: {f_make}\n"
                    f"Model: {f_model}\n"
                    f"Serial: {f_serial}\n"
                    f"Photographer: {f_photog}\n"
                    f"Replacement required: {f_replacement}\n\n"
                    f"Description of problem:\n{f_desc}"
                )
                result = snipe_post("/maintenances", {
                    "asset_id":               int(f_asset_id),
                    "is_warranty":            0,
                    "notes":                  notes,
                    "asset_maintenance_type": "Repair",
                    "title":                  title,
                    "name":                   title,
                    "start_date":             f_date,
                })
                print(f"Maintenance result: {result}")
                if result.get("status") == "success" or result.get("id"):
                    return render_template("fault_success.html",
                        user_name=session["user_name"],
                        kit_tag=f_kit
                    )
                else:
                    print(f"Maintenance failed: {result}")
                    return render_template("fault_success.html",
                        user_name=session["user_name"],
                        kit_tag=f_kit
                    )
            except Exception as e:
                print(f"Fault report error: {e}")
                import traceback; traceback.print_exc()

    return render_template("fault.html",
        user_name=session["user_name"],
        asset_id=asset_id,
        asset_tag=asset_tag,
        kit_tag=kit_tag,
        asset_name=asset_name,
        make=make,
        model=model,
        serial=serial,
        today=datetime.now().strftime("%Y-%m-%d"),
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)
