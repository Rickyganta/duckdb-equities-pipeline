with staged as (
    select distinct symbol
    from {{ ref('stg_stock_data') }}
)

select
    symbol as symbol_id,
    symbol,
    case symbol
        when 'AAPL' then 'Apple'
        when 'MSFT' then 'Microsoft'
        when 'SPY' then 'S&P 500 ETF'
        else symbol
    end as company_name
from staged
