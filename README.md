# Purolator Network Weather Command Center

A map-first Streamlit dashboard that combines Canadian weather alerts, traffic
incidents, priority hubs, and linehaul corridors into one national operating
picture.

The landing screen is designed for directors: it answers where the highest
risks are, how serious they are, and which configured network assets may be
affected. Analysts can inspect forecasts, traffic details, and truck-aware route
impact without leaving the dashboard.

## Features

- National risk KPIs and ranked priority alerts
- Toronto-first full-width map with viewport-synchronized KPIs and alerts
- Clickable and clustered risk markers with persistent selected context
- Environment Canada alert polygons, radar, satellite, and precipitation layers
- TomTom traffic incidents and optional traffic-flow tiles
- Configurable hubs, expanded planning corridors, risk thresholds, and truck profile
- `Critical`, `High`, `Moderate`, and `Low` operational risk scoring
- Saved-lane and custom Canadian city-pair route analysis
- Route weather waypoints, nearby incidents, and route-specific severity
- Five-minute automatic refresh with stale and partial-outage states
- Last-successful data preservation within the active Streamlit session

## Architecture

`app.py` is the Streamlit coordinator. The `weather_dashboard` package contains:

- `providers/`: Environment Canada, TomTom Traffic, and TomTom Routing adapters
- `models.py`: normalized provider-independent records
- `risk.py`: network impact matching and risk scoring
- `geo.py`: distance, corridor, and traffic-scan calculations
- `viewport.py`: Toronto defaults and visible-map risk filtering
- `routes.py`: saved and custom route request construction
- `route_analysis.py`: route weather sampling and incident matching
- `map_view.py`: Folium map and layer construction
- `ui.py`: reusable visual components and dashboard styling
- `config.py`: versioned application and network configuration loading

Provider JSON is normalized at the adapter boundary. UI and risk logic do not
depend on deeply nested API response shapes.

## Setup

Requires Python 3.12 and `uv`.

```bash
uv sync
```

Create `.streamlit/secrets.toml`:

```toml
TOMTOM_API_KEY = "your-api-key"
```

Run the dashboard:

```bash
uv run streamlit run app.py
```

The app remains usable with weather data only when TomTom is unavailable, but
traffic and truck-route features will be marked as degraded.

## Network Configuration

Edit `config/network.json` to replace the planning defaults with approved
Purolator data:

- Hubs: identifier, display name, province, coordinates, and priority
- Corridors: origin/destination hubs, priority, and intermediate scan points
- Truck profile: commercial vehicle dimensions, weight, axles, and speed

The coordinates currently committed are broad planning locations and are not
authoritative facility records. The saved route list contains 18 planning lanes;
custom routing can use configured hubs or any Canadian city exposed by the
weather dataset.

Edit `config/settings.json` for:

- Provider URLs
- Timeouts and cache durations
- Stale-data threshold
- Risk severity thresholds
- Environment Canada `User-Agent`

Use an operational contact in the `User-Agent` before production deployment.

## Data Sources

- [Environment Canada City Page Weather](https://api.weather.gc.ca/collections/citypageweather-realtime)
- [MSC Open Data usage policy](https://eccc-msc.github.io/open-data/usage-policy/readme_en/)
- [TomTom Traffic Incident Details](https://developer.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-incidents/incident-details)
- [TomTom Calculate Route](https://developer.tomtom.com/routing-api/documentation/tomtom-maps/calculate-route)

The Environment Canada City Page Weather collection is experimental. Its
adapter validates required fields and tolerates missing optional fields.

## Testing

Run the standard-library test suite:

```bash
uv run python -m unittest discover -s tests -v
```

The tests cover provider parsing, TomTom closure semantics, incident
deduplication, truck routing parameters, viewport filtering, Toronto defaults,
saved/custom route construction, route weather sampling, geographic matching,
risk ranking, and schema variation.

## Troubleshooting

- **Weather unavailable on first load:** verify access to `api.weather.gc.ca`.
  No fallback exists until the session has one successful response.
- **Traffic degraded:** confirm `TOMTOM_API_KEY` exists and has Traffic and
  Routing API access.
- **Few traffic incidents:** the app intentionally queries only configured
  hubs and corridor scan points to bound API usage.
- **Unexpected risk ranking:** review priorities and thresholds in `config/`.
- **Map feels busy:** disable optional radar, satellite, precipitation, or
  traffic-flow layers from the layer control.
