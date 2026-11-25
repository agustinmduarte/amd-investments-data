# AMD Investments · motor de datos

Calcula los datos del screener de AMD Investments (método de Bernardo de García) para el S&P 500, el Nasdaq 100, los CEDEARs y las acciones argentinas.

- `build.py full`: balances desde la SEC (companyfacts) o Yahoo Finance, estimaciones de analistas, noticias e info. Corre los días hábiles a las 06:00 (Buenos Aires).
- `build.py prices`: precios en USD (Yahoo), CEDEARs y acciones en pesos (data912) y CCL implícito (mediana). Corre a las 11:20 y 17:20.
- `ratios.json`: ratios de CEDEAR conocidos. `extra.txt`: tickers extra.
- Resultado en `out/`. No contiene datos personales: el portafolio vive en la cuenta de Claude.
