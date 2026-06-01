with source as (
    select * from {{ source('raw', 'raw_stock_data') }}
),

cleaned as (
    select
        upper(trim(symbol)) as symbol,
        cast(date as date) as date,
        cast(open as double) as open,
        cast(high as double) as high,
        cast(low as double) as low,
        cast(close as double) as close,
        cast(volume as bigint) as volume,
        cast(extracted_at as timestamp) as extracted_at
    from source
    where symbol is not null
      and date is not null
      and open is not null
      and high is not null
      and low is not null
      and close is not null
      and volume is not null
      and open > 0
      and close > 0
)

select * from cleaned
