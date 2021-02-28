#!/usr/bin/env python3

from flask import Flask, session, render_template, abort, request, flash, url_for, redirect, g
from main import *
import dns.resolver
from config import *
from flask_sqlalchemy import SQLAlchemy
from flask_babel import Babel, gettext

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = SQLITE_URI
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
babel = Babel(app)

sqlalchemy = SQLAlchemy(app)

influx = get_influx()

@babel.localeselector
def get_locale():
    # otherwise try to guess the language from the user accept
    # header the browser transmits.  We support de/fr/en in this
    # example.  The best match wins.
    return request.accept_languages.best_match(['de', 'fr', 'en'])

def get_db():
    global sqlalchemy
    return sqlalchemy.session

@app.errorhandler(404)
def page_not_found(e):
    # note that we set the 404 status explicitly
    return render_template('404.html'), 404

@app.route('/')
def hello_world():
    return render_template("index.html")

@app.route('/node/<nodeid>')
def node(nodeid):
    db = get_db()
    nodeset = NodeSet()
    nodeset.update_from_db(db)

    node = nodeset.find_by_nodeid(nodeid)

    if not node:
        flash('Error: Node with nodeid ' + nodeid + " not found!", 'danger')
        abort(404)

    if influx:
        node.load_from_influx(influx, datetime.timedelta(minutes=15))

    now = datetime.datetime.now()
    pings = np.flipud(node.pings)

    subscription = node.get_subscription_by_user(db, get_user())

    return render_template("node.html", node=node, now=now, pings=pings,
                           NODE_LINKS=NODE_LINKS, subscription=subscription)

@app.route('/node/<nodeid>/toggle_notifications')
def toggle_notifications(nodeid):
    db = get_db()
    nodeset = NodeSet()
    nodeset.update_from_db(db)

    user = get_user()

    if not user:
        flash('Error: You need to be logged in to toggle notifications.', 'danger')
        return redirect('/')


    node = nodeset.find_by_nodeid(nodeid)

    if not node:
        flash('Error: Node with nodeid ' + nodeid + " not found!", 'danger')
        return redirect_to_last_page()

    subscription = node.get_subscription_by_user(db, user)

    if not subscription:
        flash('Error: Toggling notifications failed. You were not subscribed to ' + node.name + "!", 'danger')
        return redirect_to_last_page()

    subscription.send_notifications = not subscription.send_notifications
    db.add(subscription)
    db.commit()
    return redirect_to_last_page()


@app.route('/register', methods=['GET', 'POST'])
def register():
    db = get_db()

    def res(code):
        return render_template("register.html"), code

    if request.method == 'POST':
        email = request.form.get('email')
        if '@' not in email:
            flash('Error: The entered mail does not contain an @.', 'danger')
            return res(400)

        domain = email.rsplit('@', 1)[-1]
        try:
            dns.resolver.query(domain, 'MX')
        except dns.resolver.Timeout:
            flash('Error: Email invalid. The domain ' + domain + ' does not have an MX record.', 'danger')
            return res(400)
        except dns.resolver.NXDOMAIN:
            flash('Error: Email invalid. The domain ' + domain + ' does not have an MX record.', 'danger')
            return res(400)

        user = User.find_by_email(db, email)

        if user:
            flash('User already registered. Resending login token.', 'warning')
            user.send_confirm_mail(url_for('login', _external=True))
            return res(200)

        user = User(email=email)
        db.add(user)
        db.commit()
        user.send_confirm_mail(url_for('login', _external=True))
        flash('Confirmation mail sent.', 'info')
        return res(200)

    return res(200)

def get_user():
    db = get_db()
    email = session.get('email', None)
    user = None

    if email:
        user = User.find_by_email(db, email)

    return user

@app.context_processor
def inject_stuff():
    db = get_db()

    nodeset = NodeSet()
    nodeset.update_from_db(db)

    return dict(node_list=nodeset, user=get_user(), np=np)

@app.template_filter('show_constitution')
def show_constitution(node):
    if node.constitution == 'ok':
        css_class = 'text-success'
    elif node.constitution == 'problem':
        css_class = 'text-danger'
    else:
        css_class = 'text-muted'

    return '<span class="%s">%s</span>' % (css_class, node.constitution)

@app.route('/login')
def login():
    db = get_db()

    def res(code):
        return render_template("login.html"), code

    if 'email' not in request.args:
        flash('Error: Email was not given in request. Please use the link from your confirmation mail.', 'danger')
        return res(400)

    if 'token' not in request.args:
        flash('Error: Token was not given in request. Please use the link from your confirmation mail.', 'danger')
        return res(400)

    user = User.find_by_email(db, request.args['email'])

    if not user:
        flash('Error: Email not found.', 'danger')
        return res(400)


    if not user.try_confirm(db, request.args['token']):
        flash('Error: The supplied token is invalid.', 'danger')
        return res(400)

    session['email'] = user.email

    flash('Success: Email confirmed. You are now logged in.', 'success')
    return redirect('/')

@app.route('/logout')
def logout():
    if session['email'] is not None:
        session['email'] = None

        flash('Logged out.', 'info')

    return redirect_to_last_page()

def redirect_to_last_page():
    referrer = request.headers.get("Referer", None)

    if referrer:
        return redirect(referrer)

    return redirect('/')

@app.route('/subscribe')
def subscribe():
    user = get_user()
    if not user:
        flash('Error: You need to be logged in to subscribe.', 'danger')
        return redirect('/')

    def res(code):
        return render_template("subscribe.html", nodes_json_cache=nodes_json_cache), code

    def try_subscribe(node):
        if user in node.subscribed_users:
            flash('Error: You are already subscribed to ' + node.name + '!', 'danger')
            return redirect_to_last_page()

        s = Subscription()
        s.user = user
        s.node = node

        db.add(s)
        db.add(node) # node might not be in db yet
        db.commit()

        flash('Subscribed to node ' + node.name + '.', 'success')
        if request.args.get('goto') == 'yes':
            return redirect(url_for('node', nodeid=node.nodeid))
        else:
            return redirect_to_last_page()


    db = get_db()
    nodeset = NodeSet()
    nodeset.update_from_db(db)

    # First, we try to query the nodeset. By chance, someone is already
    # subscribed to this node. This is usually faster than loading the
    # nodes.json.
    if "nodeid" in request.args:
        node = nodeset.find_by_nodeid(request.args['nodeid'])

        if node:
            return try_subscribe(node)

    nodes_json_cache = NodesJSONCache()
    nodes_json_cache.update(nodeset)

    if "nodeid" in request.args:
        node = nodes_json_cache.find_by_nodeid(request.args['nodeid'])

        if not node:
            flash('Error: Node with nodeid ' + request.args['nodeid'] + " not found!", 'danger')
            return res(400)

        return try_subscribe(node)

    return res(200)

@app.route('/unsubscribe')
def unsubscribe():
    user = get_user()
    if not user:
        flash('Error: You need to be logged in to unsubscribe.', 'danger')
        return redirect('/')

    if 'nodeid' not in request.args:
        flash('Error: Unsubscribe failed. No nodeid was given.', 'danger')
        return redirect_to_last_page()

    db = get_db()
    nodeset = NodeSet()
    nodeset.update_from_db(db)

    node = nodeset.find_by_nodeid(request.args['nodeid'])

    if not node:
        flash('Error: Unsubscribe failed. Node with nodeid ' + request.args['nodeid'] + " not found!", 'danger')
        return redirect_to_last_page()

    subscription = node.get_subscription_by_user(db, user)

    if not subscription:
        flash('Error: Unsubscribe failed. You were not subscribed to ' + node.name + "!", 'danger')
        return redirect_to_last_page()

    db.delete(subscription)
    db.commit()

    flash('Sucessfully unsubscribed from ' + node.name + "!", 'info')

    if len(node.subscriptions) == 0:
        db.delete(node)
        db.commit()
        flash('Node ' + node.name + ' was removed, because nobody subscribes to it anymore.', 'info')

        return redirect('/')

    return redirect_to_last_page()
