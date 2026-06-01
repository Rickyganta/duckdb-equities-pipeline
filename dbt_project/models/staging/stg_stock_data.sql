with source as (
    select * from {{ source('raw', 'raw_stock_data') }}
),

cleaned as (
    select
        upper(trim(ticker)) as ticker,
        cast(date as date) as trade_date,
        cast(open as double) as open_price,
        cast(high as double) as high_price,
        cast(low as double) as low_price,
        cast(close as double) as close_price,
        cast(volume as bigint) as volume,
        coalesce(cast(dividends as double), 0.0) as dividends,
        coalesce(cast(stock_splits as double), 0.0) as stock_splits,
        cast(extracted_at as timestamp) as extracted_at
    from source
    where ticker is not null
      and date is not null
      and close is not null
)

select * from cleaned
