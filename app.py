import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY")

# --- PAGE CONFIG ---
st.set_page_config(page_title="Purolator Weather Dashboard", layout="wide", page_icon="🌤️")

# --- DATA FETCHING ---
API_URL = "https://api.weather.gc.ca/collections/citypageweather-realtime/items?f=json&limit=500"

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

# --- SIDEBAR & REFRESH ---
with st.sidebar:
    st.header("Controls")
    if st.button("Refresh Data 🔄"):
        fetch_weather_data.clear()
        raw_data = fetch_weather_data()
        st.session_state.df = process_geojson(raw_data)
        st.rerun()

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
        "fields": "{incidents{properties{id,iconCategory,magnitudeOfDelay,events{description,code},startTime,endTime,from,to,length,delay}}}",
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
    
    zone_data = ZONES[selected_zone]

    show_alerts_only = st.sidebar.checkbox("🚨 Show only cities with active alerts", value=False)
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
        marker_color = 'red' if row['Has Alert'] else 'green'
        if not row['Has Alert'] and row['Temperature (°C)'] is not None and row['Temperature (°C)'] < -15:
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
                events = props.get('events', [])
                desc = events[0].get('description', 'Unknown') if events else 'Unknown Incident'
                
                # Ensure we have numbers, not None
                raw_delay = props.get('delay')
                delay_sec = int(raw_delay) if raw_delay is not None else 0
                
                raw_length = props.get('length')
                length_m = int(raw_length) if raw_length is not None else 0
                
                # Only show impactful incidents (e.g. > 60 sec delay or closures)
                if delay_sec > 60 or props.get('iconCategory') == 0:
                    parsed_incidents.append({
                        "Type/Location": f"{desc} from {props.get('from', 'Unknown')} to {props.get('to', 'Unknown')}",
                        "Delay (Mins)": round(delay_sec / 60, 1),
                        "Length (km)": round(length_m / 1000, 2),
                        "Severity": props.get('magnitudeOfDelay', 0)
                    })
                    
            if parsed_incidents:
                inc_df = pd.DataFrame(parsed_incidents)
                # Sort by highest delay
                inc_df = inc_df.sort_values(by="Delay (Mins)", ascending=False).reset_index(drop=True)
                st.dataframe(inc_df, use_container_width=True)
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
        
        cols[0].metric("Temperature", f"{city_data['Temperature (°C)']} °C" if pd.notna(city_data['Temperature (°C)']) else "N/A")
        cols[1].metric("Condition", city_data['Condition'])
        cols[2].metric("Wind", wind_str)
        cols[3].metric("Visibility", f"{city_data['Visibility (km)']} km" if pd.notna(city_data['Visibility (km)']) else "N/A")
        cols[4].metric("Humidity", f"{city_data.get('Humidity (%)')}%" if pd.notna(city_data.get('Humidity (%)')) else "N/A")
        
        # Advanced Metrics
        st.write("#### Additional Metrics")
        cols2 = st.columns(5)
        
        wind_chill = city_data.get('Wind Chill')
        cols2[0].metric("Wind Chill / Humidex", f"{wind_chill} °C" if pd.notna(wind_chill) else "N/A")
        
        dewpoint = city_data.get('Dewpoint (°C)')
        cols2[1].metric("Dewpoint", f"{dewpoint} °C" if pd.notna(dewpoint) else "N/A")
        
        wind_gust = city_data.get('Wind Gust')
        cols2[2].metric("Wind Gust", f"{wind_gust} km/h" if pd.notna(wind_gust) else "N/A")
        
        pressure = city_data.get('Pressure (kPa)')
        pressure_tend = city_data.get('Pressure Tendency')
        press_str = f"{pressure} kPa" if pd.notna(pressure) else "N/A"
        cols2[3].metric("Pressure", press_str, delta=pressure_tend if pressure_tend else None, delta_color="off")
        
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
                labels={'x': 'Hours from now', 'y': 'Temperature (°C)'}
            )
            st.plotly_chart(fig, use_container_width=True)
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
                    
                d_df.append({
                    'Period': d.get('period', {}).get('textForecastName', {}).get('en', 'Unknown'),
                    'Forecast': d.get('textSummary', {}).get('en', 'Unknown'),
                    'Temp (°C)': temp_val,
                    'Precipitation': precip_str
                })
            st.dataframe(pd.DataFrame(d_df), use_container_width=True)
        else:
            st.info("Daily forecast data is currently unavailable for this location.")

# --- NAVIGATION ---
pg = st.navigation([
    st.Page(page_regional_overview, title="Regional Overview", icon="🗺️"),
    st.Page(page_city_details, title="City Details", icon="🏙️")
])

pg.run()
