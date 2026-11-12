-- 中位数涨跌幅按百分数两位入库，小数固定四位。0.11% → 0.0011。
-- 用 JSON 数字原文做 numeric 四舍五入，半分远离零，避免先变成 float8 再进位。

CREATE FUNCTION marketreview.json_percent_ratio(p_value jsonb, p_field text, p_allow_null boolean)
RETURNS double precision
LANGUAGE plpgsql
SET search_path = marketreview, pg_temp
AS $fn$
#variable_conflict use_variable
BEGIN
  IF p_value IS NULL OR jsonb_typeof(p_value) = 'null' THEN
    IF p_allow_null THEN
      RETURN NULL;
    END IF;
    PERFORM marketreview.raise_app('INVALID_TYPE', format('[INVALID_TYPE] %s 必须为数值', p_field));
  END IF;
  IF jsonb_typeof(p_value) <> 'number' THEN
    PERFORM marketreview.raise_app('INVALID_TYPE', format('[INVALID_TYPE] %s 必须为数值', p_field));
  END IF;
  RETURN round(p_value::text::numeric, 4)::double precision;
END;
$fn$;

REVOKE ALL ON FUNCTION marketreview.json_percent_ratio(jsonb, text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketreview.json_percent_ratio(jsonb, text, boolean) TO service_role;

CREATE OR REPLACE FUNCTION marketreview.patch_review_fields(p_trade_date text, p_fields jsonb)
RETURNS void
LANGUAGE plpgsql
SET search_path = marketreview, pg_temp
AS $fn$
#variable_conflict use_variable
DECLARE
  key text;
  int_fields text[] := ARRAY['advancing_count', 'declining_count', 'pullback_count'];
  float_fields text[] := ARRAY[
    'avg_stock_price', 'cy_index_close', 'cy_index_prev_close', 'float_market_cap',
    'margin_balance_bj', 'margin_balance_sh', 'margin_balance_sz',
    'pe_all', 'pe_cy', 'pe_sh', 'pe_sz', 'sh_index_close', 'sh_index_prev_close',
    'sz_index_close', 'sz_index_prev_close', 'total_market_cap',
    'turnover_amount_bj', 'turnover_amount_cy', 'turnover_amount_sh', 'turnover_amount_sz'
  ];
BEGIN
  IF p_fields IS NULL OR jsonb_typeof(p_fields) <> 'object' THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] fields 必须为对象');
  END IF;
  FOR key IN SELECT jsonb_object_keys(p_fields)
  LOOP
    IF key = ANY(int_fields) THEN
      EXECUTE format(
        'UPDATE marketreview.daily_market_review SET %I = $1 WHERE trade_date = $2',
        key
      ) USING marketreview.json_int4(p_fields -> key, key, true), p_trade_date;
    ELSIF key = 'median_change_pct' THEN
      EXECUTE format(
        'UPDATE marketreview.daily_market_review SET %I = $1 WHERE trade_date = $2',
        key
      ) USING marketreview.json_percent_ratio(p_fields -> key, key, true), p_trade_date;
    ELSIF key = ANY(float_fields) THEN
      EXECUTE format(
        'UPDATE marketreview.daily_market_review SET %I = $1 WHERE trade_date = $2',
        key
      ) USING marketreview.json_number(p_fields -> key, key, true), p_trade_date;
    ELSE
      PERFORM marketreview.raise_app('UNKNOWN_FIELD', format('[UNKNOWN_FIELD] 未知字段：%s', key));
    END IF;
  END LOOP;
END;
$fn$;

CREATE OR REPLACE FUNCTION marketreview.insert_sync_review(p_key jsonb, p_review jsonb)
RETURNS void
LANGUAGE plpgsql
SET search_path = marketreview, pg_temp
AS $fn$
#variable_conflict use_variable
DECLARE
  day text;
BEGIN
  PERFORM marketreview.assert_sync_review(p_key, p_review);
  day := p_key ->> 'trade_date';
  INSERT INTO marketreview.daily_market_review (
    trade_date, advancing_count, avg_stock_price, cy_index_close, cy_index_prev_close,
    declining_count, float_market_cap, margin_balance_bj, margin_balance_sh, margin_balance_sz,
    median_change_pct, pe_all, pe_cy, pe_sh, pe_sz, pullback_count, sh_index_close,
    sh_index_prev_close, sz_index_close, sz_index_prev_close, total_market_cap,
    turnover_amount_bj, turnover_amount_cy, turnover_amount_sh, turnover_amount_sz,
    created_at, updated_at
  ) VALUES (
    day,
    marketreview.json_int4(p_review -> 'advancing_count', 'advancing_count', true),
    marketreview.json_number(p_review -> 'avg_stock_price', 'avg_stock_price', true),
    marketreview.json_number(p_review -> 'cy_index_close', 'cy_index_close', true),
    marketreview.json_number(p_review -> 'cy_index_prev_close', 'cy_index_prev_close', true),
    marketreview.json_int4(p_review -> 'declining_count', 'declining_count', true),
    marketreview.json_number(p_review -> 'float_market_cap', 'float_market_cap', true),
    marketreview.json_number(p_review -> 'margin_balance_bj', 'margin_balance_bj', true),
    marketreview.json_number(p_review -> 'margin_balance_sh', 'margin_balance_sh', true),
    marketreview.json_number(p_review -> 'margin_balance_sz', 'margin_balance_sz', true),
    marketreview.json_percent_ratio(p_review -> 'median_change_pct', 'median_change_pct', true),
    marketreview.json_number(p_review -> 'pe_all', 'pe_all', true),
    marketreview.json_number(p_review -> 'pe_cy', 'pe_cy', true),
    marketreview.json_number(p_review -> 'pe_sh', 'pe_sh', true),
    marketreview.json_number(p_review -> 'pe_sz', 'pe_sz', true),
    marketreview.json_int4(p_review -> 'pullback_count', 'pullback_count', true),
    marketreview.json_number(p_review -> 'sh_index_close', 'sh_index_close', true),
    marketreview.json_number(p_review -> 'sh_index_prev_close', 'sh_index_prev_close', true),
    marketreview.json_number(p_review -> 'sz_index_close', 'sz_index_close', true),
    marketreview.json_number(p_review -> 'sz_index_prev_close', 'sz_index_prev_close', true),
    marketreview.json_number(p_review -> 'total_market_cap', 'total_market_cap', true),
    marketreview.json_number(p_review -> 'turnover_amount_bj', 'turnover_amount_bj', true),
    marketreview.json_number(p_review -> 'turnover_amount_cy', 'turnover_amount_cy', true),
    marketreview.json_number(p_review -> 'turnover_amount_sh', 'turnover_amount_sh', true),
    marketreview.json_number(p_review -> 'turnover_amount_sz', 'turnover_amount_sz', true),
    marketreview.require_timestamp(p_review ->> 'created_at', 'created_at'),
    marketreview.require_timestamp(p_review ->> 'updated_at', 'updated_at')
  );
END;
$fn$;
