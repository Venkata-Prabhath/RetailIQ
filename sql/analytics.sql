-- Assumes schema initialized by src.database.postgres.initialize_schema.
-- 1. Overall KPI
SELECT SUM(sales) AS sales, SUM(profit) AS profit, COUNT(DISTINCT order_id) AS orders, SUM(profit)/NULLIF(SUM(sales),0) AS margin FROM retail_transactions;
-- 2. Monthly trend
SELECT date_trunc('month',order_date)::date AS month, SUM(sales) sales, SUM(profit) profit FROM retail_transactions GROUP BY 1 ORDER BY 1;
-- 3. Month-over-month change
WITH m AS (SELECT date_trunc('month',order_date)::date month,SUM(sales) sales,SUM(profit) profit FROM retail_transactions GROUP BY 1)
SELECT *, sales-LAG(sales) OVER(ORDER BY month) sales_change, profit-LAG(profit) OVER(ORDER BY month) profit_change FROM m ORDER BY month;
-- 4. Regional performance
SELECT region,SUM(sales) sales,SUM(profit) profit,SUM(profit)/NULLIF(SUM(sales),0) margin FROM retail_transactions GROUP BY region ORDER BY profit DESC;
-- 5. Category and subcategory profitability
SELECT category,sub_category,SUM(sales) sales,SUM(profit) profit,SUM(profit)/NULLIF(SUM(sales),0) margin FROM retail_transactions GROUP BY category,sub_category ORDER BY profit;
-- 6. Segment performance
SELECT segment,SUM(sales) sales,SUM(profit) profit,COUNT(DISTINCT order_id) orders FROM retail_transactions GROUP BY segment ORDER BY profit DESC;
-- 7. Top products by sales
SELECT product_id,product_name,SUM(sales) sales,SUM(profit) profit FROM retail_transactions GROUP BY product_id,product_name ORDER BY sales DESC LIMIT 20;
-- 8. Bottom products by profit
SELECT product_id,product_name,SUM(sales) sales,SUM(profit) profit FROM retail_transactions GROUP BY product_id,product_name ORDER BY profit LIMIT 20;
-- 9. Product groups with losses
SELECT category,sub_category,SUM(profit) profit FROM retail_transactions GROUP BY category,sub_category HAVING SUM(profit)<0 ORDER BY profit;
-- 10. Discount-band comparison
SELECT CASE WHEN discount=0 THEN '0%' WHEN discount<=.1 THEN '0-10%' WHEN discount<=.2 THEN '10-20%' WHEN discount<=.3 THEN '20-30%' ELSE '30%+' END band,SUM(sales) sales,SUM(profit) profit,SUM(profit)/NULLIF(SUM(sales),0) margin FROM retail_transactions GROUP BY 1 ORDER BY 1;
-- 11. Highest-revenue customers
SELECT customer_id,SUM(sales) revenue,SUM(profit) profit FROM retail_transactions GROUP BY customer_id ORDER BY revenue DESC LIMIT 20;
-- 12. Customers with cumulative losses
SELECT customer_id,SUM(sales) sales,SUM(profit) profit FROM retail_transactions GROUP BY customer_id HAVING SUM(profit)<0 ORDER BY profit;
-- 13. Shipping mode performance, when ship_mode exists
SELECT ship_mode,SUM(sales) sales,SUM(profit) profit,COUNT(DISTINCT order_id) orders FROM retail_transactions GROUP BY ship_mode ORDER BY profit DESC;
-- 14. Repeat customer order counts
WITH customer_orders AS (SELECT customer_id,COUNT(DISTINCT order_id) order_count FROM retail_transactions GROUP BY customer_id)
SELECT CASE WHEN order_count>1 THEN 'Repeat' ELSE 'Single order' END customer_type,COUNT(*) customers,AVG(order_count) avg_orders FROM customer_orders GROUP BY 1;
