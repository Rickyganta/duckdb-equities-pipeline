with staged as (
    select * from {{ ref('stg_stock_data') }}
),

dim as (
    select ticker_sk, ticker from {{ ref('dim_tickers') }}
),

joined as (
    select
        d.ticker_sk,
        s.ticker,
        s.trade_date,
        s.open_price,
        s.high_price,
        s.low_price,
        s.close_price,
        s.volume,
        s.dividends,
        s.stock_splits,
        s.close_price - lag(s.close_price) over (
            partition by s.ticker
            order by s.trade_date
        ) as daily_price_change,
        case
            when lag(s.close_price) over (
                partition by s.ticker
                order by s.trade_date
            ) is null
            or lag(s.close_price) over (
                partition by s.ticker
                order by s.trade_date
            ) = 0
            then null
            else round(
                100.0 * (
                    s.close_price - lag(s.close_price) over (
                        partition by s.ticker
                        order by s.trade_date
                    )
                ) / lag(s.close_price) over (
                    partition by s.ticker
                    order by s.trade_date
                ),
                4
            )
        end as daily_return_pct,
        s.extracted_at
    from staged s
    inner join dim d on s.ticker = d.ticker
)

select * from joined
