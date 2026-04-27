select
    o.order_id,
    o.customer_id,
    o.order_date,
    o.status,
    o.order_amount,   -- BUG: column is named 'amount' in stg_orders, not 'order_amount'
    c.first_name,
    c.last_name,
    c.email
from {{ ref('stg_orders') }} o
left join {{ ref('stg_customers') }} c
    on o.customer_id = c.customer_id
