"""Checkin changes

Revision ID: f155905b37f6
Revises: fb6c96630733
Create Date: 2016-07-24 22:49:44.350212

"""

# revision identifiers, used by Alembic.
revision = 'f155905b37f6'
down_revision = 'fb6c96630733'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('ticket_checkin_version',
    sa.Column('ticket_id', sa.Integer(), autoincrement=False, nullable=False),
    sa.Column('checked_in', sa.Boolean(), autoincrement=False, nullable=True),
    sa.Column('badged_up', sa.Boolean(), autoincrement=False, nullable=True),
    sa.Column('transaction_id', sa.BigInteger(), autoincrement=False, nullable=False),
    sa.Column('operation_type', sa.SmallInteger(), nullable=False),
    sa.PrimaryKeyConstraint('ticket_id', 'transaction_id', name=op.f('pk_ticket_checkin_version'))
    )
    with op.batch_alter_table('ticket_checkin_version', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ticket_checkin_version_operation_type'), ['operation_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_ticket_checkin_version_transaction_id'), ['transaction_id'], unique=False)

    with op.batch_alter_table(u'ticket', schema=None) as batch_op:
        batch_op.drop_constraint(u'uq_ticket_qrcode', type_='unique')
        batch_op.drop_constraint(u'uq_ticket_receipt', type_='unique')
        batch_op.drop_column('qrcode')
        batch_op.drop_column('receipt')

    with op.batch_alter_table(u'ticket_checkin', schema=None) as batch_op:
        batch_op.drop_column('timestamp')

    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table(u'ticket_checkin', schema=None) as batch_op:
        batch_op.add_column(sa.Column('timestamp', sa.DATETIME(), nullable=False))

    with op.batch_alter_table(u'ticket', schema=None) as batch_op:
        batch_op.add_column(sa.Column('receipt', sa.VARCHAR(), nullable=True))
        batch_op.add_column(sa.Column('qrcode', sa.VARCHAR(), nullable=True))
        batch_op.create_unique_constraint(u'uq_ticket_receipt', ['receipt'])
        batch_op.create_unique_constraint(u'uq_ticket_qrcode', ['qrcode'])

    with op.batch_alter_table('ticket_checkin_version', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ticket_checkin_version_transaction_id'))
        batch_op.drop_index(batch_op.f('ix_ticket_checkin_version_operation_type'))

    op.drop_table('ticket_checkin_version')
    ### end Alembic commands ###
