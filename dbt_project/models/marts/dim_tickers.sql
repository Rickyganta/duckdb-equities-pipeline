with tickers as (
    select distinct
        ticker,
        min(trade_date) as first_trade_date,
        max(trade_date) as last_trade_date,
        max(extracted_at) as last_extracted_at
    from {{ ref('stg_stock_data') }}
    group by ticker
)

select
    row_number() over (order by ticker) as ticker_sk,
    ticker,
    case ticker
        when 'AAPL' then 'Apple Inc.'
        when 'MSFT' then 'Microsoft Corporation'
        when 'SPY' then 'SPDR S&P 500 ETF Trust'
        else ticker
    end as company_name,
    first_trade_date,
    last_trade_date,
    last_extracted_at
from tickers
