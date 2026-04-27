select
    id as order_id,
    customer_id,
    status,
    order_date,
    amount          -- note: column is 'amount', not 'order_amount'
from {{ source('raw', 'orders') }}
