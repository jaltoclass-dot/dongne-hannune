import math
import requests
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
from streamlit_geolocation import streamlit_geolocation

st.set_page_config(page_title="동네한눈에", page_icon="📍", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; max-width: 1250px;}
.main-title {font-size:2.2rem;font-weight:800;margin-bottom:0;}
.sub-title {color:#64748b;margin-top:.2rem;margin-bottom:1.2rem;}
div[data-testid="stMetric"] {background:#f8fafc;padding:12px;border-radius:12px;}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-title">📍 동네한눈에</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">내 주변 생활 편의시설을 한 지도에서 찾아보세요.</p>', unsafe_allow_html=True)

CATEGORIES = {
    "공중화장실": {"filters": ['["amenity"="toilets"]'], "color": "blue", "icon": "info-sign"},
    "편의점": {"filters": ['["shop"="convenience"]'], "color": "green", "icon": "shopping-cart"},
    "주차장": {"filters": ['["amenity"="parking"]'], "color": "orange", "icon": "road"},
    "ATM": {"filters": ['["amenity"="atm"]'], "color": "purple", "icon": "credit-card"},
    "무료 와이파이": {"filters": ['["internet_access"="wlan"]["internet_access:fee"="no"]', '["internet_access"="wlan"]["fee"="no"]'], "color": "cadetblue", "icon": "signal"},
    "약국": {"filters": ['["amenity"="pharmacy"]'], "color": "pink", "icon": "plus"},
    "병원·의원": {"filters": ['["amenity"="hospital"]', '["healthcare"="hospital"]', '["amenity"="clinic"]'], "color": "red", "icon": "plus-sign"},
    # 일반 자판기·티켓 발권기가 섞이지 않도록 이름에 민원 관련 단어가 있는 시설만 검색
    "무인민원발급기": {"filters": ['["name"~"무인민원|민원발급|무인발급"]'], "color": "darkblue", "icon": "print"}
}
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter"
]

def haversine(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2-lat1)
    dl = math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.atan2(math.sqrt(a), math.sqrt(1-a))

def make_query(lat, lon, radius, selected):
    clauses = []
    for category in selected:
        for filt in CATEGORIES[category]["filters"]:
            clauses.append(f'nwr(around:{radius},{lat},{lon}){filt};')
    return "[out:json][timeout:35];(" + "".join(clauses) + ");out center tags;"

@st.cache_data(ttl=600, show_spinner=False)
def fetch_places(lat, lon, radius, selected_tuple):
    query = make_query(lat, lon, radius, list(selected_tuple))
    headers = {"User-Agent": "DongneHannuneStudentProject/1.0 (educational map)"}
    last_error = None
    for url in OVERPASS_URLS:
        try:
            response = requests.post(url, data={"data": query}, headers=headers, timeout=50)
            response.raise_for_status()
            payload = response.json()
            rows = []
            for el in payload.get("elements", []):
                tags = el.get("tags", {})
                if el.get("type") == "node":
                    plat, plon = el.get("lat"), el.get("lon")
                else:
                    center = el.get("center", {})
                    plat, plon = center.get("lat"), center.get("lon")
                if plat is None or plon is None:
                    continue

                matched = []
                for category in selected_tuple:
                    # 검색 조건과 동일한 태그 기준으로 분류해 엉뚱한 시설이 섞이지 않게 합니다.
                    if category == "공중화장실" and tags.get("amenity") == "toilets":
                        matched.append(category)
                    elif category == "편의점" and tags.get("shop") == "convenience":
                        matched.append(category)
                    elif category == "주차장" and tags.get("amenity") == "parking":
                        matched.append(category)
                    elif category == "ATM" and tags.get("amenity") == "atm":
                        matched.append(category)
                    elif category == "무료 와이파이" and tags.get("internet_access") == "wlan" and (tags.get("internet_access:fee") == "no" or tags.get("fee") == "no"):
                        matched.append(category)
                    elif category == "약국" and tags.get("amenity") == "pharmacy":
                        matched.append(category)
                    elif category == "병원·의원" and (tags.get("amenity") in ("hospital", "clinic") or tags.get("healthcare") == "hospital"):
                        matched.append(category)
                    elif category == "무인민원발급기" and any(
                        word in (tags.get("name", "") + " " + tags.get("name:ko", ""))
                        for word in ("무인민원", "민원발급", "무인발급")
                    ):
                        matched.append(category)
                if not matched:
                    continue
                name = tags.get("name") or tags.get("name:ko") or matched[0] + " (이름 미등록)"
                address = " ".join(filter(None, [
                    tags.get("addr:postcode"), tags.get("addr:city"), tags.get("addr:district"),
                    tags.get("addr:street"), tags.get("addr:housenumber")
                ])) or "주소 정보 미등록"
                rows.append({
                    "id": f'{el.get("type")}/{el.get("id")}',
                    "name": name, "category": ", ".join(matched),
                    "lat": float(plat), "lon": float(plon), "address": address,
                    "hours": tags.get("opening_hours", "운영시간 정보 미등록"),
                    "distance": haversine(lat, lon, float(plat), float(plon)),
                    "osm_url": f'https://www.openstreetmap.org/{el.get("type")}/{el.get("id")}'
                })
            result = pd.DataFrame(rows)
            if not result.empty:
                result = result.drop_duplicates(subset=["id"]).sort_values("distance")
            return result
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"주변 시설 데이터를 가져오지 못했습니다: {last_error}")

with st.sidebar:
    st.header("🔎 검색 설정")
    st.caption("GPS 위치는 브라우저 권한을 허용해야 사용할 수 있습니다.")
    gps = streamlit_geolocation()
    if gps and gps.get("latitude") is not None and gps.get("longitude") is not None:
        st.session_state["gps_lat"] = float(gps["latitude"])
        st.session_state["gps_lon"] = float(gps["longitude"])
        st.success("현재 위치를 확인했습니다.")
        st.caption(f"위치 정확도: 약 {gps.get('accuracy', '정보 없음')}m")
    else:
        st.info("아래에 좌표를 입력하면 GPS 없이도 테스트할 수 있습니다.")

    default_lat = st.session_state.get("gps_lat", 37.5665)
    default_lon = st.session_state.get("gps_lon", 126.9780)
    lat = st.number_input("위도", value=float(default_lat), format="%.6f")
    lon = st.number_input("경도", value=float(default_lon), format="%.6f")
    radius = st.select_slider("검색 반경", options=[300, 500, 1000, 2000, 3000, 5000], value=1000, format_func=lambda x: f"{x:,}m")
    selected = st.multiselect("시설 종류", list(CATEGORIES.keys()), default=list(CATEGORIES.keys()))
    search = st.button("주변 시설 검색", type="primary", use_container_width=True)
    st.caption("검색 데이터: OpenStreetMap 커뮤니티 지도 데이터")
    st.caption("※ 시설 분류는 지도에 등록된 태그를 기준으로 하며, 정보가 없거나 잘못 등록된 시설은 검색되지 않을 수 있습니다.")

if "places" not in st.session_state:
    st.session_state["places"] = None

if search:
    if not selected:
        st.warning("검색할 시설 종류를 하나 이상 선택하세요.")
        st.session_state["places"] = None
    else:
        try:
            with st.spinner("주변 시설을 검색하고 있습니다..."):
                st.session_state["places"] = fetch_places(lat, lon, radius, tuple(selected))
            st.session_state["last_search"] = (lat, lon, radius, tuple(selected))
        except Exception as exc:
            st.error(str(exc))
            st.info("잠시 후 다시 시도하거나 검색 반경을 줄여주세요. 공공 Overpass 서버는 혼잡할 수 있습니다.")

last = st.session_state.get("last_search")
if st.session_state["places"] is None:
    st.info("왼쪽에서 GPS 위치를 허용하거나 좌표를 입력한 뒤 '주변 시설 검색'을 눌러주세요.")
    st.markdown("**사용 방법**")
    st.markdown("1. GPS 버튼을 눌러 위치 권한을 허용합니다.  \n2. 검색 반경과 시설 종류를 선택합니다.  \n3. 주변 시설 검색을 누르면 지도와 목록이 표시됩니다.")
else:
    places = st.session_state["places"]
    count = len(places)
    a, b, c = st.columns(3)
    a.metric("검색된 시설", f"{count:,}개")
    b.metric("검색 반경", f"{last[2]:,}m")
    c.metric("선택 시설", f"{len(last[3])}종")

    map_obj = folium.Map(location=[last[0], last[1]], zoom_start=15, control_scale=True)
    folium.Circle([last[0], last[1]], radius=last[2], color="#2563eb", fill=True, fill_opacity=0.06).add_to(map_obj)
    folium.Marker([last[0], last[1]], tooltip="내 위치", popup="검색 기준 위치",
                  icon=folium.Icon(color="red", icon="user")).add_to(map_obj)

    if not places.empty:
        for _, row in places.iterrows():
            category = row["category"].split(", ")[0]
            style = CATEGORIES.get(category, {"color": "gray", "icon": "info-sign"})
            popup = f"""<b>{row['name']}</b><br>
            종류: {row['category']}<br>
            거리: {row['distance']:.0f}m<br>
            주소: {row['address']}<br>
            운영시간: {row['hours']}<br>
            <a href="{row['osm_url']}" target="_blank">OpenStreetMap에서 보기</a>"""
            folium.Marker([row["lat"], row["lon"]], tooltip=row["name"],
                          popup=folium.Popup(popup, max_width=300),
                          icon=folium.Icon(color=style["color"], icon=style["icon"])).add_to(map_obj)

    st.subheader("🗺️ 주변 편의시설 지도")
    st_folium(map_obj, use_container_width=True, height=520, key="facility_map")

    st.subheader("📋 가까운 시설 목록")
    if places.empty:
        st.warning("검색된 시설이 없습니다. 반경을 넓히거나 다른 시설 종류를 선택해보세요.")
    else:
        view = places[["name", "category", "distance", "address", "hours", "osm_url"]].copy()
        view["distance"] = view["distance"].round().astype(int).astype(str) + "m"
        view.columns = ["시설명", "종류", "거리", "주소", "운영시간", "지도 링크"]
        st.dataframe(view, use_container_width=True, hide_index=True,
                     column_config={"지도 링크": st.column_config.LinkColumn("지도 링크")})
        st.download_button("검색 결과 CSV 다운로드",
                           data=places.to_csv(index=False).encode("utf-8-sig"),
                           file_name="동네한눈에_검색결과.csv",
                           mime="text/csv")

st.divider()
st.caption("데이터 출처: © OpenStreetMap contributors. 시설 정보는 이용자 기여 데이터로 누락·오류·변경이 있을 수 있습니다. 방문 전 운영 여부를 확인하세요.")
