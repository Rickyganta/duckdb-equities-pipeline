{{ config(
    materialized='incremental',
    unique_key=['symbol', 'date']
) }}

with staged as (
    select * from {{ ref('stg_stock_data') }}
),

dim as (
    select symbol_id, symbol from {{ ref('dim_tickers') }}
),

joined as (
    select
        d.symbol_id,
        s.symbol,
        s.date,
        s.open,
        s.high,
        s.low,
        s.close,
        s.volume,
        round(((s.close - s.open) / s.open) * 100.0, 4) as daily_return_percentage,
        s.extracted_at
    from staged s
    inner join dim d on s.symbol = d.symbol
),

enriched as (
    select
        *,
        round(
            avg(close) over (
                partition by symbol
                order by date
                rows between 6 preceding and current row
            ),
            4
        ) as sma_7,
        round(
            avg(close) over (
                partition by symbol
                order by date
                rows between 20 preceding and current row
            ),
            4
        ) as sma_21,
        round(
            stddev(daily_return_percentage) over (
                partition by symbol
                order by date
                rows between 29 preceding and current row
            ),
            4
        ) as rolling_volatility_30,
        case
            when volume > 2.0 * avg(volume) over (
                partition by symbol
                order by date
                rows between 29 preceding and current row
            )
            then 1
            else 0
        end as volume_anomaly_flag
    from joined
)

select * from enriched
{% if is_incremental() %}
where date > (select max(date) from {{ this }})
{% endif %}
