-- Reusable analysis queries (SQLite). Revenue = net sales of lines NOT returned/refunded.
-- All results are SYNTHETIC DEMONSTRATION DATA.

-- name: monthly_sales_by_class
SELECT substr(transaction_date, 1, 7) || '-01' AS month, product_class,
       SUM(units_sold) AS units, ROUND(SUM(gross_sales_cad), 2) AS gross_sales, ROUND(SUM(net_sales_cad), 2) AS net_sales,
       ROUND(SUM(cogs_cad), 2) AS cogs, ROUND(SUM(gross_profit_cad), 2) AS gross_profit,
       ROUND(SUM(gross_sales_cad - net_sales_cad), 2) AS discount_value, COUNT(DISTINCT transaction_id) AS transactions
FROM sales_transactions WHERE return_status = 'Completed'
GROUP BY 1, 2 ORDER BY 1, 2;

-- name: monthly_totals
SELECT substr(transaction_date, 1, 7) || '-01' AS month,
       ROUND(SUM(net_sales_cad), 2) AS net_sales, ROUND(SUM(gross_profit_cad), 2) AS gross_profit,
       SUM(CASE WHEN product_class = 'E-Bike' THEN units_sold ELSE 0 END) AS bike_units,
       COUNT(DISTINCT transaction_id) AS transactions
FROM sales_transactions WHERE return_status = 'Completed' GROUP BY 1 ORDER BY 1;

-- name: sales_by_brand
SELECT brand, product_class, SUM(units_sold) AS units, ROUND(SUM(net_sales_cad), 2) AS net_sales,
       ROUND(SUM(gross_profit_cad), 2) AS gross_profit, ROUND(100.0 * SUM(gross_profit_cad) / SUM(net_sales_cad), 2) AS gross_margin_pct,
       ROUND(AVG(discount_pct) * 100, 2) AS avg_discount_pct
FROM sales_transactions WHERE return_status = 'Completed' GROUP BY 1, 2 ORDER BY net_sales DESC;

-- name: sales_by_model
SELECT s.product_id, s.brand, s.model, s.product_category, s.product_class, p.retail_price_cad,
       SUM(units_sold) AS units, ROUND(SUM(net_sales_cad), 2) AS net_sales, ROUND(SUM(gross_profit_cad), 2) AS gross_profit,
       ROUND(100.0 * SUM(gross_profit_cad) / SUM(net_sales_cad), 2) AS gross_margin_pct,
       MIN(transaction_date) AS first_sale, MAX(transaction_date) AS last_sale
FROM sales_transactions s JOIN products p USING (product_id)
WHERE return_status = 'Completed' GROUP BY 1, 2, 3, 4, 5, 6 ORDER BY net_sales DESC;

-- name: sales_by_category
SELECT product_category, product_class, SUM(units_sold) AS units, ROUND(SUM(net_sales_cad), 2) AS net_sales,
       ROUND(SUM(gross_profit_cad), 2) AS gross_profit, ROUND(100.0 * SUM(gross_profit_cad) / SUM(net_sales_cad), 2) AS gross_margin_pct
FROM sales_transactions WHERE return_status = 'Completed' GROUP BY 1, 2 ORDER BY net_sales DESC;

-- name: sales_by_channel
SELECT sales_channel, COUNT(DISTINCT transaction_id) AS transactions, ROUND(SUM(net_sales_cad), 2) AS net_sales,
       ROUND(SUM(net_sales_cad) / COUNT(DISTINCT transaction_id), 2) AS avg_transaction_value
FROM sales_transactions WHERE return_status = 'Completed' GROUP BY 1 ORDER BY net_sales DESC;

-- name: transaction_values
SELECT transaction_id, MIN(transaction_date) AS transaction_date, ROUND(SUM(net_sales_cad), 2) AS basket_value,
       MAX(CASE WHEN product_class = 'E-Bike' THEN 1 ELSE 0 END) AS has_bike, COUNT(*) AS lines,
       SUM(CASE WHEN product_class <> 'E-Bike' THEN 1 ELSE 0 END) AS non_bike_lines, MIN(sales_rep_id) AS sales_rep_id
FROM sales_transactions WHERE return_status = 'Completed' GROUP BY 1;

-- name: discount_bands
SELECT product_class,
       CASE WHEN discount_pct = 0 THEN '0%' WHEN discount_pct <= 0.05 THEN '0-5%' WHEN discount_pct <= 0.10 THEN '5-10%'
            WHEN discount_pct <= 0.15 THEN '10-15%' ELSE '>15%' END AS discount_band,
       SUM(units_sold) AS units, ROUND(SUM(net_sales_cad), 2) AS net_sales, ROUND(SUM(gross_profit_cad), 2) AS gross_profit,
       ROUND(100.0 * SUM(gross_profit_cad) / SUM(net_sales_cad), 2) AS gross_margin_pct,
       ROUND(SUM(gross_sales_cad - net_sales_cad), 2) AS discount_value
FROM sales_transactions WHERE return_status = 'Completed' GROUP BY 1, 2;

-- name: promotion_performance
SELECT p.promotion_id, p.promotion_name, p.start_date, p.end_date, p.discount_pct,
       COUNT(DISTINCT s.transaction_id) AS transactions, SUM(s.units_sold) AS units,
       ROUND(SUM(s.net_sales_cad), 2) AS net_sales, ROUND(SUM(s.gross_profit_cad), 2) AS gross_profit,
       ROUND(SUM(s.gross_sales_cad - s.net_sales_cad), 2) AS discount_cost
FROM promotions p LEFT JOIN sales_transactions s ON s.promotion_id = p.promotion_id AND s.return_status = 'Completed'
GROUP BY 1, 2, 3, 4, 5 ORDER BY p.start_date;

-- name: daily_bike_sales
SELECT c.date, c.open, c.mean_temp_c, c.precip_mm, c.snow_cm,
       COALESCE(SUM(CASE WHEN s.product_class = 'E-Bike' THEN s.units_sold END), 0) AS bike_units,
       COALESCE(SUM(s.net_sales_cad), 0) AS net_sales
FROM store_calendar c LEFT JOIN sales_transactions s ON s.transaction_date = c.date AND s.return_status = 'Completed'
GROUP BY 1, 2, 3, 4, 5 ORDER BY 1;

-- name: monthly_service
SELECT substr(date_received, 1, 7) || '-01' AS month, COUNT(*) AS orders,
       ROUND(SUM(labour_revenue_cad), 2) AS labour_revenue, ROUND(SUM(parts_revenue_cad), 2) AS parts_revenue,
       ROUND(SUM(labour_revenue_cad + parts_revenue_cad), 2) AS service_revenue, ROUND(SUM(parts_cost_cad), 2) AS parts_cost,
       ROUND(SUM(service_cost_cad), 2) AS service_cost, ROUND(SUM(gross_profit_cad), 2) AS service_gross_profit,
       ROUND(AVG(turnaround_days), 2) AS avg_turnaround_days, ROUND(AVG(satisfaction_score), 2) AS avg_satisfaction,
       SUM(warranty) AS warranty_orders
FROM service_orders GROUP BY 1 ORDER BY 1;

-- name: service_by_type
SELECT service_type, COUNT(*) AS orders, ROUND(SUM(labour_revenue_cad + parts_revenue_cad), 2) AS revenue,
       ROUND(SUM(gross_profit_cad), 2) AS gross_profit, ROUND(AVG(labour_revenue_cad + parts_revenue_cad), 2) AS avg_ticket,
       ROUND(AVG(labour_hours), 2) AS avg_labour_hours, ROUND(AVG(turnaround_days), 2) AS avg_turnaround_days,
       ROUND(AVG(satisfaction_score), 2) AS avg_satisfaction,
       ROUND(SUM(gross_profit_cad) / SUM(labour_hours), 2) AS gross_profit_per_labour_hour
FROM service_orders GROUP BY 1 ORDER BY revenue DESC;

-- name: technician_productivity
SELECT technician_id, e.role, COUNT(*) AS orders, ROUND(SUM(labour_hours), 1) AS labour_hours,
       ROUND(SUM(billable_hours), 1) AS billable_hours, ROUND(SUM(billable_hours) / SUM(labour_hours), 3) AS billable_ratio,
       ROUND(SUM(labour_revenue_cad + parts_revenue_cad), 2) AS revenue, ROUND(SUM(gross_profit_cad), 2) AS gross_profit,
       ROUND(AVG(turnaround_days), 2) AS avg_turnaround_days, ROUND(AVG(satisfaction_score), 2) AS avg_satisfaction
FROM service_orders s JOIN staff e ON e.employee_id = s.technician_id GROUP BY 1, 2 ORDER BY 1;

-- name: monthly_opex
SELECT * FROM operating_expenses ORDER BY month;

-- name: monthly_pnl
WITH s AS (SELECT substr(transaction_date, 1, 7) || '-01' AS month, SUM(net_sales_cad) AS retail_revenue, SUM(gross_profit_cad) AS retail_gp
           FROM sales_transactions WHERE return_status = 'Completed' GROUP BY 1),
     v AS (SELECT substr(date_received, 1, 7) || '-01' AS month, SUM(labour_revenue_cad + parts_revenue_cad) AS service_revenue,
                  SUM(gross_profit_cad) AS service_gp FROM service_orders GROUP BY 1)
SELECT o.month, ROUND(s.retail_revenue, 2) AS retail_revenue, ROUND(v.service_revenue, 2) AS service_revenue,
       ROUND(s.retail_revenue + v.service_revenue, 2) AS total_revenue,
       ROUND(s.retail_gp, 2) AS retail_gross_profit, ROUND(v.service_gp, 2) AS service_gross_profit,
       ROUND(s.retail_gp + v.service_gp, 2) AS total_gross_profit, o.total_opex_cad AS operating_expenses,
       ROUND(s.retail_gp + v.service_gp - o.total_opex_cad, 2) AS operating_profit
FROM operating_expenses o LEFT JOIN s USING (month) LEFT JOIN v USING (month) ORDER BY o.month;

-- name: inventory_month_end
SELECT p.product_id, p.brand, p.model, p.product_class, p.category, p.est_purchase_cost_cad,
       m.movement_date, m.movement_type, m.quantity
FROM inventory_movements m JOIN products p USING (product_id) ORDER BY m.movement_date, m.movement_id;

-- name: product_inventory_status
SELECT p.product_id, p.sku, p.brand, p.model, p.category, p.product_class, p.retail_price_cad, p.est_purchase_cost_cad,
       p.current_inventory, ROUND(p.current_inventory * p.est_purchase_cost_cad, 2) AS inventory_value_cost,
       p.reorder_point_current_policy, p.supplier_lead_time_days, p.min_order_qty, p.stockout_occurrences,
       COALESCE(so.lost_units, 0) AS lost_units, COALESCE(so.lost_revenue, 0) AS lost_revenue_est,
       COALESCE(sl.units_12m, 0) AS units_last_12m, sl.last_sale
FROM products p
LEFT JOIN (SELECT product_id, SUM(lost_units) AS lost_units, SUM(lost_revenue_est_cad) AS lost_revenue FROM stockout_events GROUP BY 1) so USING (product_id)
LEFT JOIN (SELECT product_id, SUM(CASE WHEN transaction_date >= '2025-10-01' THEN units_sold ELSE 0 END) AS units_12m, MAX(transaction_date) AS last_sale
           FROM sales_transactions WHERE return_status = 'Completed' GROUP BY 1) sl USING (product_id)
ORDER BY inventory_value_cost DESC;

-- name: stockouts_monthly
SELECT substr(e.event_date, 1, 7) || '-01' AS month, p.product_class, p.brand, SUM(e.lost_units) AS lost_units,
       ROUND(SUM(e.lost_revenue_est_cad), 2) AS lost_revenue_est, COUNT(*) AS stockout_days
FROM stockout_events e JOIN products p USING (product_id) GROUP BY 1, 2, 3 ORDER BY 1;

-- name: customer_rfm_base
SELECT c.customer_id, c.customer_type, c.geo_segment, c.acquisition_channel, c.preferred_category,
       MAX(x.last_date) AS last_activity, SUM(x.n) AS frequency, ROUND(SUM(x.spend), 2) AS monetary,
       c.bikes_bought, c.service_visits, c.test_ride_count, c.satisfaction_score, MIN(x.first_date) AS first_activity
FROM customers c JOIN (
    SELECT customer_id, MAX(transaction_date) AS last_date, MIN(transaction_date) AS first_date,
           COUNT(DISTINCT transaction_id) AS n, SUM(net_sales_cad) AS spend
    FROM sales_transactions WHERE return_status = 'Completed' AND customer_id IS NOT NULL GROUP BY 1
    UNION ALL
    SELECT customer_id, MAX(date_received), MIN(date_received), COUNT(*),
           SUM(parts_revenue_cad + CASE WHEN warranty = 1 THEN 0 ELSE labour_revenue_cad END)
    FROM service_orders GROUP BY 1) x USING (customer_id)
GROUP BY c.customer_id;

-- name: lead_funnel
SELECT lead_channel, COUNT(*) AS leads, SUM(test_ride) AS test_rides, SUM(converted) AS conversions,
       ROUND(100.0 * SUM(converted) / COUNT(*), 2) AS conversion_pct,
       ROUND(100.0 * SUM(CASE WHEN test_ride = 1 AND converted = 1 THEN 1 ELSE 0 END) / NULLIF(SUM(test_ride), 0), 2) AS conv_with_test_ride_pct,
       ROUND(100.0 * SUM(CASE WHEN test_ride = 0 AND converted = 1 THEN 1 ELSE 0 END) / NULLIF(SUM(1 - test_ride), 0), 2) AS conv_without_test_ride_pct
FROM leads WHERE lead_date <= date('2026-09-30', '-30 day') GROUP BY 1 ORDER BY leads DESC;

-- name: monthly_leads_by_channel
SELECT substr(lead_date, 1, 7) || '-01' AS month, lead_channel, COUNT(*) AS leads, SUM(converted) AS conversions
FROM leads GROUP BY 1, 2 ORDER BY 1;

-- name: marketing_spend_by_channel
SELECT marketing_channel, ROUND(SUM(spend_cad), 2) AS spend FROM marketing_spend GROUP BY 1 ORDER BY spend DESC;

-- name: sales_rep_performance
SELECT s.sales_rep_id, e.role, COUNT(DISTINCT s.transaction_id) AS transactions,
       SUM(CASE WHEN s.product_class = 'E-Bike' THEN s.units_sold ELSE 0 END) AS bikes,
       ROUND(SUM(s.net_sales_cad), 2) AS net_sales, ROUND(100.0 * SUM(s.gross_profit_cad) / SUM(s.net_sales_cad), 2) AS gross_margin_pct,
       ROUND(100.0 * AVG(CASE WHEN s.product_class = 'E-Bike' THEN s.discount_pct END), 2) AS avg_bike_discount_pct
FROM sales_transactions s JOIN staff e ON e.employee_id = s.sales_rep_id
WHERE s.return_status = 'Completed' GROUP BY 1, 2 ORDER BY net_sales DESC;

-- name: returns_summary
SELECT p.product_class, p.category, r.reason, COUNT(*) AS returns, SUM(r.qty) AS units, ROUND(SUM(r.refund_amount_cad), 2) AS refunds,
       SUM(CASE WHEN r.restocked = 0 THEN 1 ELSE 0 END) AS written_off
FROM returns r JOIN products p USING (product_id) GROUP BY 1, 2, 3 ORDER BY refunds DESC;

-- name: workshop_monthly
SELECT substr(date, 1, 7) || '-01' AS month, ROUND(SUM(capacity_hours), 1) AS capacity_hours, ROUND(SUM(assembly_hours), 1) AS assembly_hours,
       ROUND(SUM(repair_hours_received), 1) AS repair_hours, ROUND(AVG(backlog_hours_end), 1) AS avg_backlog_hours,
       ROUND(100.0 * (SUM(assembly_hours) + SUM(repair_hours_received)) / SUM(capacity_hours), 1) AS utilisation_pct
FROM workshop_daily GROUP BY 1 ORDER BY 1;
