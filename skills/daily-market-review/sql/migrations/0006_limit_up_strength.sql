-- 涨停事件明细增加封单额、首次涨停时间、收盘价、个股流通市值四个可空列。
-- 封成比 seal_ratio 是读取派生字段（seal_amount ÷ turnover_amount），不入库。
-- 已有明细保持 NULL，不回填。

ALTER TABLE marketreview.daily_price_limit_event_detail
  ADD COLUMN IF NOT EXISTS seal_amount double precision,
  ADD COLUMN IF NOT EXISTS first_limit_time text,
  ADD COLUMN IF NOT EXISTS close_price double precision,
  ADD COLUMN IF NOT EXISTS stock_float_market_cap double precision;

CREATE OR REPLACE FUNCTION marketreview.json_limit_time(p_value jsonb, p_field text)
RETURNS text
LANGUAGE plpgsql
SET search_path = marketreview, pg_temp
AS $fn$
#variable_conflict use_variable
DECLARE
  raw text;
  parts text[];
  hour integer;
  minute integer;
  second integer;
  total integer;
BEGIN
  IF p_value IS NULL OR jsonb_typeof(p_value) = 'null' THEN
    RETURN NULL;
  END IF;
  IF jsonb_typeof(p_value) <> 'string' THEN
    PERFORM marketreview.raise_app('INVALID_TYPE', format('[INVALID_TYPE] %s 必须为字符串', p_field));
  END IF;
  raw := btrim(p_value #>> '{}');
  IF raw !~ '^[0-9]{1,2}:[0-9]{2}(:[0-9]{2})?$' THEN
    PERFORM marketreview.raise_app(
      'INVALID_REQUEST',
      format('[INVALID_REQUEST] %s 必须为 HH:MM 或 HH:MM:SS', p_field)
    );
  END IF;
  parts := string_to_array(raw, ':');
  hour := parts[1]::integer;
  minute := parts[2]::integer;
  second := CASE WHEN array_length(parts, 1) = 3 THEN parts[3]::integer ELSE 0 END;
  IF minute > 59 OR second > 59 THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', format('[INVALID_REQUEST] %s 不是有效时间', p_field));
  END IF;
  total := hour * 3600 + minute * 60 + second;
  IF total < 9 * 3600 + 25 * 60 OR total > 15 * 3600 THEN
    PERFORM marketreview.raise_app(
      'INVALID_REQUEST',
      format('[INVALID_REQUEST] %s 必须在 09:25:00 至 15:00:00', p_field)
    );
  END IF;
  RETURN format(
    '%s:%s:%s',
    lpad(hour::text, 2, '0'),
    lpad(minute::text, 2, '0'),
    lpad(second::text, 2, '0')
  );
END;
$fn$;

REVOKE ALL ON FUNCTION marketreview.json_limit_time(jsonb, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketreview.json_limit_time(jsonb, text) TO service_role;

CREATE OR REPLACE FUNCTION marketreview.json_detail_number(p_value jsonb, p_field text)
RETURNS double precision
LANGUAGE plpgsql
SET search_path = marketreview, pg_temp
AS $fn$
#variable_conflict use_variable
DECLARE
  num double precision;
BEGIN
  num := marketreview.json_number(p_value, p_field, true);
  IF num IS NULL THEN
    RETURN NULL;
  END IF;
  IF p_field IN ('previous_close', 'open_price', 'close_price', 'stock_float_market_cap') AND num <= 0 THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', format('[INVALID_REQUEST] %s 必须大于 0', p_field));
  END IF;
  IF p_field IN (
    'previous_turnover_amount', 'auction_amount', 'turnover_amount', 'turnover_rate',
    'seal_amount'
  ) AND num < 0 THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', format('[INVALID_REQUEST] %s 不能为负数', p_field));
  END IF;
  RETURN num;
END;
$fn$;

CREATE OR REPLACE FUNCTION marketreview.detail_row_json(r marketreview.daily_price_limit_event_detail)
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path = marketreview, pg_temp
AS $fn$
  SELECT jsonb_build_object(
    'trade_date', r.trade_date,
    'market', r.market,
    'code', r.code,
    'direction', r.direction,
    'previous_turnover_amount', r.previous_turnover_amount,
    'auction_amount', r.auction_amount,
    'previous_close', r.previous_close,
    'open_price', r.open_price,
    'turnover_amount', r.turnover_amount,
    'turnover_rate', r.turnover_rate,
    'seal_amount', r.seal_amount,
    'seal_ratio', CASE
      WHEN r.seal_amount IS NOT NULL AND r.turnover_amount > 0
      THEN r.seal_amount / r.turnover_amount
      ELSE NULL
    END,
    'first_limit_time', r.first_limit_time,
    'close_price', r.close_price,
    'stock_float_market_cap', r.stock_float_market_cap,
    'is_leader', marketreview.leader_json(r.is_leader),
    'note', r.note,
    'created_at', r.created_at,
    'updated_at', r.updated_at
  );
$fn$;

CREATE OR REPLACE FUNCTION marketreview.detail_scalar_json(r marketreview.daily_price_limit_event_detail)
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path = marketreview, pg_temp
AS $fn$
  SELECT jsonb_build_object(
    'previous_turnover_amount', r.previous_turnover_amount,
    'auction_amount', r.auction_amount,
    'previous_close', r.previous_close,
    'open_price', r.open_price,
    'turnover_amount', r.turnover_amount,
    'turnover_rate', r.turnover_rate,
    'seal_amount', r.seal_amount,
    'seal_ratio', CASE
      WHEN r.seal_amount IS NOT NULL AND r.turnover_amount > 0
      THEN r.seal_amount / r.turnover_amount
      ELSE NULL
    END,
    'first_limit_time', r.first_limit_time,
    'close_price', r.close_price,
    'stock_float_market_cap', r.stock_float_market_cap,
    'is_leader', marketreview.leader_json(r.is_leader),
    'note', r.note,
    'created_at', r.created_at,
    'updated_at', r.updated_at
  );
$fn$;

CREATE OR REPLACE FUNCTION marketreview.apply_detail_patch(
  p_trade_date text,
  p_patch jsonb,
  p_batch text
) RETURNS void
LANGUAGE plpgsql
SET search_path = marketreview, pg_temp
AS $fn$
#variable_conflict use_variable
DECLARE
  market text;
  code text;
  direction text;
  key text;
  allowed text[] := ARRAY[
    'market', 'code', 'direction', 'previous_turnover_amount', 'auction_amount',
    'previous_close', 'open_price', 'turnover_amount', 'turnover_rate',
    'seal_amount', 'first_limit_time', 'close_price', 'stock_float_market_cap',
    'is_leader', 'note', 'sectors', 'limit_up_reasons'
  ];
  scalar_fields text[] := ARRAY[
    'previous_turnover_amount', 'auction_amount', 'previous_close', 'open_price',
    'turnover_amount', 'turnover_rate', 'seal_amount', 'first_limit_time',
    'close_price', 'stock_float_market_cap', 'is_leader', 'note'
  ];
  number_fields text[] := ARRAY[
    'previous_turnover_amount', 'auction_amount', 'previous_close', 'open_price',
    'turnover_amount', 'turnover_rate', 'seal_amount',
    'close_price', 'stock_float_market_cap'
  ];
  sectors text[];
  reasons text[];
BEGIN
  IF p_patch IS NULL OR jsonb_typeof(p_patch) <> 'object' THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] 明细必须为对象');
  END IF;
  FOR key IN SELECT jsonb_object_keys(p_patch)
  LOOP
    IF key <> ALL(allowed) THEN
      IF key IN ('auction_ratio', 'open_change', 'seal_ratio') THEN
        PERFORM marketreview.raise_app('UNKNOWN_FIELD', format('[UNKNOWN_FIELD] %s 是读取派生字段，不能写入', key));
      END IF;
      PERFORM marketreview.raise_app('UNKNOWN_FIELD', format('[UNKNOWN_FIELD] 未知字段：%s', key));
    END IF;
  END LOOP;
  market := marketreview.require_market(marketreview.json_text(p_patch -> 'market', 'market', false));
  code := marketreview.require_code(marketreview.json_text(p_patch -> 'code', 'code', false));
  direction := marketreview.require_direction(marketreview.json_text(p_patch -> 'direction', 'direction', false));
  IF jsonb_exists(p_patch, 'limit_up_reasons') AND direction <> 'up' THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] limit_up_reasons 只允许写入 direction=up 的事件');
  END IF;
  IF jsonb_exists(p_patch, 'first_limit_time') AND direction <> 'up' THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] first_limit_time 只允许写入 direction=up 的事件');
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM marketreview.daily_price_limit_event AS event_row
    WHERE event_row.trade_date = p_trade_date
      AND event_row.market = market
      AND event_row.code = code
      AND event_row.direction = direction
  ) THEN
    PERFORM marketreview.raise_app('PARENT_EVENT_MISSING', '[PARENT_EVENT_MISSING] 父事件不存在');
  END IF;
  IF jsonb_exists_any(p_patch, scalar_fields) THEN
    INSERT INTO marketreview.daily_price_limit_event_detail (
      trade_date, market, code, direction, created_at, updated_at
    ) VALUES (p_trade_date, market, code, direction, p_batch, p_batch)
    ON CONFLICT ON CONSTRAINT daily_price_limit_event_detail_pkey DO NOTHING;
    FOREACH key IN ARRAY scalar_fields
    LOOP
      IF NOT jsonb_exists(p_patch, key) THEN
        CONTINUE;
      END IF;
      IF key = ANY(number_fields) THEN
        EXECUTE format(
          'UPDATE marketreview.daily_price_limit_event_detail
           SET %I = $1, updated_at = $2
           WHERE trade_date = $3 AND market = $4 AND code = $5 AND direction = $6',
          key
        ) USING marketreview.json_detail_number(p_patch -> key, key), p_batch,
          p_trade_date, market, code, direction;
      ELSIF key = 'first_limit_time' THEN
        UPDATE marketreview.daily_price_limit_event_detail AS detail_row
        SET first_limit_time = marketreview.json_limit_time(p_patch -> 'first_limit_time', 'first_limit_time'),
            updated_at = p_batch
        WHERE detail_row.trade_date = p_trade_date
          AND detail_row.market = market
          AND detail_row.code = code
          AND detail_row.direction = direction;
      ELSIF key = 'is_leader' THEN
        UPDATE marketreview.daily_price_limit_event_detail AS detail_row
        SET is_leader = marketreview.bool_to_smallint(
              marketreview.json_bool(p_patch -> 'is_leader', 'is_leader', true)
            ),
            updated_at = p_batch
        WHERE detail_row.trade_date = p_trade_date
          AND detail_row.market = market
          AND detail_row.code = code
          AND detail_row.direction = direction;
      ELSE
        UPDATE marketreview.daily_price_limit_event_detail AS detail_row
        SET note = NULLIF(btrim(marketreview.json_text(p_patch -> 'note', 'note', true)), ''),
            updated_at = p_batch
        WHERE detail_row.trade_date = p_trade_date
          AND detail_row.market = market
          AND detail_row.code = code
          AND detail_row.direction = direction;
      END IF;
    END LOOP;
  END IF;
  IF jsonb_exists(p_patch, 'sectors') THEN
    sectors := marketreview.json_string_list(p_patch -> 'sectors', 'sectors');
    PERFORM marketreview.replace_text_list(
      'daily_price_limit_event_sector', p_trade_date, market, code, direction, sectors
    );
  END IF;
  IF jsonb_exists(p_patch, 'limit_up_reasons') THEN
    reasons := marketreview.json_string_list(p_patch -> 'limit_up_reasons', 'limit_up_reasons');
    PERFORM marketreview.replace_text_list(
      'daily_price_limit_event_reason', p_trade_date, market, code, direction, reasons
    );
  END IF;
END;
$fn$;

CREATE OR REPLACE FUNCTION marketreview.replace_direction(p_request jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = marketreview, pg_temp
AS $fn$
#variable_conflict use_variable
DECLARE
  day text;
  batch text;
  market text;
  code text;
  old_direction text;
  event_body jsonb;
  new_direction text;
  detail_row marketreview.daily_price_limit_event_detail%ROWTYPE;
  detail_exists boolean;
  sectors text[];
  reasons text[];
  new_revision bigint;
BEGIN
  PERFORM marketreview.assert_schema(p_request);
  day := marketreview.require_request_trade_date(p_request);
  batch := marketreview.require_batch_time(p_request);
  market := marketreview.require_market(marketreview.json_text(p_request -> 'market', 'market', false));
  code := marketreview.require_code(marketreview.json_text(p_request -> 'code', 'code', false));
  old_direction := marketreview.require_direction(
    marketreview.json_text(p_request -> 'old_direction', 'old_direction', false)
  );
  event_body := marketreview.parse_event_body(p_request -> 'event');
  IF (event_body ->> 'market') <> market OR (event_body ->> 'code') <> code THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] 替换事件的 market/code 必须与目标一致');
  END IF;
  new_direction := event_body ->> 'direction';
  IF new_direction = old_direction THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] 方向未变化');
  END IF;
  PERFORM marketreview.lock_ledger();
  IF NOT EXISTS (
    SELECT 1 FROM marketreview.daily_price_limit_event AS event_row
    WHERE event_row.trade_date = day
      AND event_row.market = market
      AND event_row.code = code
      AND event_row.direction = old_direction
  ) THEN
    PERFORM marketreview.raise_app('REPLACE_SOURCE_MISSING', '[REPLACE_SOURCE_MISSING] 被替换事件不存在');
  END IF;
  IF EXISTS (
    SELECT 1 FROM marketreview.daily_price_limit_event AS event_row
    WHERE event_row.trade_date = day
      AND event_row.market = market
      AND event_row.code = code
      AND event_row.direction = new_direction
  ) THEN
    PERFORM marketreview.raise_app('REPLACE_TARGET_EXISTS', '[REPLACE_TARGET_EXISTS] 目标方向已存在');
  END IF;
  SELECT * INTO detail_row
  FROM marketreview.daily_price_limit_event_detail AS detail_src
  WHERE detail_src.trade_date = day
    AND detail_src.market = market
    AND detail_src.code = code
    AND detail_src.direction = old_direction;
  detail_exists := FOUND;
  SELECT COALESCE(array_agg(sector_row.value ORDER BY sector_row.position), ARRAY[]::text[])
  INTO sectors
  FROM marketreview.daily_price_limit_event_sector AS sector_row
  WHERE sector_row.trade_date = day
    AND sector_row.market = market
    AND sector_row.code = code
    AND sector_row.direction = old_direction;
  SELECT COALESCE(array_agg(reason_row.value ORDER BY reason_row.position), ARRAY[]::text[])
  INTO reasons
  FROM marketreview.daily_price_limit_event_reason AS reason_row
  WHERE reason_row.trade_date = day
    AND reason_row.market = market
    AND reason_row.code = code
    AND reason_row.direction = old_direction;
  DELETE FROM marketreview.daily_price_limit_event AS event_row
  WHERE event_row.trade_date = day
    AND event_row.market = market
    AND event_row.code = code
    AND event_row.direction = old_direction;
  INSERT INTO marketreview.daily_price_limit_event (
    trade_date, market, code, name, direction, closed_at_limit, limit_rate_bp, streak_height,
    created_at, updated_at
  ) VALUES (
    day, market, code, event_body ->> 'name', new_direction,
    (event_body ->> 'closed_at_limit')::integer,
    (event_body ->> 'limit_rate_bp')::integer,
    (event_body ->> 'streak_height')::integer,
    batch, batch
  );
  IF detail_exists THEN
    INSERT INTO marketreview.daily_price_limit_event_detail (
      trade_date, market, code, direction,
      previous_turnover_amount, auction_amount, previous_close, open_price,
      turnover_amount, turnover_rate, seal_amount, first_limit_time,
      close_price, stock_float_market_cap, is_leader, note, created_at, updated_at
    ) VALUES (
      day, market, code, new_direction,
      detail_row.previous_turnover_amount, detail_row.auction_amount, detail_row.previous_close,
      detail_row.open_price, detail_row.turnover_amount, detail_row.turnover_rate,
      detail_row.seal_amount,
      CASE WHEN new_direction = 'up' THEN detail_row.first_limit_time ELSE NULL END,
      detail_row.close_price, detail_row.stock_float_market_cap,
      detail_row.is_leader, detail_row.note, batch, batch
    );
  END IF;
  PERFORM marketreview.replace_text_list(
    'daily_price_limit_event_sector', day, market, code, new_direction, sectors
  );
  IF new_direction = 'up' THEN
    PERFORM marketreview.replace_text_list(
      'daily_price_limit_event_reason', day, market, code, new_direction, reasons
    );
  END IF;
  new_revision := marketreview.bump_revision();
  PERFORM marketreview.insert_history(
    'event',
    jsonb_build_object('trade_date', day, 'market', market, 'code', code),
    new_revision,
    'direction_replace',
    true,
    true,
    NULL
  );
  RETURN marketreview.write_result(new_revision, false);
END;
$fn$;

CREATE OR REPLACE FUNCTION marketreview.insert_sync_direction(
  p_trade_date text,
  p_market text,
  p_code text,
  p_event jsonb
) RETURNS void
LANGUAGE plpgsql
SET search_path = marketreview, pg_temp
AS $fn$
#variable_conflict use_variable
DECLARE
  direction text;
  detail_exists boolean;
  detail jsonb;
  key text;
  allowed_event text[] := ARRAY[
    'direction', 'name', 'closed_at_limit', 'limit_rate_bp', 'streak_height',
    'created_at', 'updated_at', 'detail_exists', 'detail', 'sectors', 'limit_up_reasons'
  ];
  detail_keys text[] := ARRAY[
    'previous_turnover_amount', 'auction_amount', 'previous_close', 'open_price',
    'turnover_amount', 'turnover_rate', 'seal_amount', 'first_limit_time',
    'close_price', 'stock_float_market_cap', 'is_leader', 'note', 'created_at', 'updated_at'
  ];
  sectors text[];
  reasons text[];
BEGIN
  IF p_event IS NULL OR jsonb_typeof(p_event) IS DISTINCT FROM 'object' THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] 同步事件必须为对象');
  END IF;
  FOR key IN SELECT jsonb_object_keys(p_event)
  LOOP
    IF key <> ALL(allowed_event) THEN
      PERFORM marketreview.raise_app('UNKNOWN_FIELD', format('[UNKNOWN_FIELD] 未知字段：%s', key));
    END IF;
  END LOOP;
  IF NOT jsonb_exists_all(p_event, allowed_event) THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] 同步事件缺少字段');
  END IF;
  direction := marketreview.require_direction(marketreview.json_text(p_event -> 'direction', 'direction', false));
  IF jsonb_typeof(p_event -> 'detail_exists') IS DISTINCT FROM 'boolean' THEN
    PERFORM marketreview.raise_app('INVALID_TYPE', '[INVALID_TYPE] detail_exists 必须为布尔值');
  END IF;
  detail_exists := p_event -> 'detail_exists' = 'true'::jsonb;
  sectors := marketreview.json_string_list(p_event -> 'sectors', 'sectors');
  reasons := marketreview.json_string_list(p_event -> 'limit_up_reasons', 'limit_up_reasons');
  IF direction = 'down' AND coalesce(array_length(reasons, 1), 0) > 0 THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] down 方向不能带涨停原因');
  END IF;
  IF detail_exists THEN
    detail := p_event -> 'detail';
    IF detail IS NULL OR jsonb_typeof(detail) <> 'object' THEN
      PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] detail_exists 为真时必须提供明细对象');
    END IF;
    FOR key IN SELECT jsonb_object_keys(detail)
    LOOP
      IF key <> ALL(detail_keys) THEN
        PERFORM marketreview.raise_app('UNKNOWN_FIELD', format('[UNKNOWN_FIELD] 未知明细字段：%s', key));
      END IF;
    END LOOP;
    IF NOT jsonb_exists_all(detail, detail_keys) THEN
      PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] 同步明细缺少字段');
    END IF;
    IF direction = 'down' AND jsonb_typeof(detail -> 'first_limit_time') IS DISTINCT FROM 'null' THEN
      PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] down 方向不能带首次涨停时间');
    END IF;
    PERFORM marketreview.json_limit_time(detail -> 'first_limit_time', 'first_limit_time');
    PERFORM marketreview.json_detail_number(detail -> 'seal_amount', 'seal_amount');
    PERFORM marketreview.json_detail_number(detail -> 'close_price', 'close_price');
    PERFORM marketreview.json_detail_number(detail -> 'stock_float_market_cap', 'stock_float_market_cap');
  ELSIF jsonb_typeof(p_event -> 'detail') IS DISTINCT FROM 'null' THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] 无明细行时 detail 必须为 null');
  END IF;
  INSERT INTO marketreview.daily_price_limit_event (
    trade_date, market, code, name, direction, closed_at_limit, limit_rate_bp, streak_height,
    created_at, updated_at
  ) VALUES (
    p_trade_date,
    p_market,
    p_code,
    marketreview.json_text(p_event -> 'name', 'name', false),
    direction,
    marketreview.bool_to_smallint(marketreview.json_bool(p_event -> 'closed_at_limit', 'closed_at_limit', false)),
    marketreview.limit_rate(p_event -> 'limit_rate_bp'),
    marketreview.streak_height(p_event -> 'streak_height'),
    marketreview.require_timestamp(p_event ->> 'created_at', 'created_at'),
    marketreview.require_timestamp(p_event ->> 'updated_at', 'updated_at')
  );
  IF detail_exists THEN
    INSERT INTO marketreview.daily_price_limit_event_detail (
      trade_date, market, code, direction,
      previous_turnover_amount, auction_amount, previous_close, open_price,
      turnover_amount, turnover_rate, seal_amount, first_limit_time,
      close_price, stock_float_market_cap, is_leader, note, created_at, updated_at
    ) VALUES (
      p_trade_date, p_market, p_code, direction,
      marketreview.json_detail_number(detail -> 'previous_turnover_amount', 'previous_turnover_amount'),
      marketreview.json_detail_number(detail -> 'auction_amount', 'auction_amount'),
      marketreview.json_detail_number(detail -> 'previous_close', 'previous_close'),
      marketreview.json_detail_number(detail -> 'open_price', 'open_price'),
      marketreview.json_detail_number(detail -> 'turnover_amount', 'turnover_amount'),
      marketreview.json_detail_number(detail -> 'turnover_rate', 'turnover_rate'),
      marketreview.json_detail_number(detail -> 'seal_amount', 'seal_amount'),
      marketreview.json_limit_time(detail -> 'first_limit_time', 'first_limit_time'),
      marketreview.json_detail_number(detail -> 'close_price', 'close_price'),
      marketreview.json_detail_number(detail -> 'stock_float_market_cap', 'stock_float_market_cap'),
      marketreview.bool_to_smallint(marketreview.json_bool(detail -> 'is_leader', 'is_leader', true)),
      NULLIF(btrim(marketreview.json_text(detail -> 'note', 'note', true)), ''),
      marketreview.require_timestamp(detail ->> 'created_at', 'created_at'),
      marketreview.require_timestamp(detail ->> 'updated_at', 'updated_at')
    );
  END IF;
  PERFORM marketreview.replace_text_list(
    'daily_price_limit_event_sector', p_trade_date, p_market, p_code, direction, sectors
  );
  PERFORM marketreview.replace_text_list(
    'daily_price_limit_event_reason', p_trade_date, p_market, p_code, direction, reasons
  );
END;
$fn$;

CREATE OR REPLACE FUNCTION marketreview.assert_sync_direction(p_event jsonb)
RETURNS void
LANGUAGE plpgsql
SET search_path = marketreview, pg_temp
AS $fn$
#variable_conflict use_variable
DECLARE
  direction text;
  detail_exists boolean;
  detail jsonb;
  key text;
  allowed_event text[] := ARRAY[
    'direction', 'name', 'closed_at_limit', 'limit_rate_bp', 'streak_height',
    'created_at', 'updated_at', 'detail_exists', 'detail', 'sectors', 'limit_up_reasons'
  ];
  detail_keys text[] := ARRAY[
    'previous_turnover_amount', 'auction_amount', 'previous_close', 'open_price',
    'turnover_amount', 'turnover_rate', 'seal_amount', 'first_limit_time',
    'close_price', 'stock_float_market_cap', 'is_leader', 'note', 'created_at', 'updated_at'
  ];
  reasons text[];
BEGIN
  IF p_event IS NULL OR jsonb_typeof(p_event) IS DISTINCT FROM 'object' THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] 同步事件必须为对象');
  END IF;
  FOR key IN SELECT jsonb_object_keys(p_event)
  LOOP
    IF key <> ALL(allowed_event) THEN
      PERFORM marketreview.raise_app('UNKNOWN_FIELD', format('[UNKNOWN_FIELD] 未知字段：%s', key));
    END IF;
  END LOOP;
  IF NOT jsonb_exists_all(p_event, allowed_event) THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] 同步事件缺少字段');
  END IF;
  direction := marketreview.require_direction(marketreview.json_text(p_event -> 'direction', 'direction', false));
  IF jsonb_typeof(p_event -> 'detail_exists') IS DISTINCT FROM 'boolean' THEN
    PERFORM marketreview.raise_app('INVALID_TYPE', '[INVALID_TYPE] detail_exists 必须为布尔值');
  END IF;
  detail_exists := p_event -> 'detail_exists' = 'true'::jsonb;
  PERFORM marketreview.json_string_list(p_event -> 'sectors', 'sectors');
  reasons := marketreview.json_string_list(p_event -> 'limit_up_reasons', 'limit_up_reasons');
  IF direction = 'down' AND coalesce(array_length(reasons, 1), 0) > 0 THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] down 方向不能带涨停原因');
  END IF;
  IF detail_exists THEN
    detail := p_event -> 'detail';
    IF detail IS NULL OR jsonb_typeof(detail) IS DISTINCT FROM 'object' THEN
      PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] detail_exists 为真时必须提供明细对象');
    END IF;
    FOR key IN SELECT jsonb_object_keys(detail)
    LOOP
      IF key <> ALL(detail_keys) THEN
        PERFORM marketreview.raise_app('UNKNOWN_FIELD', format('[UNKNOWN_FIELD] 未知明细字段：%s', key));
      END IF;
    END LOOP;
    IF NOT jsonb_exists_all(detail, detail_keys) THEN
      PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] 同步明细缺少字段');
    END IF;
    IF direction = 'down' AND jsonb_typeof(detail -> 'first_limit_time') IS DISTINCT FROM 'null' THEN
      PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] down 方向不能带首次涨停时间');
    END IF;
    PERFORM marketreview.json_limit_time(detail -> 'first_limit_time', 'first_limit_time');
    PERFORM marketreview.json_detail_number(detail -> 'seal_amount', 'seal_amount');
    PERFORM marketreview.json_detail_number(detail -> 'close_price', 'close_price');
    PERFORM marketreview.json_detail_number(detail -> 'stock_float_market_cap', 'stock_float_market_cap');
  ELSIF jsonb_typeof(p_event -> 'detail') IS DISTINCT FROM 'null' THEN
    PERFORM marketreview.raise_app('INVALID_REQUEST', '[INVALID_REQUEST] 无明细行时 detail 必须为 null');
  END IF;
  PERFORM marketreview.json_text(p_event -> 'name', 'name', false);
  PERFORM marketreview.json_bool(p_event -> 'closed_at_limit', 'closed_at_limit', false);
  PERFORM marketreview.limit_rate(p_event -> 'limit_rate_bp');
  PERFORM marketreview.streak_height(p_event -> 'streak_height');
  PERFORM marketreview.require_timestamp(p_event ->> 'created_at', 'created_at');
  PERFORM marketreview.require_timestamp(p_event ->> 'updated_at', 'updated_at');
END;
$fn$;
