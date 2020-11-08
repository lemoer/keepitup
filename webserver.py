#!/usr/bin/env python3

from flask import Flask, session, render_template, abort, request, flash, url_for, redirect, g
from main import *
import dns.resolver
from config import *
from flask_sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = SQLITE_URI

sqlalchemy = SQLAlchemy(app)

influx = get_influx()

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
    node.load_from_influx(influx, datetime.timedelta(minutes=15))

    if not node:
        abort(404)

    now = datetime.datetime.now()
    pings = np.flipud(node.pings)
    return render_template("node.html", node=node, now=now, pings=pings)

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

    return dict(node_list=nodeset, user=get_user())


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

    return redirect('/')

@app.route('/subscribe')
def subscribe():
    user = get_user()
    if not user:
        flash('Error: You need to be logged in to subscribe.', 'danger')
        return redirect('/')

    def res(code):
        return render_template("subscribe.html", nodes_json_cache=nodes_json_cache), code

    db = get_db()
    nodeset = NodeSet()
    nodeset.update_from_db(db)
    nodes_json_cache = NodesJSONCache()
    nodes_json_cache.update(nodeset)

    if "nodeid" in request.args:
        node = nodes_json_cache.find_by_nodeid(request.args['nodeid'])

        if not node:
            flash('Error: Node with nodeid ' + request.args['nodeid'] + " not found!", 'danger')
            return res(400)

        if user in node.subscribed_users:
            flash('Error: You are already subscribed to ' + node.name + '!', 'danger')
            return res(400)

        s = Subscription()
        s.user = user
        s.node = node

        db.add(s)
        db.add(node) # node might not be in db yet
        db.commit()

        flash('Subscribed to node ' + node.name + '.', 'success')
        return redirect('/subscribe')

    return res(200)