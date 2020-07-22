from werkzeug.exceptions import abort
from .config import Configuration
from .user import User
from .wrappers import is_admin, requires_admin, check_db_conn, ajax_requires_admin

from flask import render_template, request, redirect, flash, url_for, Blueprint, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from .database_helper import update_hs_id, lookup_by_id

from .upload import retire_handshake

blob_api = Blueprint('blob_api', __name__)


def get_cracked_tuple(document):
    handshake = document["handshake"]
    result = dict()

    result["id"] = document["id"]
    result["ssid"] = handshake["SSID"]
    result["mac"] = handshake["MAC"]
    result["hs_type"] = handshake["handshake_type"]
    result["date_added"] = document["date_added"].strftime('%H:%M - %d.%m.%Y')
    result["cracked_by"] = handshake["cracked_rule"]

    result["password"] = handshake["password"]
    result["date"] = handshake["date_cracked"].strftime('%H:%M - %d.%m.%Y')
    result["raw_date"] = handshake["date_cracked"]

    return result


def get_uncracked_tuple(document):
    handshake = document["handshake"]
    result = dict()

    result["id"] = document["id"]
    result["ssid"] = handshake["SSID"]
    result["mac"] = handshake["MAC"]
    result["hs_type"] = handshake["handshake_type"]
    result["date_added"] = document["date_added"].strftime('%H:%M - %d.%m.%Y')
    if handshake["active"]:
        result["tried_rules"] = "Trying rule %s" % document["reserved"]["tried_rule"]
        result["eta"] = handshake["eta"]
    else:
        result["tried_rules"] = "%s/%s" % (len(handshake["tried_dicts"]), Configuration.number_rules)
        result["eta"] = ""

    return result


@blob_api.route('/admin/', methods=['GET', 'POST'])
@requires_admin
def admin_panel():
    if request.method == 'GET':
        if check_db_conn() is None:
            flash("DATABASE IS DOWN!")
            return render_template('admin.html')

        admin_table, error = Configuration.get_admin_table()
        if admin_table is None:
            flash(error)
            return render_template('admin.html')

        workload = int(admin_table["workload"])

        if workload < 1 or workload > 4:
            workload = 2
            flash("Workload returned by database is not within bounds! Corrected to value 2.")
            Configuration.logger.error("Workload returned by database is not within bounds! Corrected to value 2.")

        return render_template('admin.html', workload=workload)

    elif request.method == 'POST':
        workload = int(request.form.get("workload", None))
        force = False if request.form.get("force_checkbox", None) is None else True

        update = {"workload": workload, "force": force}

        flash("Workload = '%s', force = '%s'" % (workload, force), category='success')

        Configuration.set_admin_table(update)

        return render_template('admin.html', workload=workload)
    else:
        Configuration.logger.error("Unsupported method!")
        abort(404)


@blob_api.route('/', methods=['GET'])
def home():
    if is_admin(current_user):
        if check_db_conn() is None:
            flash("DATABASE IS DOWN")
            return render_template('admin_home.html')

        # Dictionary with key=<user>, value=[<handshake>]
        user_handshakes = {}

        try:
            all_files = Configuration.wifis.find({}).sort([("date_added", 1)])
            Configuration.logger.info("Retrieved all user data for admin display.")
        except Exception as e:
            Configuration.logger.error("Database error at retrieving all user data %s" % e)
            flash("Database error at retrieving all user data %s" % e)
            return render_template('admin_home.html')

        for file_structure in all_files:
            # First user is the original uploader
            crt_user = file_structure["users"][0]

            if crt_user not in user_handshakes:
                user_handshakes[crt_user] = {"cracked": [], "uncracked": []}

            if file_structure["handshake"]["password"] == "":
                user_handshakes[crt_user]["uncracked"].append(get_uncracked_tuple(file_structure))
            else:
                user_handshakes[crt_user]["cracked"].append(get_cracked_tuple(file_structure))

        users_list = list(Configuration.users.find())
        no_users = len(users_list)
        for i in range(no_users):
            crt_user = users_list[i]["username"]
            if crt_user not in user_handshakes and crt_user != Configuration.admin_account:
                user_handshakes[crt_user] = {"cracked": [], "uncracked": []}

        # Sort based on crack date using raw date field
        for entry in user_handshakes.values():
            entry["cracked"] = sorted(entry["cracked"], key=lambda k: k["raw_date"])

        # Transform dict to list and sort by username
        user_handshakes = sorted(user_handshakes.items(), key=lambda k: k[0])

        #  Dictionary with key=<user>, value=[<allow_api_value>]
        entries = Configuration.users.find({})
        allow_api_dict = {}
        for entry in entries:
            allow_api_dict[entry['username']] = entry['allow_api']

        return render_template('admin_home.html', user_handshakes=user_handshakes, permissions=allow_api_dict)

    logged_in = current_user.is_authenticated
    if logged_in and check_db_conn() is None:
        flash("Database error!")
        return render_template('home.html', logged_in=True)

    uncracked = []
    cracked = []
    if logged_in:
        # Sort in mongo by the time the handshake was added
        for file_structure in Configuration.wifis.find({"users": current_user.get_id()}).sort([("date_added", 1)]):
            # Sort in python by the SSID
            handshake = file_structure["handshake"]
            if handshake["password"] == "":
                uncracked.append(get_uncracked_tuple(file_structure))
            else:
                cracked.append(get_cracked_tuple(file_structure))

    # Sort based on crack date using raw date field
    cracked = sorted(cracked, key=lambda k: k["raw_date"])

    return render_template('home.html', uncracked=uncracked, cracked=cracked, logged_in=logged_in)


@blob_api.route('/change_permissions/<name>')
@ajax_requires_admin
def change_permissions(name):
    change = False
    if Configuration.users.find_one({'username': name})['allow_api']:
        Configuration.users.update_one({'username': name}, {"$set": {'allow_api': False}})
    else:
        Configuration.users.update_one({'username': name}, {"$set": {'allow_api': True}})
        change = True
    # return jsonify({"success": False, "reason": "Failed to connect to database"})
    return jsonify({"success": True, "data": change})


@blob_api.route('/delete_wifi/', methods=['POST'])
@login_required
def delete_wifi():
    wifi_id = request.form.get("id")
    document = lookup_by_id(wifi_id)
    if document is None:
        flash("Id does not exist!")
        return redirect(url_for("home"))

    if document is False:
        flash("Internal error occured")
        return redirect(url_for("blob_api.home"))

    new_users = document["users"]
    new_users.remove(current_user.get_id())
    if len(new_users) < 1:
        retire_handshake(wifi_id, document)
    else:
        update_hs_id(wifi_id, {"users": new_users})

    return redirect(url_for("blob_api.home"))


def get_rule_tuple(rule):
    try:
        priority = rule["priority"]
        name = rule["name"]
    except KeyError:
        Configuration.logger.error("Error! Malformed rule %s" % rule)
        return None

    examples = ""
    desc = ""
    link = ""
    try:
        desc = rule["desc"]
        link = rule["link"]
        for example in rule["examples"]:
            examples += example + " "

        if len(examples) > 0:
            examples = examples[:-1]
    except KeyError:
        pass

    return priority, name, desc, examples, link


@blob_api.route('/statuses/', methods=['GET'])
@login_required
def statuses():
    status_list = []

    for rule in Configuration.get_active_rules():
        status_list.append(get_rule_tuple(rule))

    return render_template('statuses.html', statuses=status_list)


@blob_api.route('/login/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        flash("User is already authenticated!")
        return redirect(url_for("blob_api.home"))

    if request.method == 'GET':
        return render_template('login.html')

    if request.method == 'POST':
        username = request.form.get("username", None)
        password = request.form.get("password", None)

        if username is None or len(username) == 0:
            flash("No username introduced!")
            return redirect(request.url)

        if password is None or len(password) == 0:
            flash("No password introduced!")
            return redirect(request.url)

        if not User.check_credentials(username, password):
            Configuration.logger.warning("Failed login attempt from username = '%s' with password = '%s'" %
                                         (username, password))
            flash("Incorrect username/password!")
            return redirect(request.url)

        login_user(User(username))

        return redirect(url_for("blob_api.home"))


@blob_api.route("/register/", methods=["GET", "POST"])
def register():
    if request.method == 'GET':
        if current_user.is_authenticated:
            flash("You already have an account")
            return redirect(url_for("blob_api.home"))
        return render_template('register.html')

    if request.method == "POST":
        username = request.form.get("username", None)
        password = request.form.get("password", None)

        if username is None or len(username) == 0:
            flash("No username introduced!")
            return redirect(request.url)

        if password is None or len(password) == 0:
            flash("No password introduced!")
            return redirect(request.url)

        if len(password) < 6:
            flash("C'mon... use at least 6 characters... pretty please?")
            return redirect(request.url)

        if Configuration.username_regex.search(username) is None:
            flash("Username should start with a letter and only contain alphanumeric or '-._' characters!")
            return redirect(request.url)

        if len(username) > 150 or len(password) > 150:
            flash("Either the username or the password is waaaaay too long. Please dont.")
            return redirect(request.url)

        retval = User.create_user(username, password)

        if retval is None:
            return redirect(url_for("blob_api.home"))

        flash(retval)
        return redirect(request.url)


@blob_api.route('/logout/', methods=["GET"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("blob_api.home"))


@blob_api.route('/profile/', methods=['GET', 'POST'])
@login_required
def profile():
    # TODO make a try except. Check for none
    user_entry = Configuration.users.find_one({"username": current_user.get_id()})

    fst_name = "Enter first name"
    last_name = "Enter last name"
    email = "Enter email"

    try:
        fst_name = Configuration.users.find_one({'username': current_user.get_id()})['first_name']
    except KeyError:
        pass

    try:
        last_name = Configuration.users.find_one({'username': current_user.get_id()})['last_name']
    except KeyError:
        pass

    try:
        email = Configuration.users.find_one({'username': current_user.get_id()})['email']
    except KeyError:
        pass

    if request.method == "POST":
        fst_name = request.form.get("first_name", None)
        last_name = request.form.get("last_name", None)
        email = request.form.get("email", None)

        if fst_name is not None and len(fst_name) > 0:
            try:
                if user_entry["first_name"] != fst_name:
                    Configuration.users.update({"username": current_user.get_id()}, {"$set": {"first_name": fst_name}})
            except KeyError:
                Configuration.users.update({"username": current_user.get_id()}, {"$set": {"first_name": fst_name}})

        if last_name is not None and len(last_name) > 0:
            try:
                if user_entry["last_name"] != last_name:
                    Configuration.users.update({"username": current_user.get_id()}, {"$set": {"last_name": last_name}})
            except KeyError:
                Configuration.users.update({"username": current_user.get_id()}, {"$set": {"last_name": last_name}})

        if email is not None and len(email) > 0:
            try:
                if user_entry["email"] != email:
                    Configuration.users.update({"username": current_user.get_id()}, {"$set": {"email": email}})
            except KeyError:
                Configuration.users.update({"username": current_user.get_id()}, {"$set": {"email": email}})

    return render_template('profile.html', username=current_user.get_id(), first_name=fst_name,
                           last_name=last_name, email=email)
