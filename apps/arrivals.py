import re
from collections import OrderedDict

from flask import (
    render_template, redirect, request, flash,
    url_for, session, current_app as app, Blueprint, abort,
    Markup, render_template_string,
)
from sqlalchemy import func

from models.ticket import Ticket, TicketType, CheckinStateException, TicketCheckin
from models.user import User, checkin_code_re
from .common import require_permission, json_response

arrivals = Blueprint('arrivals', __name__)

arrivals_required = require_permission('arrivals')  # Decorator to require arrivals permission


@arrivals.route('')
@arrivals_required
def main():
    badge = bool(session.get('badge'))
    return render_template('arrivals/arrivals.html', badge=badge)


@arrivals.route('/check-in')
@arrivals_required
def begin_check_in():
    session.pop('badge', None)
    return redirect(url_for('.main'))


@arrivals.route('/badge-up')
@arrivals_required
def begin_badge_up():
    session['badge'] = True
    return redirect(url_for('.main'))


# Entrypoint for QR code if desired
@arrivals.route('/checkin/qrcode/<code>')
@arrivals_required
def checkin_qrcode(code):
    match = re.match('%s$' % checkin_code_re, code)
    if not match:
        abort(404)

    user = User.get_by_checkin_code(app.config.get('SECRET_KEY'), code)
    return redirect(url_for('.checkin', user_id=user.id))


def user_from_code(query):
    if not query:
        return None

    # QR code
    match = re.match(re.escape(app.config.get('CHECKIN_BASE')) + '(%s)$' % checkin_code_re, query)
    if not match:
        # Barcode
        match = re.match('(%s)$' % checkin_code_re, query)

    if not match:
        return None

    code = match.group(1)
    user = User.get_by_checkin_code(app.config.get('SECRET_KEY'), code)
    return user

def users_from_query(query):
    names = User.query.order_by(User.name)
    emails = User.query.order_by(User.email)

    def escape(like):
        return like.replace('^', '^^').replace('%', '^%')

    def name_match(pattern, query):
        return names.filter(User.name.ilike(pattern.format(query), escape='^')).limit(10).all()

    def email_match(pattern, query):
        return emails.filter(User.email.ilike(pattern.format(query), escape='^')).limit(10).all()

    fulls = []
    starts = []
    contains = []
    query = query.lower()
    words = map(escape, filter(None, query.split(' ')))

    if ' ' in query:
        fulls += name_match('%{0}%', '%'.join(words))
        fulls += email_match('%{0}%', '%'.join(words))

    for word in words:
        starts += name_match('{0}%', word)
        contains += name_match('%{0}%', word)

    for word in words:
        starts += email_match('{0}%', word)
        contains += email_match('%{0}%', word)

    # make unique, but keep in order
    users = list(OrderedDict.fromkeys(fulls + starts + contains))[:10]
    return users


@arrivals.route('/search', methods=['GET', 'POST'])
@arrivals.route('/search/<query>')  # debug only
@json_response
@arrivals_required
def search(query=None):
    if not (app.config.get('DEBUG') and query):
        query = request.form.get('q')

    if query.startswith('fail'):
        raise ValueError('User-requested failure: %s' % query)

    if not query:
        abort(404)

    data = {}
    if request.form.get('n'):
        # To serialise requests as they may go slow for certain query strings
        data['n'] = int(request.form.get('n'))

    query = query.strip()
    badge = bool(session.get('badge'))

    user = user_from_code(query)

    if user:
        return {'location': url_for('.checkin', user_id=user.id)}

    users_ordered = users_from_query(query)
    users = User.query.filter(User.id.in_([u.id for u in users_ordered]))
    tickets = users.join(Ticket).filter_by(paid=True) \
                   .group_by(User).with_entities(User.id, func.count(User.id))
    tickets = dict(tickets)

    checkins = users.join(Ticket, TicketCheckin)
    if badge:
        completes = checkins.filter_by(badged_up=True) \
                            .join(TicketType).filter_by(has_badge=True)
    else:
        completes = checkins.filter_by(checked_in=True)

    completes = completes.group_by(User).with_entities(User.id, func.count(User.id))
    completes = dict(completes)

    user_data = []
    for u in users:
        user = {
            'id': u.id,
            'name': u.name,
            'email': u.email,
            'tickets': tickets.get(u.id, 0),
            'completes': completes.get(u.id, 0),
            'url': url_for('.checkin', user_id=u.id)
        }
        user_data.append(user)

    data['users'] = user_data

    return data


@arrivals.route('/checkin/<int:user_id>', methods=['GET', 'POST'])
@arrivals_required
def checkin(user_id):
    badge = bool(session.get('badge'))
    user = User.query.get_or_404(user_id)

    if badge:
        # Ticket must be checked in to receive a badge
        tickets = user.tickets \
                      .join(TicketCheckin).filter_by(checked_in=True) \
                      .join(TicketType).filter_by(has_badge=True)
    else:
        tickets = user.tickets.filter_by(paid=True)

    if request.method == 'POST':
        failed = []
        for t in tickets:
            # Only allow bulk completion, not undoing
            try:
                if badge:
                    t.badge_up()
                else:
                    t.check_in()
            except CheckinStateException:
                failed.append(t)

        if failed:
            failed_str = ', '.join(str(t.id) for t in failed)
            if badge:
                flash("Already issued: %s" % failed_str)
            else:
                flash("Already checked in: %s" % failed_str)

            return redirect(url_for('.checkin', user_id=user.id))

        msg = Markup(render_template_string('''
            {{ tickets.count() }} ticket {{- tickets.count() != 1 and 's' or '' }} checked in.
            <a class="alert-link" href="{{ url_for('.checkin', user_id=user.id) }}">Show tickets</a>.''',
            user=user, tickets=tickets))
        flash(msg)

        return redirect(url_for('.main'))

    return render_template('arrivals/checkin.html', user=user,
                           tickets=tickets, badge=badge)


@arrivals.route('/checkin/ticket/<ticket_id>', methods=['POST'])
@arrivals_required
def ticket_checkin(ticket_id):
    badge = bool(session.get('badge'))
    ticket = Ticket.query.get_or_404(ticket_id)

    try:
        if badge:
            ticket.badge_up()
        else:
            ticket.check_in()
    except CheckinStateException as e:
        flash(str(e))

    return redirect(url_for('.checkin', user_id=ticket.user.id))

@arrivals.route('/checkin/ticket/<ticket_id>/undo', methods=['POST'])
@arrivals_required
def undo_ticket_checkin(ticket_id):
    badge = bool(session.get('badge'))
    ticket = Ticket.query.get_or_404(ticket_id)

    try:
        if badge:
            ticket.undo_badge_up()
        else:
            ticket.undo_check_in()
    except CheckinStateException as e:
        flash(str(e))

    return redirect(url_for('.checkin', user_id=ticket.user.id))

