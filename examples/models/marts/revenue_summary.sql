select
    o.order_date,
    count(o.order_id) as order_count,
    sum(o.order_amount) as total_revenue,
    p.payment_method
from {{ ref('fct_orders') }} o
left join {{ ref('stg_payments') }} p   -- BUG: model was renamed to stg_payment_methods
    on o.order_id = p.order_id
group by 1, 4
