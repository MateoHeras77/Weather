import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px
from streamlit_autorefresh import st_autorefresh

# Load environment variables (from Streamlit Secrets)
TOMTOM_API_KEY = st.secrets.get("TOMTOM_API_KEY") if hasattr(st, "secrets") else None

# --- PAGE CONFIG ---
st.set_page_config(page_title="Purolator Weather Dashboard", layout="wide", page_icon="🌤️")

# Custom CSS for Purolator Branding
st.markdown("""
<style>
    /* Main Header Background and Text */
    header[data-testid="stHeader"] {
        background-color: #1C3F94 !important;
    }
    header[data-testid="stHeader"] * {
        color: white !important;
    }
    
    /* Hide Sidebar */
    [data-testid="stSidebar"] {
        display: none;
    }
    
    /* Main Content Padding */
    .main .block-container {
        padding-top: 1rem;
    }

    /* Primary Titles */
    h1, h2, h3 {
        color: #1C3F94 !important;
    }

    /* Buttons (CTAs) */
    .stButton>button {
        background-color: #EE3124 !important;
        color: white !important;
        border-radius: 4px;
        border: none;
        width: 100%;
    }
    
    .stButton>button:hover {
        background-color: #D22B1F !important;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        color: #1C3F94 !important;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
        border-bottom: 2px solid #F0F2F6;
    }

    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 4px 4px 0px 0px;
        color: #262730;
        font-weight: 600;
        font-size: 16px;
    }

    .stTabs [aria-selected="true"] {
        background-color: #F0F2F6 !important;
        color: #1C3F94 !important;
        border-bottom: 3px solid #EE3124 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- AUTO REFRESH LOGIC ---
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = False

# --- APP HEADER ---
head_col1, head_col2, head_col3 = st.columns([2, 1, 1])

with head_col1:
    st.image("logo.svg", width=300)

with head_col2:
    # Manual Refresh
    if st.button("Refresh Data 🔄"):
        fetch_weather_data.clear()
        fetch_traffic_incidents.clear()
        raw_data = fetch_weather_data()
        st.session_state.df = process_geojson(raw_data)
        st.rerun()

with head_col3:
    # Auto Refresh Toggle
    auto_refresh_toggle = st.checkbox("Auto-Refresh (5m)", value=st.session_state.auto_refresh)
    if auto_refresh_toggle != st.session_state.auto_refresh:
        st.session_state.auto_refresh = auto_refresh_toggle
        st.rerun()

if st.session_state.auto_refresh:
    # 300,000 ms = 5 minutes
    count = st_autorefresh(interval=300000, limit=None, key="data_autorefresh")
    if count > 0: # Clear cache on the interval ticks
        fetch_weather_data.clear()
        fetch_traffic_incidents.clear()
        raw_data = fetch_weather_data()
        st.session_state.df = process_geojson(raw_data)

# --- DATA FETCHING ---
API_URL = "https://api.weather.gc.ca/collections/citypageweather-realtime/items?f=json&limit=1000"

@st.cache_data(ttl=600) # Cache for 10 minutes
def fetch_weather_data():
    try:
        response = requests.get(API_URL, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None

# --- PROCESS DATA ---
def process_geojson(data):
    if not data or 'features' not in data:
        return pd.DataFrame()
    
    cities = []
    for feature in data['features']:
        props = feature.get('properties', {})
        geom = feature.get('geometry', {})
        
        # Coordinates
        coords = geom.get('coordinates', [None, None])
        if coords[0] is None or coords[1] is None:
            continue
        lon, lat = coords[0], coords[1]
        
        # Basic Info
        city_name = props.get('name', {}).get('en', 'Unknown City')
        
        # Current Conditions
        curr = props.get('currentConditions', {})
        
        def extract_en(val):
            return val.get('en') if isinstance(val, dict) else val

        temp = extract_en(curr.get('temperature', {}).get('value'))
        wind_speed = extract_en(curr.get('wind', {}).get('speed', {}).get('value'))
        wind_dir = extract_en(curr.get('wind', {}).get('direction', {}).get('value'))
        wind_gust = extract_en(curr.get('wind', {}).get('gust', {}).get('value'))
        condition = curr.get('condition', {}).get('en', 'Unknown')
        visibility = extract_en(curr.get('visibility', {}).get('value'))
        
        humidity = extract_en(curr.get('relativeHumidity', {}).get('value'))
        dewpoint = extract_en(curr.get('dewpoint', {}).get('value'))
        pressure = extract_en(curr.get('pressure', {}).get('value'))
        pressure_tend = curr.get('pressure', {}).get('tendency', {}).get('en', '')
        wind_chill = extract_en(curr.get('windChill', {}).get('value'))
        
        # Alerts
        warnings = props.get('warnings', [])
        alert_details = []
        for w in warnings:
            if not w: continue
            w_type = w.get('type', {}).get('en', 'Alert')
            w_desc = w.get('description', {}).get('en', 'No description available.')
            alert_details.append({"type": w_type, "description": w_desc})
            
        has_alert = len(alert_details) > 0
        alert_types_str = ", ".join([a["type"] for a in alert_details]) if has_alert else "None"
        
        cities.append({
            'City': city_name,
            'Latitude': lat,
            'Longitude': lon,
            'Temperature (°C)': temp,
            'Wind Speed (km/h)': wind_speed,
            'Wind Dir': wind_dir,
            'Wind Gust': wind_gust,
            'Condition': condition,
            'Visibility (km)': visibility,
            'Humidity (%)': humidity,
            'Dewpoint (°C)': dewpoint,
            'Pressure (kPa)': pressure,
            'Pressure Tendency': pressure_tend,
            'Wind Chill': wind_chill,
            'Alerts': alert_types_str,
            'Alert Details': alert_details,
            'Has Alert': has_alert,
            'RawProperties': props
        })
        
    return pd.DataFrame(cities)

# Initialize Data
if "df" not in st.session_state:
    with st.spinner("Fetching latest weather data across Canada..."):
        raw_data = fetch_weather_data()
        st.session_state.df = process_geojson(raw_data)

df = st.session_state.df

if df.empty:
    st.warning("No data available. Please check the API.")
    st.stop()

# --- TOMTOM DATA FETCHING ---
ZONES = {
    "National View": {"center": [56.1304, -106.3468], "zoom": 4},
    "Greater Toronto Area (GTA)": {"center": [43.7, -79.4], "zoom": 9},
    "Greater Montreal": {"center": [45.5, -73.6], "zoom": 10},
    "Metro Vancouver": {"center": [49.2, -123.0], "zoom": 10},
    "Calgary Hub": {"center": [51.0, -114.0], "zoom": 10}
}

@st.cache_data(ttl=300) # Cache traffic data for 5 minutes
def fetch_traffic_incidents(bbox, api_key):
    if not bbox or not api_key: return []
    # TomTom Incident Details API
    url = "https://api.tomtom.com/traffic/services/5/incidentDetails"
    params = {
        "key": api_key,
        "bbox": bbox,
        "fields": "{incidents{geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,events{description,code},startTime,endTime,from,to,length,delay,roadNumbers}}}",
        "language": "en-GB"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get('incidents', [])
    except Exception as e:
        st.error(f"Error fetching TomTom Traffic: {e}")
        return []

# --- PAGE 1: REGIONAL OVERVIEW ---
def page_regional_overview():
    st.title("Logistics Weather: Regional Overview")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("Use the layer control icon (top right of map) to toggle Weather Radar, Satellite, and Traffic layers.")
    with col2:
        selected_zone = st.selectbox("Focus Map:", list(ZONES.keys()), index=0)
        
    with st.expander("🗺️ Map Legend & Icon Guide", expanded=False):
        leg_col1, leg_col2 = st.columns(2)
        with leg_col1:
            st.markdown("""
            **🌤️ Weather Markers (Cities)**
            *   🟢 **Green:** Normal / Clear conditions.
            *   🟠 **Orange:** Extreme Cold / Icy (<-15°C).
            *   🔴 **Red (#EE3124):** Active Severe Weather Alert.
            *   🟣 **Purple:** High Wind Danger (Gusts > 70km/h). High risk of trailer rollover.
            """)
        with leg_col2:
            st.markdown("""
            **🚗 TomTom Traffic Flow Lines**
            *   🟡 **Yellow/Orange:** Minor congestion / slow traffic.
            *   🔴 **Red:** Heavy congestion / significant delays.
            *   🟤 **Dark Red:** Stopped traffic / extreme delay / road closure.
            """)
    
    zone_data = ZONES[selected_zone]

    show_alerts_only = st.checkbox("🚨 Show only cities with active alerts", value=False)
    filtered_df = df[df['Has Alert'] == True] if show_alerts_only else df

    m = folium.Map(location=zone_data["center"], zoom_start=zone_data["zoom"])

    folium.WmsTileLayer(
        url="https://geo.weather.gc.ca/geomet",
        layers="RADAR_1KM_RRSKS",
        fmt="image/png",
        transparent=True,
        name="Weather Radar",
        overlay=True,
        control=True,
        show=False
    ).add_to(m)

    folium.WmsTileLayer(
        url="https://geo.weather.gc.ca/geomet",
        layers="GOES-16",
        fmt="image/png",
        transparent=True,
        name="Satellite Imagery",
        overlay=True,
        control=True,
        show=False
    ).add_to(m)

    if TOMTOM_API_KEY:
        # TomTom Traffic Flow Layer
        folium.TileLayer(
            tiles=f"https://api.tomtom.com/traffic/map/4/tile/flow/relative0/{{z}}/{{x}}/{{y}}.png?key={TOMTOM_API_KEY}",
            attr="TomTom Traffic",
            name="Traffic Flow (TomTom)",
            overlay=True,
            control=True,
            show=False
        ).add_to(m)
        
        # TomTom Traffic Incidents Layer
        folium.TileLayer(
            tiles=f"https://api.tomtom.com/traffic/map/4/tile/incidents/s3/{{z}}/{{x}}/{{y}}.png?key={TOMTOM_API_KEY}",
            attr="TomTom Incidents",
            name="Traffic Incidents (TomTom)",
            overlay=True,
            control=True,
            show=True
        ).add_to(m)

    for idx, row in filtered_df.iterrows():
        marker_color = 'green'
        
        # Wind Gust Logic (High Priority for Trucks)
        try:
            gust = float(row.get('Wind Gust', 0) or 0)
        except:
            gust = 0
            
        if gust > 70:
            marker_color = 'purple' # High wind rollover danger
        elif row['Has Alert']:
            marker_color = '#EE3124' # Brand Red
        elif row['Temperature (°C)'] is not None and row['Temperature (°C)'] < -15:
            marker_color = 'orange'
            
        tooltip = f"{row['City']}: {row['Condition']}, {row['Temperature (°C)']}°C"
        
        folium.CircleMarker(
            location=[row['Latitude'], row['Longitude']],
            radius=5,
            color=marker_color,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.8,
            tooltip=tooltip
        ).add_to(m)

    folium.LayerControl().add_to(m)

    # Display Map
    map_data = st_folium(m, width=1200, height=500, returned_objects=["last_object_clicked", "bounds"])
    
    # Simple redirect to city details on click
    if map_data and map_data.get("last_object_clicked"):
        clicked_lat = map_data["last_object_clicked"]["lat"]
        clicked_lon = map_data["last_object_clicked"]["lng"]
        
        if not filtered_df.empty:
            filtered_df['dist'] = ((filtered_df['Latitude'] - clicked_lat)**2 + (filtered_df['Longitude'] - clicked_lon)**2)**0.5
            closest_city_row = filtered_df.loc[filtered_df['dist'].idxmin()]
            if closest_city_row['dist'] < 0.2: 
                st.session_state.selected_city = closest_city_row['City']
                st.success(f"Selected {closest_city_row['City']}! Switch to the 'City Details' page to view more.")

    # --- TRAFFIC INCIDENTS TABLE ---
    # Fetch dynamically based on map bounds
    current_bbox = None
    zoom_too_far = False
    
    if map_data and map_data.get("bounds"):
        bounds = map_data["bounds"]
        sw = bounds.get("_southWest", {})
        ne = bounds.get("_northEast", {})
        if sw and ne:
            lon_diff = abs(ne['lng'] - sw['lng'])
            lat_diff = abs(ne['lat'] - sw['lat'])
            
            # TomTom Incident API rejects areas > 10,000 sq km.
            # 1 deg lat ~= 111km. 1 deg lon in Canada (lat 45) ~= 78km.
            approx_area_sqkm = lon_diff * lat_diff * 8658
            
            if approx_area_sqkm > 9000:
                zoom_too_far = True
            else:
                # TomTom expects: minLon,minLat,maxLon,maxLat
                current_bbox = f"{sw['lng']},{sw['lat']},{ne['lng']},{ne['lat']}"

    if zoom_too_far:
        st.divider()
        st.info("🗺️ **Zoom in closer on the map** to a specific city or region to load the live traffic incidents table.")
    elif current_bbox and TOMTOM_API_KEY:
        st.divider()
        st.subheader("Active Traffic Incidents in Current View")
        with st.spinner("Fetching live incidents for your current map area..."):
            incidents = fetch_traffic_incidents(current_bbox, TOMTOM_API_KEY)
            
        if incidents:
            parsed_incidents = []
            for inc in incidents:
                props = inc.get('properties', {})
                geom = inc.get('geometry', {})
                events = props.get('events', [])
                desc = events[0].get('description', 'Unknown') if events else 'Unknown Incident'
                
                # Coordinate Extraction for Map Link
                map_link = None
                coords = geom.get('coordinates', [])
                if coords and isinstance(coords, list):
                    # Get first coord [lon, lat]
                    first_coord = coords[0] if isinstance(coords[0], list) else coords
                    lon_inc, lat_inc = first_coord[0], first_coord[1]
                    map_link = f"https://www.google.com/maps/search/?api=1&query={lat_inc},{lon_inc}"

                # Ensure we have numbers, not None
                raw_delay = props.get('delay')
                delay_sec = int(raw_delay) if raw_delay is not None else 0
                
                raw_length = props.get('length')
                length_m = int(raw_length) if raw_length is not None else 0
                
                # Start Time Parsing
                start_time_str = props.get('startTime')
                mins_ago = 0
                if start_time_str:
                    try:
                        st_time = pd.to_datetime(start_time_str, utc=True)
                        now = pd.Timestamp.now('UTC')
                        diff = now - st_time
                        mins_ago = int(diff.total_seconds() / 60)
                        if mins_ago < 0: mins_ago = 0
                    except Exception:
                        pass
                
                # Determine Status (Closure vs Delay)
                icon_cat = props.get('iconCategory', 6) # 0 is closure, 6 is unknown/general
                is_closed = (icon_cat == 0) or ("closed" in desc.lower()) or ("blocked" in desc.lower())
                status = "⛔ CLOSED" if is_closed else "⚠️ DELAY"
                
                # Only show impactful incidents (e.g. > 60 sec delay or closures)
                if is_closed or delay_sec > 60:
                    delay_val = round(delay_sec / 60, 1) if not is_closed else 0.0
                    delay_display = "BLOCKAGE" if is_closed else str(delay_val)
                    
                    parsed_incidents.append({
                        "Status": status,
                        "Type": desc,
                        "From": props.get('from', 'Unknown'),
                        "To": props.get('to', 'Unknown'),
                        "Link": map_link,
                        "Started (Mins Ago)": mins_ago,
                        "Delay (Mins)": delay_display,
                        "delay_raw": delay_val, # Hidden for sorting
                        "Length (km)": round(length_m / 1000, 2),
                        "Severity": props.get('magnitudeOfDelay', 0)
                    })
                    
            if parsed_incidents:
                inc_df = pd.DataFrame(parsed_incidents)
                # Default sort: incidents that started most recently first in ascending elapsed time.
                # Secondary sort keeps closures ahead when start times are equal.
                inc_df['sort_order'] = inc_df['Status'].apply(lambda x: 0 if "CLOSED" in x else 1)
                inc_df = inc_df.sort_values(
                    by=["Started (Mins Ago)", "sort_order", "delay_raw"],
                    ascending=[True, True, False]
                ).drop(columns=['sort_order', 'delay_raw']).reset_index(drop=True)
                
                # Display dataframe with custom column config
                st.dataframe(
                    inc_df, 
                    width="stretch",
                    column_config={
                        "Status": st.column_config.TextColumn("Status", width="small"),
                        "Link": st.column_config.LinkColumn("Map", display_text="📍 View"),
                        "Started (Mins Ago)": st.column_config.NumberColumn(
                            "Started",
                            help="How long ago the incident was reported",
                            format="%d mins ago"
                        )
                    }
                )
            else:
                st.success("No major traffic delays detected in this view right now.")
        else:
            st.success("No active traffic incidents found in this view.")
    elif not TOMTOM_API_KEY:
         st.warning("TomTom API Key missing. Add it to .env to see traffic data.")

# --- PAGE 2: CITY DETAILS ---
def page_city_details():
    st.title("Logistics Weather: City Details")
    
    city_list = df['City'].sort_values().tolist()
    default_city = st.session_state.get('selected_city', city_list[0] if city_list else None)
    selected_index = city_list.index(default_city) if default_city in city_list else 0
    
    selected_city = st.selectbox("Select a city for detailed forecast:", city_list, index=selected_index)
    st.session_state.selected_city = selected_city # Persist selection
    
    if selected_city:
        city_data = df[df['City'] == selected_city].iloc[0]
        
        # Alerts Display
        if city_data['Has Alert']:
            st.error(f"🚨 **ACTIVE WEATHER ALERTS FOR {selected_city.upper()}**")
            for alert in city_data['Alert Details']:
                with st.expander(f"**{alert['type']}**", expanded=True):
                    st.write(alert['description'])
        
        st.write("---")
        st.subheader("Current Conditions")
        
        # Primary Metrics
        st.write("#### Core Metrics")
        cols = st.columns(5)
        
        wind_spd = city_data.get('Wind Speed (km/h)')
        wind_dir = city_data.get('Wind Dir')
        wind_str = f"{wind_spd} km/h {wind_dir or ''}".strip() if pd.notna(wind_spd) else "N/A"
        
        cols[0].metric("🌡️ Temperature", f"{city_data['Temperature (°C)']} °C" if pd.notna(city_data['Temperature (°C)']) else "N/A")
        cols[1].metric("☁️ Condition", city_data['Condition'])
        cols[2].metric("💨 Wind", wind_str)
        cols[3].metric("👁️ Visibility", f"{city_data['Visibility (km)']} km" if pd.notna(city_data['Visibility (km)']) else "N/A")
        cols[4].metric("💧 Humidity", f"{city_data.get('Humidity (%)')}%" if pd.notna(city_data.get('Humidity (%)')) else "N/A")
        
        # Advanced Metrics
        st.write("#### Additional Metrics")
        cols2 = st.columns(5)
        
        wind_chill = city_data.get('Wind Chill')
        cols2[0].metric("🥶 Wind Chill / Humidex", f"{wind_chill} °C" if pd.notna(wind_chill) else "N/A")
        
        dewpoint = city_data.get('Dewpoint (°C)')
        cols2[1].metric("🌫️ Dewpoint", f"{dewpoint} °C" if pd.notna(dewpoint) else "N/A")
        
        wind_gust = city_data.get('Wind Gust')
        cols2[2].metric("🌬️ Wind Gust", f"{wind_gust} km/h" if pd.notna(wind_gust) else "N/A")
        
        pressure = city_data.get('Pressure (kPa)')
        pressure_tend = city_data.get('Pressure Tendency')
        press_str = f"{pressure} kPa" if pd.notna(pressure) else "N/A"
        cols2[3].metric("⏲️ Pressure", press_str, delta=pressure_tend if pressure_tend else None, delta_color="off")
        
        props = city_data['RawProperties']
        
        st.write("---")
        
        # Hourly Forecast
        st.subheader("Hourly Forecast")
        hourly_data = props.get('hourlyForecastGroup', {}).get('hourlyForecasts', [])
        if hourly_data:
            h_times = []
            h_temps = []
            for h in hourly_data:
                time_obj = h.get('dateTime', [])
                time_label = time_obj[1].get('textSummary', 'Unknown') if len(time_obj) > 1 else 'Unknown'
                temp_val = h.get('temperature', {}).get('value')
                temp = temp_val.get('en') if isinstance(temp_val, dict) else temp_val
                
                h_times.append(time_label)
                h_temps.append(temp)
                
            fig = px.line(
                x=range(len(h_temps)),
                y=h_temps, 
                markers=True, 
                title="Hourly Temperature Trend",
                labels={'x': 'Hours from now', 'y': 'Temperature (°C)'},
                color_discrete_sequence=['#1C3F94']
            )
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Hourly forecast data is currently unavailable for this location.")
            
        # Daily Forecast
        st.subheader("Daily Forecast (Up to 15 Days)")
        daily_data = props.get('forecastGroup', {}).get('forecasts', [])
        if daily_data:
            d_df = []
            for d in daily_data:
                temp_obj = d.get('temperatures', {}).get('temperature', [])
                temp_val = 'N/A'
                if temp_obj and isinstance(temp_obj, list) and len(temp_obj) > 0:
                    t_v = temp_obj[0].get('value')
                    temp_val = t_v.get('en') if isinstance(t_v, dict) else t_v
                
                precip_str = "None"
                precip_acc = d.get('precipitation', {}).get('accumulation', {})
                if precip_acc:
                    p_amt = precip_acc.get('amount', {}).get('value', {}).get('en')
                    p_unit = precip_acc.get('amount', {}).get('units', {}).get('en', '')
                    p_name = precip_acc.get('name', {}).get('en', 'precip').capitalize()
                    if p_amt is not None:
                        precip_str = f"{p_amt} {p_unit} {p_name}"
                
                # Fallback: Extract POP (Probability of Precipitation) from text if accumulation is None
                if precip_str == "None":
                    import re
                    txt = d.get('textSummary', {}).get('en', '')
                    # Look for "XX percent chance"
                    match = re.search(r"(\d+)\s*percent\s*chance", txt, re.IGNORECASE)
                    if match:
                        precip_str = f"{match.group(1)}% Chance"
                    elif "showers" in txt.lower() or "rain" in txt.lower() or "snow" in txt.lower():
                        precip_str = "Likely"
                    
                d_df.append({
                    'Period': d.get('period', {}).get('textForecastName', {}).get('en', 'Unknown'),
                    'Forecast': d.get('textSummary', {}).get('en', 'Unknown'),
                    'Temp (°C)': temp_val,
                    '☔ Precipitation': precip_str
                })
            st.dataframe(pd.DataFrame(d_df), width='stretch')
        else:
            st.info("Daily forecast data is currently unavailable for this location.")

import math

# --- TOMTOM HELPERS ---
@st.cache_data(ttl=3600)
def geocode_city(query, api_key):
    if not query or not api_key: return None
    url = f"https://api.tomtom.com/search/2/geocode/{query}.json"
    params = {"key": api_key, "limit": 1, "countrySet": "CA"}
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get('results'):
            res = data['results'][0]
            return {
                "name": res.get('address', {}).get('freeformAddress'),
                "lat": res.get('position', {}).get('lat'),
                "lon": res.get('position', {}).get('lon')
            }
    except Exception as e:
        st.error(f"Geocoding error: {e}")
    return None

@st.cache_data(ttl=600)
def fetch_route(origin_coords, dest_coords, api_key):
    if not origin_coords or not dest_coords or not api_key: return None
    # locations format: lat,lon:lat,lon
    locs = f"{origin_coords['lat']},{origin_coords['lon']}:{dest_coords['lat']},{dest_coords['lon']}"
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{locs}/json"
    params = {"key": api_key, "traffic": "true"}
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get('routes'):
            route = data['routes'][0]
            points = []
            for leg in route.get('legs', []):
                for pt in leg.get('points', []):
                    points.append([pt['latitude'], pt['longitude']])
            return {
                "polyline": points,
                "summary": route.get('summary', {})
            }
    except Exception as e:
        st.error(f"Routing error: {e}")
    return None

def haversine_dist(lat1, lon1, lat2, lon2):
    R = 6371 # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def get_corridor_data(route_polyline, df, api_key):
    if not route_polyline: return [], []
    
    # 1. Weather Waypoints (5 intervals)
    num_points = len(route_polyline)
    indices = [0, int(num_points*0.25), int(num_points*0.5), int(num_points*0.75), num_points-1]
    waypoint_stations = []
    
    for idx in indices:
        lat, lon = route_polyline[idx]
        # Find closest station in df
        df['temp_dist'] = df.apply(lambda row: haversine_dist(lat, lon, row['Latitude'], row['Longitude']), axis=1)
        closest_row = df.loc[df['temp_dist'].idxmin()].copy()
        if closest_row['temp_dist'] < 50: # Only if within 50km
            waypoint_stations.append(closest_row)
            
    # Remove duplicates while preserving order
    unique_stations = []
    seen_cities = set()
    for s in waypoint_stations:
        if s['City'] not in seen_cities:
            unique_stations.append(s)
            seen_cities.add(s['City'])
            
    # 2. Traffic Incidents along corridor
    # Split route into chunks to respect TomTom's 10,000 sq km limit per request
    num_chunks = 8 # Toronto to Montreal is ~540km, 8 chunks is ~65km each (safe area)
    chunk_size = max(1, num_points // num_chunks)
    
    raw_incidents = []
    seen_inc_ids = set()
    
    for i in range(0, num_points, chunk_size):
        chunk = route_polyline[i : i + chunk_size + 1]
        c_lats = [p[0] for p in chunk]
        c_lons = [p[1] for p in chunk]
        c_bbox = f"{min(c_lons)},{min(c_lats)},{max(c_lons)},{max(c_lats)}"
        
        chunk_incidents = fetch_traffic_incidents(c_bbox, api_key)
        for inc in chunk_incidents:
            inc_id = inc.get('properties', {}).get('id')
            if inc_id not in seen_inc_ids:
                raw_incidents.append(inc)
                seen_inc_ids.add(inc_id)
    
    corridor_incidents = []
    for inc in raw_incidents:
        geom = inc.get('geometry', {})
        coords = geom.get('coordinates', [])
        if not coords: continue
        
        # Check if incident is within 10km of ANY route point (optimized: check every 10th point)
        first_coord = coords[0] if isinstance(coords[0], list) else coords
        inc_lon, inc_lat = first_coord[0], first_coord[1]
        
        is_near = False
        for i in range(0, len(route_polyline), 10):
            rpt = route_polyline[i]
            if haversine_dist(inc_lat, inc_lon, rpt[0], rpt[1]) < 10:
                is_near = True
                break
        
        if is_near:
            props = inc.get('properties', {})
            events = props.get('events', [])
            desc = events[0].get('description', 'Unknown') if events else 'Unknown'
            raw_delay = props.get('delay', 0)
            delay = int(raw_delay) if raw_delay is not None else 0
            
            # Start Time Parsing
            start_time_str = props.get('startTime')
            mins_ago = 0
            if start_time_str:
                try:
                    st_time = pd.to_datetime(start_time_str, utc=True)
                    now = pd.Timestamp.now('UTC')
                    diff = now - st_time
                    mins_ago = int(diff.total_seconds() / 60)
                    if mins_ago < 0: mins_ago = 0
                except Exception:
                    pass
            
            icon_cat = props.get('iconCategory', 6)
            is_closed = (icon_cat == 0) or ("closed" in desc.lower()) or ("blocked" in desc.lower())
            
            # Classify Road (4-Tier System)
            road_numbers = props.get('roadNumbers', [])
            from_name = props.get('from', '')
            to_name = props.get('to', '')
            combined_names = (from_name + " " + to_name).lower()
            
            # Extract just the primary street name without the parenthetical intersections (e.g. "Hwy-11/Yonge St (Carlton St)" -> "Hwy-11/Yonge St")
            import re
            primary_from = re.sub(r'\(.*?\)', '', from_name).strip().lower()
            primary_to = re.sub(r'\(.*?\)', '', to_name).strip().lower()
            primary_names = primary_from + " " + primary_to
            
            # 1. Ramps & Exits (Crucial for logistics to distinguish from full highway closures)
            if any(kw in primary_names for kw in ['ramp', 'exit', 'sortie', 'interchange', 'bretelle']):
                road_class = "🔀 Highway Exit / Ramp"
            # 2. Major Highways: Must have an official number OR strongly match a highway keyword in the primary name
            elif road_numbers or any(kw in primary_names for kw in ['hwy', 'highway', 'expy', 'expressway', 'fwy', 'freeway', 'pkwy', 'parkway', 'autoroute', 'transcanadienne', '401', '400', '404', '407', 'qew', 'a-', 'on-', 'qc-']):
                road_class = "🛣️ Major Highway"
            # 3. Arterial Roads: Major city streets and regional routes
            elif any(kw in combined_names for kw in ['ave', 'avenue', 'blvd', 'boulevard', 'rd', 'road', 'st', 'street', 'rte', 'route', 'line', 'concession', 'county']):
                road_class = "🚙 Arterial Road"
            # 4. Local Streets: Everything else (drives, lanes, courts, crescents)
            else:
                road_class = "🏘️ Local Street"
            
            corridor_incidents.append({
                "Is Closed": is_closed,
                "Road Class": road_class,
                "Type": desc,
                "Delay (Mins)": str(round(delay/60, 1)) if not is_closed else "BLOCKAGE",
                "From": from_name if from_name else 'Unknown',
                "To": to_name if to_name else 'Unknown',
                "Started": mins_ago,
                "lat": inc_lat,
                "lon": inc_lon
            })
            
    return unique_stations, corridor_incidents

# --- PAGE 3: ROUTE ANALYSIS ---
def page_route_analysis():
    st.title("Logistics Weather: Route Analysis")
    st.markdown("Analyze weather and traffic corridor for specific shipping routes.")
    
    # Prepare city list for dropdown
    city_options = df['City'].sort_values().unique().tolist()
    
    col_in1, col_in2, col_btn = st.columns([2, 2, 1])
    with col_in1:
        origin_city = st.selectbox("Origin City", city_options, index=None, placeholder="Select start city...")
    with col_in2:
        dest_city = st.selectbox("Destination City", city_options, index=None, placeholder="Select end city...")
    with col_btn:
        st.write("##") # Spacer
        calculate = st.button("Analyze Route 🛣️")
        
    if calculate or "current_route" in st.session_state:
        if calculate:
            if not origin_city or not dest_city:
                st.error("Please select both an origin and a destination city.")
            elif origin_city == dest_city:
                st.error("Origin and destination must be different.")
            else:
                with st.spinner("Calculating route and safety corridor..."):
                    # Get coords directly from our dataframe
                    orig_row = df[df['City'] == origin_city].iloc[0]
                    dest_row = df[df['City'] == dest_city].iloc[0]
                    
                    orig = {"name": origin_city, "lat": orig_row['Latitude'], "lon": orig_row['Longitude']}
                    dest = {"name": dest_city, "lat": dest_row['Latitude'], "lon": dest_row['Longitude']}
                    
                    route_data = fetch_route(orig, dest, TOMTOM_API_KEY)
                    if route_data:
                        stations, incidents = get_corridor_data(route_data['polyline'], df, TOMTOM_API_KEY)
                        st.session_state.current_route = {
                            "orig": orig,
                            "dest": dest,
                            "polyline": route_data['polyline'],
                            "summary": route_data['summary'],
                            "stations": stations,
                            "incidents": incidents
                        }
                    else:
                        st.error(f"Could not calculate road route between {origin_city} and {dest_city}.")

        if "current_route" in st.session_state:
            rd = st.session_state.current_route
            
            # Summary Metrics
            dist_km = round(rd['summary'].get('lengthInMeters', 0) / 1000, 1)
            time_min = round(rd['summary'].get('travelTimeInSeconds', 0) / 60)
            
            met1, met2, met3 = st.columns(3)
            met1.metric("Trip Distance", f"{dist_km} km")
            met2.metric("Est. Travel Time", f"{time_min} mins")
            met3.metric("Waypoints Found", len(rd['stations']))
            
            st.divider()
            
            # Incident Filtering (Move above map)
            st.subheader("Route Safety Corridor")
            filtered_inc_df = pd.DataFrame()
            if rd['incidents']:
                inc_df = pd.DataFrame(rd['incidents'])
                
                # Safety check for 'Started' column (prevents KeyError from old session data)
                if 'Started' not in inc_df.columns:
                    inc_df['Started'] = 0
                
                with st.form("incident_filters_form"):
                    f_col1, f_col2, f_col3 = st.columns(3)
                    with f_col1:
                        type_options = sorted(inc_df['Type'].unique().tolist())
                        selected_type = st.multiselect("Filter incidents by Type", type_options, default=type_options)
                    with f_col2:
                        if 'Road Class' in inc_df.columns:
                            road_options = sorted(inc_df['Road Class'].unique().tolist())
                            selected_road = st.multiselect("Filter incidents by Road Class", road_options, default=road_options)
                        else:
                            selected_road = []
                    with f_col3:
                        time_options = ["Any Time", "Last 2 Hours", "Last 12 Hours", "Last 24 Hours", "Last 7 Days"]
                        selected_time = st.selectbox("Time Since Reported", time_options, index=1)
                    
                    submit_filters = st.form_submit_button("Apply Filters")
                
                # Convert time selection to minutes
                max_mins = float('inf')
                if selected_time == "Last 2 Hours": max_mins = 120
                elif selected_time == "Last 12 Hours": max_mins = 720
                elif selected_time == "Last 24 Hours": max_mins = 1440
                elif selected_time == "Last 7 Days": max_mins = 10080
                
                time_filtered_df = inc_df[inc_df['Started'] <= max_mins]
                
                if 'Road Class' in time_filtered_df.columns:
                    filtered_inc_df = time_filtered_df[(time_filtered_df['Type'].isin(selected_type)) & (time_filtered_df['Road Class'].isin(selected_road))]
                else:
                    filtered_inc_df = time_filtered_df[time_filtered_df['Type'].isin(selected_type)]
            
            # Map
            m = folium.Map(location=rd['polyline'][0], zoom_start=6)
            folium.PolyLine(rd['polyline'], color="#1C3F94", weight=5, opacity=0.8).add_to(m)
            
            # Origin/Dest Markers
            folium.Marker(rd['polyline'][0], tooltip="Origin", icon=folium.Icon(color='blue')).add_to(m)
            folium.Marker(rd['polyline'][-1], tooltip="Destination", icon=folium.Icon(color='red')).add_to(m)
            
            # Station Markers
            for s in rd['stations']:
                folium.CircleMarker(
                    location=[s['Latitude'], s['Longitude']],
                    radius=6, color='green', fill=True,
                    tooltip=f"Waypoint: {s['City']} ({s['Temperature (°C)']}°C)"
                ).add_to(m)
                
            # Incident Markers (Filtered)
            if not filtered_inc_df.empty:
                for idx, inc in filtered_inc_df.iterrows():
                    # Color based on Road Class hierarchy
                    rc = inc.get('Road Class', '')
                    if 'Major Highway' in rc:
                        m_color = 'red'
                    elif 'Exit / Ramp' in rc:
                        m_color = 'purple'
                    elif 'Arterial' in rc:
                        m_color = 'orange'
                    else:
                        m_color = 'lightblue'
                        
                    folium.Marker(
                        [inc['lat'], inc['lon']],
                        icon=folium.Icon(color=m_color, icon='info-sign'),
                        tooltip=f"{rc}: {inc['Type']}"
                    ).add_to(m)
            
            st_folium(m, width=1200, height=500)
            
            st.divider()
            
            # Weather Waypoints Cards
            st.subheader("Weather Corridor (Step-by-Step)")
            w_cols = st.columns(len(rd['stations']))
            for i, s in enumerate(rd['stations']):
                with w_cols[i]:
                    st.markdown(f"**{s['City']}**")
                    st.metric("Temp", f"{s['Temperature (°C)']}°C")
                    st.write(f"_{s['Condition']}_")
                    
                    # Core Metrics Vertical View
                    wind_spd = s.get('Wind Speed (km/h)')
                    wind_dir = s.get('Wind Dir')
                    wind_str = f"{wind_spd} km/h {wind_dir or ''}".strip() if pd.notna(wind_spd) else "N/A"
                    
                    # Snow/Rain Detection
                    cond_text = s['Condition'].lower()
                    precip_icon = "❄️" if "snow" in cond_text else "☔" if "rain" in cond_text or "shower" in cond_text else ""
                    
                    st.write(f"💨 **Wind:** {wind_str}")
                    st.write(f"💧 **Humidity:** {s.get('Humidity (%)')}%" if pd.notna(s.get('Humidity (%)')) else "💧 **Humidity:** N/A")
                    
                    # Extract precip from forecast if available
                    props = s.get('RawProperties', {})
                    forecasts = props.get('forecastGroup', {}).get('forecasts', [])
                    precip_info = "None"
                    if forecasts:
                        first_f = forecasts[0]
                        # Try to find POP (Probability of Precipitation)
                        import re
                        txt = first_f.get('textSummary', {}).get('en', '')
                        match = re.search(r"(\d+)\s*percent\s*chance", txt, re.IGNORECASE)
                        if match:
                            precip_info = f"{match.group(1)}% Chance"
                        elif "snow" in txt.lower() or "rain" in txt.lower():
                            precip_info = "Likely"
                    
                    st.write(f"{precip_icon or '☁️'} **Precipitation:** {precip_info}")
                    
                    if s['Has Alert']:
                        st.warning(f"⚠️ {s['Alerts']}")
                        
            st.divider()
            
            # Incidents Table (Already Filtered)
            st.subheader("Traffic Incidents Detail Table")
            if not filtered_inc_df.empty:
                # Sort Ascending by Started time
                display_df = filtered_inc_df.sort_values(by="Started", ascending=True)
                
                st.dataframe(
                    display_df.drop(columns=['lat', 'lon', 'Is Closed']),
                    width='stretch',
                    column_config={
                        "Started": st.column_config.NumberColumn(
                            "Started",
                            help="How long ago the incident was reported",
                            format="%d mins ago"
                        )
                    }
                )
            elif rd['incidents']:
                st.info("No incidents match the selected filters.")
            else:
                st.success("No significant traffic incidents detected on this route.")

# --- MAIN NAVIGATION ---
tab_regional, tab_city, tab_route = st.tabs(["🗺️ Regional Overview", "🏙️ City Details", "🛣️ Route Analysis"])

with tab_regional:
    page_regional_overview()

with tab_city:
    page_city_details()

with tab_route:
    page_route_analysis()
