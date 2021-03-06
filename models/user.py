import base64
import hmac
import hashlib
from datetime import datetime, timedelta
import time
import struct

from main import db
from permission import UserPermission, Permission
from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound
from flask import current_app as app
from flask.ext.login import UserMixin

CHECKIN_CODE_LEN = 16
checkin_code_re = r'[0-9a-zA-Z_-]{%s}' % CHECKIN_CODE_LEN

def generate_login_code(key, timestamp, uid):
    msg = "%s-%s" % (int(timestamp), uid)
    mac = hmac.new(key, 'login-' + msg, digestmod=hashlib.sha256)
    # Truncate the digest to 20 base64 bytes
    return msg + "-" + base64.urlsafe_b64encode(mac.digest())[:20]

def verify_login_code(key, current_timestamp, code):
    try:
        timestamp, uid, _ = code.split("-", 2)
    except ValueError:
        return None
    if hmac.compare_digest(generate_login_code(key, timestamp, uid), code):
        age = datetime.fromtimestamp(current_timestamp) - datetime.fromtimestamp(int(timestamp))
        if age > timedelta(hours=6):
            return None
        else:
            return int(uid)
    return None


def generate_sso_code(key, timestamp, uid):
    msg = "%s-%s" % (int(timestamp), uid)
    mac = hmac.new(key, 'sso-' + msg, digestmod=hashlib.sha256)
    # Truncate the digest to 20 base64 bytes
    return msg + "-" + base64.urlsafe_b64encode(mac.digest())[:20]


def generate_checkin_code(key, user_id, version=1):
    # H = short (< 65536), B = byte (< 256)
    msg = struct.pack('HB', user_id, version)
    mac = hmac.new(key, 'checkin-' + msg, digestmod=hashlib.sha256)
    # An input length that's a multiple of 3 ensures no wasted output
    # 9 bytes (72 bits) won't resist offline attacks, so be careful
    code = base64.urlsafe_b64encode(msg + mac.digest()[:9])
    # The output length should be (len(msg) + 9) / 3 * 4
    assert len(code) == CHECKIN_CODE_LEN
    return code

def verify_checkin_code(key, code):
    msg = base64.urlsafe_b64decode(code.encode('utf-8')[:4])
    user_id, version = struct.unpack('HB', msg)
    if version != 1:
        return None

    expected_code = generate_checkin_code(key, user_id, version=version)
    if hmac.compare_digest(expected_code, code):
        return user_id
    return None


class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, unique=True, index=True)
    name = db.Column(db.String, nullable=False, index=True)
    phone = db.Column(db.String, nullable=True)
    will_have_ticket = db.Column(db.Boolean, nullable=False, default=False)  # for CfP filtering
    checkin_note = db.Column(db.String, nullable=True)

    diversity = db.relationship('UserDiversity', uselist=False, backref='user', cascade='all, delete, delete-orphan')
    tickets = db.relationship('Ticket', lazy='dynamic', backref='user', cascade='all, delete, delete-orphan')
    payments = db.relationship('Payment', lazy='dynamic', backref='user', cascade='all')
    permissions = db.relationship('Permission', backref='user', cascade='all', secondary=UserPermission)
    votes = db.relationship('CFPVote', backref='user', lazy='dynamic')

    proposals = db.relationship('Proposal',
                                primaryjoin='Proposal.user_id == User.id',
                                backref='user', lazy='dynamic',
                                cascade='all, delete, delete-orphan')
    anonymised_proposals = db.relationship('Proposal',
                                           primaryjoin='Proposal.anonymiser_id == User.id',
                                           backref='anonymiser', lazy='dynamic',
                                           cascade='all, delete, delete-orphan')
    transfers_to = db.relationship('TicketTransfer',
                                   primaryjoin='TicketTransfer.to_user_id == User.id',
                                   backref='to_user', lazy='dynamic')
    transfers_from = db.relationship('TicketTransfer',
                                   primaryjoin='TicketTransfer.from_user_id == User.id',
                                   backref='from_user', lazy='dynamic')

    messages_from = db.relationship('CFPMessage',
                                   primaryjoin='CFPMessage.from_user_id == User.id',
                                   backref='from_user', lazy='dynamic')

    def __init__(self, email, name):
        self.email = email
        self.name = name

    def login_code(self, key):
        return generate_login_code(key, int(time.time()), self.id)

    def sso_code(self, key):
        return generate_sso_code(key, int(time.time()), self.id)

    @property
    def checkin_code(self):
        return generate_checkin_code(app.config.get('SECRET_KEY'), self.id)

    def has_permission(self, name, cascade=True):
        if cascade and name != 'admin' and self.has_permission('admin'):
            return True
        for permission in self.permissions:
            if permission.name == name:
                return True
        return False

    def grant_permission(self, name):
        try:
            perm = Permission.query.filter_by(name=name).one()
        except NoResultFound:
            perm = Permission(name)
            db.session.add(perm)
        self.permissions.append(perm)
        db.session.commit()

    def revoke_permission(self, name):
        for user_perm in self.permissions:
            if user_perm.name == name:
                self.permissions.remove(user_perm)
        db.session.commit()

    def __repr__(self):
        return '<User %s>' % self.email

    @classmethod
    def get_by_email(cls, email):
        return User.query.filter(func.lower(User.email) == func.lower(email)).one()

    @classmethod
    def does_user_exist(cls, email):
        try:
            User.get_by_email(email)
            return True
        except NoResultFound:
            return False

    @classmethod
    def get_by_code(cls, key, code):
        uid = verify_login_code(key, time.time(), code)
        if uid is None:
            return None

        return User.query.filter_by(id=uid).one()

    @classmethod
    def get_by_checkin_code(cls, key, code):
        uid = verify_checkin_code(key, code)
        if uid is None:
            return None

        return User.query.filter_by(id=uid).one()


class UserDiversity(db.Model):
    __tablename__ = 'diversity'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, primary_key=True)
    age = db.Column(db.String)
    gender = db.Column(db.String)
    ethnicity = db.Column(db.String)


