import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px

# --- PAGE CONFIG ---
st.set_page_config(page_title="Purolator Weather Dashboard", layout="wide", page_icon="🌤️")
st.title("Logistics Weather Dashboard")

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
        temp = curr.get('temperature', {}).get('value', {}).get('en') if isinstance(curr.get('temperature', {}).get('value'), dict) else curr.get('temperature', {}).get('value')
        wind_speed = curr.get('wind', {}).get('speed', {}).get('value', {}).get('en') if isinstance(curr.get('wind', {}).get('speed', {}).get('value'), dict) else curr.get('wind', {}).get('speed', {}).get('value')
        condition = curr.get('condition', {}).get('en', 'Unknown')
        visibility = curr.get('visibility', {}).get('value', {}).get('en') if isinstance(curr.get('visibility', {}).get('value'), dict) else curr.get('visibility', {}).get('value')
        
        # Alerts
        warnings = props.get('warnings', [])
        active_alerts = [w.get('type', {}).get('en', 'Alert') for w in warnings if w]
        has_alert = len(active_alerts) > 0
        
        cities.append({
            'City': city_name,
            'Latitude': lat,
            'Longitude': lon,
            'Temperature (°C)': temp,
            'Wind Speed (km/h)': wind_speed,
            'Condition': condition,
            'Visibility (km)': visibility,
            'Alerts': ", ".join(active_alerts) if has_alert else "None",
            'Has Alert': has_alert,
            'RawProperties': props
        })
        
    return pd.DataFrame(cities)

# --- SIDEBAR & REFRESH ---
with st.sidebar:
    st.header("Controls")
    if st.button("Refresh Data 🔄"):
        fetch_weather_data.clear()
        st.rerun()
        
    st.subheader("Filters")

# Main execution
with st.spinner("Fetching latest weather data across Canada..."):
    raw_data = fetch_weather_data()
df = process_geojson(raw_data)

if df.empty:
    st.warning("No data available.")
    st.stop()

# Populate Sidebar Filters
show_alerts_only = st.sidebar.checkbox("🚨 Show only cities with active alerts", value=False)

# Apply Filters
filtered_df = df[df['Has Alert'] == True] if show_alerts_only else df

# --- MAP VISUALIZATION ---
st.subheader("Regional Overview")
st.markdown("Use the layer control icon (top right of map) to toggle Weather Radar and Satellite Imagery.")

# Initialize map centered on Canada
m = folium.Map(location=[56.1304, -106.3468], zoom_start=4)

# Add WMS Layers from GeoMet
folium.WmsTileLayer(
    url="https://geo.weather.gc.ca/geomet",
    layers="RADAR_1KM_RRSKS", # Weather Radar Composite
    fmt="image/png",
    transparent=True,
    name="Weather Radar",
    overlay=True,
    control=True,
    show=False
).add_to(m)

folium.WmsTileLayer(
    url="https://geo.weather.gc.ca/geomet",
    layers="GOES-16", # Satellite placeholder (Note: exact layer name varies, using standard)
    fmt="image/png",
    transparent=True,
    name="Satellite Imagery",
    overlay=True,
    control=True,
    show=False
).add_to(m)

# Add markers for cities
for idx, row in filtered_df.iterrows():
    # Color coding logic
    marker_color = 'red' if row['Has Alert'] else 'green'
    if not row['Has Alert'] and row['Temperature (°C)'] is not None and row['Temperature (°C)'] < -15:
        marker_color = 'orange' # Cold/icy conditions warning
        
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
map_data = st_folium(m, width=1200, height=500, returned_objects=["last_object_clicked"])

# --- DRILL DOWN VIEW ---
st.divider()
st.subheader("City Details & Forecast")

selected_city = None

# Logic to select city from map click
if map_data and map_data.get("last_object_clicked"):
    clicked_lat = map_data["last_object_clicked"]["lat"]
    clicked_lon = map_data["last_object_clicked"]["lng"]
    
    if not filtered_df.empty:
        filtered_df['dist'] = ((filtered_df['Latitude'] - clicked_lat)**2 + (filtered_df['Longitude'] - clicked_lon)**2)**0.5
        closest_city_row = filtered_df.loc[filtered_df['dist'].idxmin()]
        if closest_city_row['dist'] < 0.2: 
            selected_city = closest_city_row['City']

# Fallback/Manual Selectbox
city_list = filtered_df['City'].sort_values().tolist()
selected_index = city_list.index(selected_city) if selected_city in city_list else 0
selected_city = st.selectbox("Select a city for detailed forecast:", city_list, index=selected_index)

if selected_city:
    city_data = filtered_df[filtered_df['City'] == selected_city].iloc[0]
    
    # --- Metrics Dashboard ---
    cols = st.columns(5)
    cols[0].metric("Temperature", f"{city_data['Temperature (°C)']} °C" if pd.notna(city_data['Temperature (°C)']) else "N/A")
    cols[1].metric("Wind", f"{city_data['Wind Speed (km/h)']} km/h" if pd.notna(city_data['Wind Speed (km/h)']) else "N/A")
    cols[2].metric("Condition", city_data['Condition'])
    cols[3].metric("Visibility", f"{city_data['Visibility (km)']} km" if pd.notna(city_data['Visibility (km)']) else "N/A")
    # For Snow/Ice/Precip, if not directly in current conditions, they often appear in condition text or forecasts.
    
    if city_data['Has Alert']:
        st.error(f"🚨 **ACTIVE WEATHER ALERTS:** {city_data['Alerts']}")
        
    props = city_data['RawProperties']
    
    # --- Hourly Forecast ---
    st.write("### Hourly Forecast")
    hourly_data = props.get('hourlyForecastGroup', {}).get('hourlyForecasts', [])
    if hourly_data:
        h_times = []
        h_temps = []
        h_conds = []
        for h in hourly_data:
            # Try to find a readable time label
            time_obj = h.get('dateTime', [])
            time_label = time_obj[1].get('textSummary', 'Unknown') if len(time_obj) > 1 else 'Unknown'
            temp_val = h.get('temperature', {}).get('value')
            temp = temp_val.get('en') if isinstance(temp_val, dict) else temp_val
            cond = h.get('condition', {}).get('en', '')
            
            h_times.append(time_label)
            h_temps.append(temp)
            h_conds.append(cond)
            
        fig = px.line(
            x=range(len(h_temps)), # Using index for x-axis to keep it ordered
            y=h_temps, 
            markers=True, 
            title="Hourly Temperature Trend",
            labels={'x': 'Hours from now', 'y': 'Temperature (°C)'}
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Hourly forecast data is currently unavailable for this location.")
        
    # --- Daily Forecast ---
    st.write("### Daily Forecast (Up to 15 Days)")
    daily_data = props.get('forecastGroup', {}).get('forecasts', [])
    if daily_data:
        d_df = []
        for d in daily_data:
            temp_obj = d.get('temperatures', {}).get('temperature', [])
            temp_val = 'N/A'
            if temp_obj and isinstance(temp_obj, list) and len(temp_obj) > 0:
                t_v = temp_obj[0].get('value')
                temp_val = t_v.get('en') if isinstance(t_v, dict) else t_v
                
            d_df.append({
                'Period': d.get('period', {}).get('textForecastName', {}).get('en', 'Unknown'),
                'Forecast': d.get('textSummary', {}).get('en', 'Unknown'),
                'Temp': temp_val
            })
        st.dataframe(pd.DataFrame(d_df), use_container_width=True)
    else:
        st.info("Daily forecast data is currently unavailable for this location.")