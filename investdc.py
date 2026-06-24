import os
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


from urllib.parse import urlencode

DISCORD_CLIENT_ID = st.secrets["DISCORD_CLIENT_ID"]
DISCORD_CLIENT_SECRET = st.secrets["DISCORD_CLIENT_SECRET"]
DISCORD_REDIRECT_URI = st.secrets["DISCORD_REDIRECT_URI"]
DISCORD_GUILD_ID = st.secrets["DISCORD_GUILD_ID"]
DISCORD_PREMIUM_ROLE_ID = st.secrets["DISCORD_PREMIUM_ROLE_ID"]
DISCORD_ADMIN_ROLE_ID = st.secrets.get("DISCORD_ADMIN_ROLE_ID")

def discord_login_url():
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds.members.read"
    }
    return "https://discord.com/oauth2/authorize?" + urlencode(params)

def get_discord_token(code):
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI
    }

    r = requests.post(
        "https://discord.com/api/oauth2/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    if r.status_code != 200:
        st.error("Discord login neizdevās.")
        st.write(r.text)
        st.stop()

    return r.json()["access_token"]

def get_discord_roles(access_token):
    r = requests.get(
        f"https://discord.com/api/users/@me/guilds/{DISCORD_GUILD_ID}/member",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    if r.status_code != 200:
        return []

    return r.json().get("roles", [])

def require_premium():
    code = st.query_params.get("code")

    if "discord_roles" not in st.session_state:
        if not code:
            st.title("Gabors Investment Bot")
            st.warning("Pieeja tikai Premium lietotājiem.")
            st.link_button("Login with Discord", discord_login_url())
            st.stop()

        token = get_discord_token(code)
        roles = get_discord_roles(token)

        st.session_state["discord_token"] = token
        st.session_state["discord_roles"] = roles

        st.query_params.clear()

    roles = st.session_state.get("discord_roles", [])

    ALLOWED_ROLE_IDS = [DISCORD_PREMIUM_ROLE_ID]

    if DISCORD_ADMIN_ROLE_ID:
        ALLOWED_ROLE_IDS.append(DISCORD_ADMIN_ROLE_ID)

    if not any(str(role) in [str(r) for r in ALLOWED_ROLE_IDS] for role in roles):
        st.error("Pieeja liegta. Šis bots ir tikai Premium lietotājiem.")
        st.stop()

require_premium()

st.title("Investīciju analīzes bots")


def to_float(value):
    try:
        if isinstance(value, pd.Series):
            value = value.dropna()
            if value.empty:
                return None
            value = value.iloc[0]

        if pd.isna(value):
            return None

        return float(value)

    except Exception:
        return None

def ai_future_view(name, sector, industry, summary, pe, revenue_growth, earnings_growth, price):
    prompt = f"""
Izanalizē šo investīciju un atbildi TIKAI šādā formātā:

Skats tuvākajos mēnešos:
...

Skats 1 gada laikā:
...

Skats 3-5 gadu laikā:
...

Skats līdz 10 gadiem:
...

Galvenie riski:
...

Konkurenti:
...

Uzņēmums: {name}
Sektors: {sector}
Nozare: {industry}
Cena: {price}
P/E: {pe}
Ieņēmumu pieaugums: {revenue_growth}
Peļņas pieaugums: {earnings_growth}

Apraksts:
{summary}

Raksti latviešu valodā. Raksti īsi.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500
    )

    return response.choices[0].message.content

def ai_justetf_info(etf_name, symbol):
    query = f"{etf_name} {symbol} justETF TER top holdings sectors countries dividends"

    prompt = f"""
Atrodi un apkopo ETF informāciju par: {query}

Atbildi TIKAI šādā formātā latviešu valodā:

TER:

Top holdings:

Top sektori:

Top valstis:

Dividendes / Acc vai Dist:

Neraksti neko lieku.
Ja kādu datu nav, raksti: Nav datu. Pie holdings, sektori un valstis raksti prioritārā secībā, kam lielāka ietekme, to pirmo.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250
    )

    return response.choices[0].message.content

def analyze_symbol(symbol, asset_type):
    symbol = symbol.upper()

    if asset_type == "Indekss":
        index_map = {
            "NQ": "^NDX",
            "NDX": "^NDX",
            "NASDAQ": "^IXIC",
            "SPX": "^GSPC",
            "SP500": "^GSPC",
            "S&P500": "^GSPC",
            "DJI": "^DJI",
            "DOW": "^DJI",
            "DAX": "^GDAXI",
            "FTSE": "^FTSE"
        }
        symbol = index_map.get(symbol, symbol)

    if asset_type == "ETF":
        etf_map = {
            "EQQQ": "EQQQ.L",
            "VWCE": "VWCE.DE",
            "VUAA": "VUAA.L",
            "VUSA": "VUSA.L",
            "SXR8": "SXR8.DE",
            "IWDA": "IWDA.AS",
            "CSPX": "CSPX.L",
            "QQQ": "QQQ",
            "SPY": "SPY",
            "VOO": "VOO"
        }
        symbol = etf_map.get(symbol, symbol)

    # Automātiska ETF biržas meklēšana
    if asset_type == "ETF" and "." not in symbol:

        exchanges = [".L", ".DE", ".AS", ".PA", ".SW"]

        for suffix in exchanges:
            test_symbol = symbol + suffix

            try:
                test_data = yf.download(
                    test_symbol,
                    period="5d",
                    progress=False,
                    auto_adjust=True
                )

                if not test_data.empty:
                    symbol = test_symbol
                    break

            except:
                pass

    st.write(f"Lejupielādēju datus: {symbol}")

    data = yf.download(symbol, period="7y", interval="1d", auto_adjust=True)

    if data.empty:
        st.error("Dati netika atrasti. Pārbaudi simbolu.")
        return

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # Londonas ETF: Yahoo rāda GBX, pārvēršam uz EUR
    if asset_type == "ETF" and symbol.endswith(".L"):

        gbp_to_eur = 1.16

        for col in ["Open", "High", "Low", "Close"]:
            if col in data.columns:
                data[col] = data[col] / 100 * gbp_to_eur

    ticker = yf.Ticker(symbol)
    info = ticker.info

    name = info.get("longName", symbol)
    sector = info.get("sector", "Nav datu")
    industry = info.get("industry", "Nav datu")
    summary = info.get("longBusinessSummary", "Nav apraksta.")
    market_cap = info.get("marketCap", None)
    pe = info.get("trailingPE", None)
    forward_pe = info.get("forwardPE", None)
    revenue_growth = info.get("revenueGrowth", None)
    earnings_growth = info.get("earningsGrowth", None)
    profit_margin = info.get("profitMargins", None)
    target_mean = info.get("targetMeanPrice", None)
    recommendation = info.get("recommendationKey", "Nav datu")

    data["SMA20"] = data["Close"].rolling(20).mean()
    data["SMA50"] = data["Close"].rolling(50).mean()
    data["SMA200"] = data["Close"].rolling(200).mean()

    data["Daily_Return"] = data["Close"].pct_change()
    data["Volatility_30d"] = data["Daily_Return"].rolling(30).std() * 100
    data["High_52w"] = data["Close"].rolling(252).max()
    data["Low_52w"] = data["Close"].rolling(252).min()

    price = to_float(data["Close"].iloc[-1])
    sma20 = to_float(data["SMA20"].iloc[-1])
    sma50 = to_float(data["SMA50"].iloc[-1])
    sma200 = to_float(data["SMA200"].iloc[-1])
    high_52w = to_float(data["High_52w"].iloc[-1])
    low_52w = to_float(data["Low_52w"].iloc[-1])
    volatility = to_float(data["Volatility_30d"].iloc[-1])


    if None in [price, sma20, sma50, sma200, high_52w, low_52w]:
        st.error("Nepietiek datu analīzei.")
        return

    def return_period(days):
        if len(data) > days:
            old_price = to_float(data["Close"].iloc[-days])
            return ((price - old_price) / old_price) * 100
        return None

    ret_1m = return_period(21)
    ret_3m = return_period(63)
    ret_6m = return_period(126)
    ret_1y = return_period(252)
    ret_3y = return_period(756)
    ret_5y = return_period(1260)

    distance_from_high = ((high_52w - price) / high_52w) * 100
    distance_from_low = ((price - low_52w) / low_52w) * 100
    distance_from_sma200 = ((price - sma200) / sma200) * 100

    data["Peak"] = data["Close"].cummax()
    data["Drawdown"] = (data["Close"] - data["Peak"]) / data["Peak"] * 100
    max_drawdown = to_float(data["Drawdown"].min())

    recent_high = high_52w

    pullback_from_high = ((recent_high - price) / recent_high) * 100

    pullback_5 = recent_high * 0.95
    pullback_10 = recent_high * 0.90
    pullback_15 = recent_high * 0.85

    realistic_entry = pullback_5
    good_entry = pullback_10
    deep_entry = pullback_15

    drop_to_realistic = ((price - realistic_entry) / price) * 100
    drop_to_good = ((price - good_entry) / price) * 100
    drop_to_deep = ((price - deep_entry) / price) * 100

    score = 50

    if price > sma200:
        score += 10
    else:
        score -= 20

    if sma20 > sma50:
        score += 8
    else:
        score -= 8

    if sma50 > sma200:
        score += 8
    else:
        score -= 8

    if distance_from_sma200 > 50:
        score -= 20
    elif distance_from_sma200 > 30:
        score -= 12
    elif distance_from_sma200 > 15:
        score -= 5
    elif -10 <= distance_from_sma200 <= 15:
        score += 10

    if distance_from_high < 3:
        score -= 10
    elif distance_from_high < 10:
        score -= 5
    elif 10 <= distance_from_high <= 25:
        score += 8

    if volatility is not None:
        if volatility > 5:
            score -= 15
        elif volatility > 3:
            score -= 7
        else:
            score += 5

    if max_drawdown < -60:
        score -= 15
    elif max_drawdown < -40:
        score -= 8

    if revenue_growth is not None:
        if revenue_growth > 0.20:
            score += 10
        elif revenue_growth > 0:
            score += 5
        else:
            score -= 10

    if profit_margin is not None:
        if profit_margin > 0.20:
            score += 8
        elif profit_margin < 0:
            score -= 15

    if pe is not None:
        if pe > 80:
            score -= 15
        elif pe > 50:
            score -= 8
        elif pe < 30:
            score += 5

    score = max(0, min(100, round(score)))

    if price > sma20 > sma50 > sma200:
        trend = "Ļoti spēcīgs bullish trends"
    elif price > sma50 and price > sma200:
        trend = "Pozitīvs trends"
    elif price < sma200:
        trend = "Negatīvs / vājš trends"
    else:
        trend = "Neitrāls trends"

    if (volatility is not None and volatility > 5) or max_drawdown < -60:
        risk = "Augsts"
    elif volatility is not None and volatility > 3:
        risk = "Vidējs"
    else:
        risk = "Zems / vidējs"

    if price < sma200:
        entry = "Cena ir zem ilgtermiņa trenda. Tā var būt lēta, bet risks ir lielāks, jo kritums var turpināties."
        approach = "Ja uzņēmums vai aktīvs ir kvalitatīvs, labāk izmantot DCA, nevis gaidīt perfektu dibenu."

    elif distance_from_high < 5:
        entry = "Cena ir ļoti tuvu 52 nedēļu maksimumam. Trends ir spēcīgs, bet ieeja nav lēta."
        approach = "Var pirkt pa daļām, bet labāk neatvērt visu pozīciju uzreiz."

    elif distance_from_sma200 > 35:
        entry = "Cena ir ļoti tālu virs SMA200. Aktīvs ir spēcīgs, bet korekcijas risks ir palielināts."
        approach = "Labāk pirkt pa daļām vai gaidīt vismaz nelielu korekciju."

    else:
        entry = "Cena nav ekstrēmi pārkarsusi un trends izskatās normāls."
        approach = "Var apsvērt pakāpenisku pozīcijas veidošanu."

    if score >= 75:
        potential = "Augsts"
    elif score >= 55:
        potential = "Vidējs / labs"
    else:
        potential = "Vājš vai neskaidrs"

    st.subheader("Pamatdati")
    st.write(f"**Nosaukums:** {name}")
    st.write(f"**Simbols:** {symbol}")
    st.write(f"**Pašreizējā cena:** {price:.2f}")
    st.write(f"**SMA20:** {sma20:.2f}")
    st.write(f"**SMA50:** {sma50:.2f}")
    st.write(f"**SMA200:** {sma200:.2f}")
    st.write(f"**52w maksimums:** {high_52w:.2f}")
    st.write(f"**52w minimums:** {low_52w:.2f}")
    st.write(f"**Cena zem 52w maksimuma:** {distance_from_high:.2f}%")
    st.write(f"**Cena virs 52w minimuma:** {distance_from_low:.2f}%")
    st.write(f"**Attālums no SMA200:** {distance_from_sma200:.2f}%")
    st.write(f"**Lielākais kritums 7 gados:** {max_drawdown:.2f}%")

    if asset_type == "ETF":
        st.subheader("ETF info")

        try:
            etf_ai_info = ai_justetf_info(name, symbol)
            st.write(etf_ai_info)
        except Exception as e:
            st.error("ETF informāciju neizdevās iegūt.")
            st.write(e)

    st.subheader("Ienesīgums")
    if ret_1m is not None:
        st.write(f"1 mēnesis: {ret_1m:.2f}%")
    if ret_3m is not None:
        st.write(f"3 mēneši: {ret_3m:.2f}%")
    if ret_6m is not None:
        st.write(f"6 mēneši: {ret_6m:.2f}%")
    if ret_1y is not None:
        st.write(f"1 gads: {ret_1y:.2f}%")
    if ret_3y is not None:
        st.write(f"3 gadi: {ret_3y:.2f}%")
    if ret_5y is not None:
        st.write(f"5 gadi: {ret_5y:.2f}%")

    st.subheader("Ieejas punkts")

    st.write(f"**Pašreizējā cena:** {price:.2f}")

    st.write(f"**Agresīva ieeja tagad:** {price:.2f}")
    st.write(f"**Reālistiska korekcijas zona:** {realistic_entry:.2f} ({drop_to_realistic:.1f}% zem pašreizējās cenas)")
    st.write(f"**Labāka ieejas zona:** {good_entry:.2f} ({drop_to_good:.1f}% zem pašreizējās cenas)")
    st.write(f"**Dziļa korekcija / ļoti lēta zona:** {deep_entry:.2f} ({drop_to_deep:.1f}% zem pašreizējās cenas)")

    if pullback_from_high >= 15:
        st.success(
            "Cena jau ir dziļā korekcijā. Ieeja var būt pievilcīga, ja uzņēmums joprojām ir kvalitatīvs."
        )

    elif pullback_from_high >= 10:
        st.success(
            "Cena jau ir labā korekcijas zonā."
        )

    elif pullback_from_high >= 5:
        st.info(
            "Cena jau ir nelielā korekcijā."
        )

    else:
        st.warning(
            "Cena joprojām ir ļoti tuvu maksimumiem."
        )

    st.subheader("Pirkšanas pieeja")
    st.write(approach)

    st.subheader("Varbūtība sasniegt dziļo korekcijas līmeni")

    if drop_to_deep > 18:
        st.error("Zema varbūtība tuvākajā laikā. Šis līmenis ir ļoti tālu no pašreizējās cenas.")
    elif drop_to_deep > 13:
        st.warning("Vidēja varbūtība. Šāds līmenis iespējams tikai pie lielākas korekcijas.")
    else:
        st.success("Augstāka varbūtība. Šis līmenis nav ļoti tālu no pašreizējās cenas.")

    st.warning(entry)

    st.subheader("Secinājums")
    st.write(f"**Kopējais vērtējums:** {score}/100")
    st.write(f"**Trends:** {trend}")
    st.write(f"**Risks:** {risk}")
    st.write(f"**Potenciāls:** {potential}")
    st.write(f"**Ieejas punkts:** {entry}")
    st.write(f"**Labākā pieeja:** {approach}")

    st.subheader("Uzņēmuma / aktīva info")
    st.write(f"**Sektors:** {sector}")
    st.write(f"**Nozare:** {industry}")

    if market_cap:
        st.write(f"**Tirgus kapitalizācija:** {market_cap / 1_000_000_000:.2f} miljardi")
    if pe:
        st.write(f"**P/E:** {pe:.2f}")
    if forward_pe:
        st.write(f"**Forward P/E:** {forward_pe:.2f}")
    if revenue_growth is not None:
        st.write(f"**Ieņēmumu pieaugums:** {revenue_growth * 100:.2f}%")
    if earnings_growth is not None:
        st.write(f"**Peļņas pieaugums:** {earnings_growth * 100:.2f}%")
    if profit_margin is not None:
        st.write(f"**Peļņas marža:** {profit_margin * 100:.2f}%")
    if target_mean:
        upside = ((target_mean - price) / price) * 100
        st.write(f"**Analītiķu vidējais target price:** {target_mean:.2f}")
        st.write(f"**Atšķirība līdz target price:** {upside:.2f}%")

    st.write(f"**Analītiķu rekomendācija:** {recommendation}")

    st.subheader("Ko šis uzņēmums dara")
    st.write(summary[:1200])

    st.subheader("Nākotnes skats")
    try:
        ai_analysis = ai_future_view(
            name,
            sector,
            industry,
            summary,
            pe,
            revenue_growth,
            earnings_growth,
            price
        )
        st.write(ai_analysis)
    except Exception as e:
        st.error("AI analīze neizdevās. Pārbaudi OPENAI_API_KEY Render Environment sadaļā.")
        st.write(e)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(data.index, data["Close"], label="Cena")
    ax.plot(data.index, data["SMA20"], label="SMA20")
    ax.plot(data.index, data["SMA50"], label="SMA50")
    ax.plot(data.index, data["SMA200"], label="SMA200")
    ax.set_title(symbol + " cena + SMA analīze")
    ax.legend()
    ax.grid()
    st.pyplot(fig)


mode = st.radio(
    "Ko gribi darīt?",
    ["Analīze", "Iespējas", "Salīdzināt", "Sākums", "Kalkulators", "Profils"],
    horizontal=True
)

if mode == "Salīdzināt":

    st.subheader("Aktīvu salīdzināšana")

    symbols_text = st.text_input(
        "Ievadi simbolus, atdalot ar komatiem",
        "NVDA, MSFT, GOOGL, AMD"
    )

    if st.button("Salīdzināt"):

        symbols = [s.strip().upper() for s in symbols_text.split(",") if s.strip()]
        results = []

        for symbol in symbols:
            try:

                original_symbol = symbol

                symbol_map = {
                    # Kripto
                    "BTC": "BTC-USD",
                    "ETH": "ETH-USD",
                    "SOL": "SOL-USD",
                    "XRP": "XRP-USD",
                    "ADA": "ADA-USD",

                    # ETF
                    "EQQQ": "EQQQ.L",
                    "VWCE": "VWCE.DE",
                    "VUAA": "VUAA.L",
                    "VUSA": "VUSA.L",
                    "SXR8": "SXR8.DE",
                    "IWDA": "IWDA.AS",
                    "CSPX": "CSPX.L",

                    # Indeksi
                    "NQ": "^NDX",
                    "NDX": "^NDX",
                    "NASDAQ": "^IXIC",
                    "SPX": "^GSPC",
                    "SP500": "^GSPC",
                    "DAX": "^GDAXI"
                }

                symbol = symbol_map.get(symbol, symbol)

                data = yf.download(symbol, period="5y", interval="1d", auto_adjust=True)

                if data.empty:
                    results.append({
                        "Ticker": original_symbol,
                        "Yahoo simbols": symbol,
                        "Statuss": "Nav datu"
                    })
                    continue

                if isinstance(data.columns, pd.MultiIndex):
                    data = data.xs(symbol, axis=1, level=1)

                ticker = yf.Ticker(symbol)
                info = ticker.info

                price = to_float(data["Close"].iloc[-1])

                def ret(days):
                    if len(data) > days:
                        old = to_float(data["Close"].iloc[-days])
                        return ((price - old) / old) * 100
                    return None

                ret_1m = ret(21)
                ret_1y = ret(252)
                ret_5y = ret(1260)

                data["Daily_Return"] = data["Close"].pct_change()
                volatility = to_float(data["Daily_Return"].rolling(30).std().iloc[-1]) * 100

                data["SMA200"] = data["Close"].rolling(200).mean()
                sma200 = to_float(data["SMA200"].iloc[-1])

                distance_sma200 = ((price - sma200) / sma200) * 100 if sma200 else None

                pe = info.get("trailingPE", None)
                market_cap = info.get("marketCap", None)
                name = info.get("shortName", symbol)

                score = 50

                if ret_1y is not None and ret_1y > 0:
                    score += 10
                else:
                    score -= 10

                if price > sma200:
                    score += 10
                else:
                    score -= 10

                if volatility is not None:
                    if volatility > 5:
                        score -= 10
                    elif volatility < 3:
                        score += 5

                if pe is not None:
                    if pe > 80:
                        score -= 10
                    elif pe < 30:
                        score += 5

                score = max(0, min(100, round(score)))

                if volatility is not None and volatility > 5:
                    risk = "Augsts"
                elif volatility is not None and volatility > 3:
                    risk = "Vidējs"
                else:
                    risk = "Zems / vidējs"

                results.append({
                    "Ticker": symbol,
                    "Nosaukums": name,
                    "Cena": round(price, 2),
                    "1M %": round(ret_1m, 2) if ret_1m is not None else None,
                    "1Y %": round(ret_1y, 2) if ret_1y is not None else None,
                    "5Y %": round(ret_5y, 2) if ret_5y is not None else None,
                    "P/E": round(pe, 2) if pe is not None else None,
                    "Market Cap B": round(market_cap / 1_000_000_000, 2) if market_cap else None,
                    "No SMA200 %": round(distance_sma200, 2) if distance_sma200 is not None else None,
                    "Risks": risk,
                    "Score": score,
                    "Statuss": "OK"
                })

            except Exception as e:
                results.append({
                    "Ticker": symbol,
                    "Statuss": f"Kļūda: {e}"
                })

        df_compare = pd.DataFrame(results)

        st.subheader("Salīdzinājuma tabula")
        st.dataframe(df_compare, use_container_width=True)

        valid_df = df_compare[df_compare["Statuss"] == "OK"].copy()

        if not valid_df.empty:
            best = valid_df.sort_values("Score", ascending=False).iloc[0]

            st.subheader("Secinājums")
            st.success(f"Augstākais vērtējums: {best['Ticker']} ar {best['Score']}/100")

            st.write("""
Score nav garantēts pirkšanas signāls. Tas tikai salīdzina aktīvus pēc cenas trenda,
ienesīguma, riska un dažiem fundamentālajiem rādītājiem.
""")


if mode == "Profils":

    st.subheader("Investora profils")

    age = st.slider("Vecums", 18, 80, 25)

    horizon = st.selectbox(
        "Cik ilgi plāno investēt?",
        ["Mazāk par 3 gadiem", "3-10 gadi", "10+ gadi"]
    )

    drop = st.selectbox(
        "Ja portfelis nokrīt par 30%, ko darītu?",
        [
            "Pārdotu visu",
            "Pagaidītu",
            "Pirktu vēl"
        ]
    )

    experience = st.selectbox(
        "Pieredze investēšanā",
        [
            "Nav",
            "Neliela",
            "Vidēja",
            "Liela"
        ]
    )

    goal = st.selectbox(
        "Galvenais mērķis",
        [
            "Saglabāt kapitālu",
            "Stabila izaugsme",
            "Maksimāla izaugsme"
        ]
    )

    monthly = st.number_input(
        "Cik vari investēt mēnesī (€)?",
        min_value=0,
        value=100,
        step=25
    )

    emergency_fund = st.selectbox(
        "Vai tev ir drošības rezerve 3-6 mēnešiem?",
        [
            "Nav",
            "Daļēji ir",
            "Jā, ir"
        ]
    )

    knowledge = st.selectbox(
        "Cik labi saproti, ko pērc?",
        [
            "Nesaprotu gandrīz neko",
            "Saprotu pamatus",
            "Saprotu diezgan labi"
        ]
    )

    preferred_assets = st.multiselect(
        "Kas tev interesē visvairāk?",
        [
            "ETF",
            "Akcijas",
            "Kripto",
            "Zelts",
            "Indeksi"
        ],
        default=["ETF", "Akcijas"]
    )

    if st.button("Noteikt profilu"):

        score = 0

        if horizon == "10+ gadi":
            score += 2
        elif horizon == "3-10 gadi":
            score += 1

        if drop == "Pirktu vēl":
            score += 2
        elif drop == "Pagaidītu":
            score += 1

        if experience == "Vidēja":
            score += 1
        elif experience == "Liela":
            score += 2

        if goal == "Maksimāla izaugsme":
            score += 2
        elif goal == "Stabila izaugsme":
            score += 1

        if monthly >= 500:
            score += 2
        elif monthly >= 100:
            score += 1

        if emergency_fund == "Jā, ir":
            score += 1
        elif emergency_fund == "Nav":
            score -= 2

        if knowledge == "Saprotu diezgan labi":
            score += 2
        elif knowledge == "Saprotu pamatus":
            score += 1
        else:
            score -= 1

        if "Kripto" in preferred_assets:
            score += 1

        score = max(0, score)

        if score <= 3:
            profile_name = "Konservatīvs investors"
            allocation = """
• 80% ETF
• 15% stabilas akcijas
• 5% kripto vai zelts
"""
            examples = "VOO, VWCE, SCHD, VTI, MSFT"
            warning = "Tev labāk izvairīties no ļoti svārstīgiem aktīviem un nepirkt visu vienā reizē."

        elif score <= 7:
            profile_name = "Sabalansēts investors"
            allocation = """
• 60% ETF
• 30% akcijas
• 10% kripto vai augstāka riska aktīvi
"""
            examples = "VOO, QQQ, MSFT, GOOGL, NVDA, BTC"
            warning = "Tev piemērota pakāpeniska ieguldīšana, kombinējot stabilitāti ar izaugsmi."

        else:
            profile_name = "Agresīvs investors"
            allocation = """
• 40% ETF
• 40% izaugsmes akcijas
• 20% kripto vai augsta riska aktīvi
"""
            examples = "QQQ, NVDA, PLTR, AMD, BTC, ETH, SOL"
            warning = "Tev var derēt augstāka riska aktīvi, bet jābūt gatavam lieliem kritumiem."

        st.success(f"Tavs profils: {profile_name}")

        st.subheader("Ieteicamais sadalījums")
        st.write(allocation)

        st.subheader("Piemēri")
        st.write(examples)

        st.subheader("Riska vērtējums")
        risk_score = min(10, max(1, round(score)))
        st.write(f"Riska līmenis: **{risk_score}/10**")

        st.subheader("Secinājums")

        if score <= 3:
            st.info("Tu vairāk koncentrējies uz kapitāla saglabāšanu nekā maksimālu peļņu.")
        elif score <= 7:
            st.info("Tu meklē līdzsvaru starp risku un peļņu.")
        else:
            st.info("Tu esi gatavs uzņemties lielāku risku, lai sasniegtu augstāku potenciālo atdevi.")

        st.subheader("Ko ņemt vērā")
        st.warning(warning)

        if emergency_fund == "Nav":
            st.error("Pirms lielākas investēšanas labāk vispirms izveidot drošības rezervi 3-6 mēnešiem.")

        if monthly < 50:
            st.warning("Ar ļoti mazu mēneša summu labāk sākt vienkārši ar ETF un regulāru investēšanu.")

        if age < 30 and horizon == "10+ gadi":
            st.info("Tavs vecums un ilgais horizonts ļauj uzņemties nedaudz lielāku risku nekā īstermiņa investoram.")

        if goal == "Maksimāla izaugsme" and drop == "Pārdotu visu":
            st.warning("Tev mērķis ir agresīvs, bet krituma gadījumā reakcija ir konservatīva. Labāk izvēlēties sabalansētu pieeju.")


if mode == "Kalkulators":
    st.subheader("Investīciju kalkulators")

    current_amount = st.number_input("Sākuma summa (€)", min_value=0.0, value=1200.0, step=100.0)
    annual_return = st.number_input("Gada ienesīgums (%)", min_value=0.0, value=10.0, step=1.0)
    years = st.number_input("Cik gadi?", min_value=1, value=10, step=1)
    yearly_deposit = st.number_input("Papildus iemaksa gadā (€)", min_value=0.0, value=1500.0, step=100.0)

    values = []
    amount = current_amount

    for year in range(1, years + 1):
        amount = amount * (1 + annual_return / 100) + yearly_deposit
        values.append({
            "Gads": year,
            "Summa (€)": round(amount, 2),
            "Iemaksāts kopā (€)": round(current_amount + yearly_deposit * year, 2),
            "Peļņa (€)": round(amount - (current_amount + yearly_deposit * year), 2)
        })

    df = pd.DataFrame(values)

    final_amount = df["Summa (€)"].iloc[-1]
    total_contributed = df["Iemaksāts kopā (€)"].iloc[-1]
    profit = final_amount - total_contributed

    st.subheader("Kopsavilkums")

    col1, col2, col3 = st.columns(3)
    col1.metric("Gala summa", f"{final_amount:,.2f} €")
    col2.metric("Kopā iemaksāts", f"{total_contributed:,.2f} €")
    col3.metric("Peļņa", f"{profit:,.2f} €")

    st.subheader("Tabula pa gadiem")
    st.dataframe(df, use_container_width=True)

    st.subheader("Pieauguma grafiks")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["Gads"], df["Summa (€)"], marker="o", label="Kopējā summa")
    ax.plot(df["Gads"], df["Iemaksāts kopā (€)"], marker="o", label="Iemaksāts kopā")
    ax.set_xlabel("Gadi")
    ax.set_ylabel("€")
    ax.set_title("Investīciju pieaugums")
    ax.legend()
    ax.grid(True)

    st.pyplot(fig)

    st.info("Aprēķins ir aptuvens. Reālais rezultāts var atšķirties tirgus svārstību, komisiju un nodokļu dēļ.")

if mode == "Sākums":
    st.subheader("Kā sākt investēt")

    st.write("""
Šis bots palīdz saprast aktīva cenu, trendu, risku, ieejas punktu un potenciālu.
Tas nav garantēts pirkšanas vai pārdošanas signāls.
""")

    st.subheader("Kur investēt?")

    st.write("""
1. Trading212
- Ļoti vienkārša lietošana
- Piemērota iesācējiem
- Var pirkt arī daļējas akcijas

2. Interactive Brokers (IBKR)
- Viena no lielākajām platformām pasaulē
- Ļoti zemas komisijas
- Milzīgs instrumentu klāsts

3. XTB
- Ērta platforma
- Pieejamas akcijas un ETF
- Populāra Eiropā

4. Trade Republic
- Vienkārša lietošana
- Pieejamas akcijas, ETF un obligācijas
- Zemas komisijas izmaksas
""")

    st.subheader("Svarīgākie termini")

    st.write("""
P/E (Price/Earnings)
- Cenas attiecība pret peļņu
- Zemāks parasti nozīmē lētāku uzņēmumu
- Augsts P/E nozīmē, ka tirgus sagaida strauju izaugsmi

SMA50
- Vidējā cena pēdējo 50 dienu laikā
- Parāda īstermiņa trendu

SMA200
- Vidējā cena pēdējo 200 dienu laikā
- Viens no svarīgākajiem ilgtermiņa trendu indikatoriem

Market Cap
- Uzņēmuma kopējā vērtība biržā

EPS
- Peļņa uz vienu akciju

Dividend Yield
- Dividenžu ienesīgums procentos gadā

ETF
- Fonds, kurā ir daudz uzņēmumu vienlaikus
- Samazina risku

Akcija
- Tu pērc daļu no uzņēmuma
- Ja uzņēmumam iet labi, akcijas cena var augt

Obligācija
- Aizdod naudu valstij vai uzņēmumam
- Pretī saņem procentu maksājumus

DCA
- Regulāri pirkumi pa daļām
- Samazina risku nopirkt visu nepareizā brīdī

Diversifikācija
- Naudas sadalīšana vairākos aktīvos
- Samazina risku

Volatilitāte
- Cik strauji cena kustas augšā un lejā
- Liela volatilitāte = lielāks risks
""")

    st.subheader("Iesācējam drošāka pieeja")

    st.write("""
Parasti iesācējam drošāk sākt ar plaši diversificētiem ETF, piemēram S&P500 vai pasaules ETF.
Tie sadala risku starp daudziem uzņēmumiem, nevis liek visu naudu vienā akcijā.
""")

    st.subheader("Kas parasti ir riskantāk")

    st.write("""
Riskantāk ir likt lielu summu vienā akcijā, kripto, ļoti svārstīgos uzņēmumos vai aktīvos,
kas jau ir strauji kāpuši un atrodas ļoti tuvu maksimumiem.
""")

    st.subheader("Svarīgas lietas")

    st.write("""
- Labāk pirkt pa daļām jeb DCA.
- Skaties, vai cena nav ļoti tālu virs SMA200.
- Ja cena ir zem SMA200, tā var būt lētāka, bet trends var būt vājš.
- Jo lielāks potenciāls, jo parasti lielāks risks.
- Salīdzini vairākus variantus un konkurentus, nevis izvēlies pirmo.
- Kad cena ir strauji kāpusi un visi par to runā, tas bieži nav labākais brīdis pirkšanai.
- Labākie brīži pirkšanai bieži ir tad, kad cena krīt un tirgū ir bailes, bet jāņem vērā risks, ka aktīvs var neatgūties.
""")

    st.subheader("Svarīgākie kritēriji investīcijas izvēlē")

    st.write("""
1. Trends
- Cena virs SMA200 parasti liecina par spēcīgāku ilgtermiņa trendu.
- Cena zem SMA200 var būt lētāka, bet arī riskantāka.

2. Uzņēmuma izaugsme
- Skaties Revenue Growth un Earnings Growth.
- Uzņēmumi ar augošiem ieņēmumiem un peļņu bieži attīstās straujāk.

3. Risks un volatilitāte
- Jo lielākas cenu svārstības, jo lielāks risks.
- Augstāks potenciāls parasti nozīmē arī lielāku risku.

4. Attālums no 52 nedēļu maksimuma
- Ja cena ir ļoti tuvu maksimumam, aktīvs var būt dārgs.
- Pēc korekcijām bieži rodas labākas ieejas iespējas.

5. Nozare un nākotnes potenciāls
- Meklē nozares ar ilgtermiņa izaugsmes potenciālu:
  • Mākslīgais intelekts (AI)
  • Pusvadītāji
  • Robotika
  • Kiberdrošība
  • Mākoņdatošana
  • Enerģijas uzkrāšana un baterijas

6. Saproti, ko pērc
- Pirms investēšanas saproti, kā uzņēmums pelna naudu.
- Nepērc tikai tāpēc, ka kāds internetā to iesaka.
""")

    st.success("""
Labs ilgtermiņa aktīvs parasti:
✓ Atrodas virs SMA200
✓ Aug ieņēmumi un peļņa
✓ Darbojas perspektīvā nozarē
✓ Nav pārmērīgi riskants
✓ Ir saprotams uzņēmuma biznesa modelis
""")

if mode == "Analīze":

    asset_type = st.selectbox(
        "Izvēlies aktīva tipu:",
        ["Akcija", "ETF", "Kripto", "Zelts", "Indekss"],
        key="analysis_asset_type"
    )

    symbol_input = st.text_input(
        "Ievadi simbolu, piemēram NVDA, TSLA, SPY, BTC",
        key="analysis_symbol"
    )

    if st.button("Analizēt", key="analysis_button"):
        if not symbol_input and asset_type != "Zelts":
            st.error("Ievadi simbolu.")
        else:
            if asset_type == "Kripto":
                symbol = symbol_input.upper() + "-USD"
            elif asset_type == "Zelts":
                symbol = "GC=F"
            else:
                symbol = symbol_input.upper()

            analyze_symbol(symbol, asset_type)


if mode == "Iespējas":

    st.subheader("Ideju meklētājs")

    user_theme = st.text_input(
        "Ieraksti virzienu, kas interesē, piemēram: AI, droni, baterijas, kiberdrošība"
    )

    if st.button("Ģenerēt idejas"):
        prompt = f"""
    Lietotāju interesē investīciju virziens: {user_theme}

    Atbildi latviešu valodā ļoti īsi.
    Iedod 5 investīciju idejas.

    Formāts:
    1. Ticker - tips - ļoti īss iemesls - risks

    Neizdomā neeksistējošus tickerus.
    Iekļauj akcijas, ETF vai kripto tikai, ja tie ir reāli un plaši zināmi.
    Neraksti garu tekstu.
    """

        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300
            )

            st.write(response.choices[0].message.content)

        except Exception as e:
            st.error("Ideju ģenerēšana neizdevās.")
            st.write(e)

    st.subheader("Investīciju iespējas pēc nozares")

    sector = st.selectbox(
        "Izvēlies nozari:",
        [
            "AI",
            "Pusvadītāji",
            "Robotika",
            "Kiberdrošība",
            "Mākoņdatošana",
            "Elektroauto",
            "Baterijas",
            "Kosmoss",
            "Aizsardzība",
            "Enerģētika",
            "Biotehnoloģijas",
            "Finanšu tehnoloģijas",
            "Kripto"
        ],
        key="sector_select"
    )

    sector_ideas = {
        "AI": [
            {"ticker": "NVDA", "type": "Akcija", "desc": "AI čipu līderis."},
            {"ticker": "MSFT", "type": "Akcija", "desc": "AI un mākoņdatošana."},
            {"ticker": "PLTR", "type": "Akcija", "desc": "AI datu analīze."},
            {"ticker": "QQQ", "type": "ETF", "desc": "Nasdaq-100 ETF ar lielu AI/tech ietekmi."}
        ],
        "Robotika": [
            {"ticker": "TSLA", "type": "Akcija", "desc": "Robotika, autonomija, Optimus."},
            {"ticker": "SYM", "type": "Akcija", "desc": "Noliktavu automatizācija."},
            {"ticker": "BOTZ", "type": "ETF", "desc": "Robotikas un automatizācijas ETF."}
        ],
        "Kiberdrošība": [
            {"ticker": "CRWD", "type": "Akcija", "desc": "Cloud kiberdrošība."},
            {"ticker": "PANW", "type": "Akcija", "desc": "Liels kiberdrošības uzņēmums."},
            {"ticker": "CIBR", "type": "ETF", "desc": "Kiberdrošības ETF."}
        ],
        "Pusvadītāji": [
            {"ticker": "NVDA", "type": "Akcija", "desc": "GPU un AI čipi."},
            {"ticker": "AMD", "type": "Akcija", "desc": "Procesori un GPU."},
            {"ticker": "TSM", "type": "Akcija", "desc": "Čipu ražošana."},
            {"ticker": "SOXX", "type": "ETF", "desc": "Pusvadītāju ETF."}
            ],
        "Mākoņdati": [
            {"ticker": "MSFT", "type": "Akcija", "desc": "Azure cloud."},
            {"ticker": "AMZN", "type": "Akcija", "desc": "AWS cloud."},
            {"ticker": "GOOGL", "type": "Akcija", "desc": "Google Cloud."}
        ],
        "Elektroauto": [
            {"ticker": "TSLA", "type": "Akcija", "desc": "Elektroauto, AI un baterijas."},
            {"ticker": "XPEV", "type": "Akcija", "desc": "Ķīnas elektroauto uzņēmums."},
            {"ticker": "DRIV", "type": "ETF", "desc": "EV un autonomo auto ETF."}
        ],
        "Baterijas": [
            {"ticker": "QS", "type": "Akcija", "desc": "Solid-state bateriju potenciāls."},
            {"ticker": "ALB", "type": "Akcija", "desc": "Litija uzņēmums."},
            {"ticker": "LIT", "type": "ETF", "desc": "Litija un bateriju ETF."}
        ],
        "Kosmoss": [
            {"ticker": "RKLB", "type": "Akcija", "desc": "Kosmosa palaišanas uzņēmums."},
            {"ticker": "ASTS", "type": "Akcija", "desc": "Satelītu komunikācijas."},
            {"ticker": "ARKX", "type": "ETF", "desc": "Kosmosa tematiskais ETF."}
        ],
        "Aizsardzība": [
            {"ticker": "LMT", "type": "Akcija", "desc": "Aizsardzības uzņēmums."},
            {"ticker": "RTX", "type": "Akcija", "desc": "Aizsardzība un aviācija."},
            {"ticker": "ITA", "type": "ETF", "desc": "Aizsardzības un aviācijas ETF."}
        ],
        "Enerģētika": [
            {"ticker": "XOM", "type": "Akcija", "desc": "Nafta un enerģētika."},
            {"ticker": "NEE", "type": "Akcija", "desc": "Atjaunojamā enerģija."},
            {"ticker": "XLE", "type": "ETF", "desc": "Enerģētikas ETF."}
        ],
        "Biotehnoloģijas": [
            {"ticker": "LLY", "type": "Akcija", "desc": "Farmācija un veselības inovācijas."},
            {"ticker": "NVO", "type": "Akcija", "desc": "Diabēta un svara zāles."},
            {"ticker": "IBB", "type": "ETF", "desc": "Biotehnoloģiju ETF."}
        ],
        "Finanšu tehnoloģijas": [
            {"ticker": "PYPL", "type": "Akcija", "desc": "Digitālie maksājumi."},
            {"ticker": "SQ", "type": "Akcija", "desc": "Fintech un maksājumi."},
            {"ticker": "ARKF", "type": "ETF", "desc": "Fintech ETF."}
        ],
        "Kripto": [
            {"ticker": "BTC", "type": "Kripto", "desc": "Lielākā kriptovalūta."},
            {"ticker": "ETH", "type": "Kripto", "desc": "Smart contract ekosistēma."},
            {"ticker": "SOL", "type": "Kripto", "desc": "Ātra blockchain platforma."},
            {"ticker": "MSTR", "type": "Akcija", "desc": "Akcija ar lielu Bitcoin ekspozīciju."}
        ]
    }

    ideas = sector_ideas.get(sector, [])

    st.info(f"Iespējas nozarē: {sector}")

    for item in ideas:
        with st.container(border=True):
            st.subheader(item["ticker"])
            st.write(f"**Tips:** {item['type']}")
            st.write(f"**Kas tas ir:** {item['desc']}")

            if st.button(f"Analizēt {item['ticker']}", key=f"analyze_{sector}_{item['ticker']}"):
                analyze_symbol(item["ticker"], item["type"])

