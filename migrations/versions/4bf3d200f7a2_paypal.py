"""'paypal'

Revision ID: 4bf3d200f7a2
Revises: e44ceda62698
Create Date: 2026-07-29 10:30:26.738749

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4bf3d200f7a2'
down_revision = 'e44ceda62698'
branch_labels = None
depends_on = None


from alembic import op


def upgrade():
    op.alter_column(
        "deposit_transaction",
        "paystack_reference",
        new_column_name="paypal_order_id"
    )


def downgrade():
    op.alter_column(
        "deposit_transaction",
        "paypal_order_id",
        new_column_name="paystack_reference"
    )
