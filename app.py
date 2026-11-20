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
.block-container {padding-top: 1.2rem; max-width: 1250px;}
.main-title {font-size:2.2rem;font-weight:850;color:#172554;margin-bottom:0;}
.sub-title {color:#64748b;margin-top:.25rem;margin-bottom:1rem;}
section[data-testid="stSidebar"] {border-right:1px solid #e2e8f0;}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-title">📍 동네한눈에</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">내 주변 생활 편의시설을 지도와 목록으로 찾아보세요.</p>', unsafe_allow_html=True)
st.caption("공중화장실 · 편의점 · 주차장 · ATM · 무료 와이파이 · 약국 · 병원·의원 · 무인민원발급기")

CATEGORIES = {
    "공중화장실": {"filters": ['["amenity"="toilets"]'], "color": "blue"},
    "편의점": {"filters": ['["shop"="convenience"]'], "color": "green"},
    "주차장": {"filters": ['["amenity"="parking"]'], "color": "orange"},
    "ATM": {"filters": ['["amenity"="atm"]'], "color": "purple"},
    "무료 와이파이": {"filters": ['["internet_access"="wlan"]["internet_access:fee"="no"]', '["internet_access"="wlan"]["fee"="no"]'], "color": "cadetblue"},
    "약국": {"filters": ['["amenity"="pharmacy"]'], "color": "pink"},
    "병원·의원": {"filters": ['["amenity"="hospital"]', '["healthcare"="hospital"]', '["amenity"="clinic"]'], "color": "red"},
    "무인민원발급기": {"filters": ['["name"~"무인민원|민원발급|무인발급"]'], "color": "darkblue"},
}

# 공공 서버가 한 곳에서 지연되면 다음 서버로 빠르게 넘어갑니다.
OVERPASS_URLS = [
   OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

def haversine(lat1, lon1, lat2, lon2):
    earth = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2)**2
    return 2 * earth * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def make_query(lat, lon, radius, selected):
    clauses = []
    for category in selected:
        for tag_filter in CATEGORIES[category]["filters"]:
            clauses.append(f'nwr(around:{radius},{lat},{lon}){tag_filter};')
    return '[out:json][timeout:20];(' + ''.join(clauses) + ');out center tags;'

@st.cache_data(ttl=1800, max_entries=100, show_spinner=False)
def fetch_places(lat, lon, radius, selected_tuple):
    query = make_query(lat, lon, radius, list(selected_tuple))
    headers = {"User-Agent": "DongneHannuneStudentProject/2.0"}
    errors = []

    for url in OVERPASS_URLS:
        try:
            response = requests.post(
                url, data={"data": query}, headers=headers,
                timeout=(8, 25)
            )
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
                    tags.get("addr:city"), tags.get("addr:district"),
                    tags.get("addr:street"), tags.get("addr:housenumber")
                ])) or "주소 정보 미등록"
                rows.append({
                    "id": f'{el.get("type")}/{el.get("id")}',
                    "name": name,
                    "category": ", ".join(matched),
                    "lat": float(plat),
                    "lon": float(plon),
                    "address": address,
                    "hours": tags.get("opening_hours", "운영시간 정보 미등록"),
                    "distance": haversine(lat, lon, float(plat), float(plon)),
                    "osm_url": f'https://www.openstreetmap.org/{el.get("type")}/{el.get("id")}'
                })

            result = pd.DataFrame(rows)
            if not result.empty:
                result = result.drop_duplicates(subset=["id"]).sort_values("distance").reset_index(drop=True)
            return result

        except Exception as exc:
            errors.append(f"{url}: {exc}")

    raise RuntimeError("공공 지도 데이터 서버가 응답하지 않습니다. 잠시 후 다시 시도해 주세요.\n" + "\n".join(errors))

with st.sidebar:
    st.header("🔎 검색 설정")
    gps = streamlit_geolocation()
    if gps and gps.get("latitude") is not None and gps.get("longitude") is not None:
        st.session_state["gps_lat"] = float(gps["latitude"])
        st.session_state["gps_lon"] = float(gps["longitude"])
        st.success("현재 위치를 확인했습니다.")
    else:
        st.caption("GPS 권한을 허용하거나 좌표를 직접 입력하세요.")

    lat = st.number_input("위도", value=float(st.session_state.get("gps_lat", 37.5665)), format="%.6f")
    lon = st.number_input("경도", value=float(st.session_state.get("gps_lon", 126.9780)), format="%.6f")
    radius = st.select_slider("검색 반경", options=[300, 500, 1000, 2000, 3000], value=500,
                              format_func=lambda x: f"{x:,}m")
    selected = st.multiselect("시설 종류", list(CATEGORIES.keys()),
                              default=["공중화장실", "편의점"])
    search = st.button("주변 시설 검색", type="primary", use_container_width=True)
    st.caption("처음에는 시설 1~2종류, 반경 500~1,000m로 검색하는 것을 권장합니다.")

if "places" not in st.session_state:
    st.session_state["places"] = None

if search:
    if not selected:
        st.warning("시설 종류를 하나 이상 선택하세요.")
    else:
        try:
            with st.spinner("주변 시설을 검색하고 있습니다. 잠시만 기다려 주세요."):
                st.session_state["places"] = fetch_places(lat, lon, radius, tuple(selected))
                st.session_state["last_search"] = (lat, lon, radius, tuple(selected))
        except Exception as exc:
            st.error(str(exc))
            st.info("검색 반경을 줄이거나 시설 종류를 1개만 선택해 다시 시도해 보세요.")

last = st.session_state.get("last_search")
if st.session_state["places"] is None:
    st.info("왼쪽에서 위치와 시설 종류를 선택한 뒤 '주변 시설 검색'을 눌러주세요.")
else:
    places = st.session_state["places"]
    st.metric("검색된 시설", f"{len(places):,}개")
    map_obj = folium.Map(location=[last[0], last[1]], zoom_start=15, control_scale=True)
    folium.Circle([last[0], last[1]], radius=last[2], color="#2563eb",
                  fill=True, fill_opacity=0.05).add_to(map_obj)
    folium.Marker([last[0], last[1]], tooltip="검색 기준 위치",
                  icon=folium.Icon(color="red", icon="user")).add_to(map_obj)

    # 지도 마커가 너무 많아지는 것을 막고, 전체 결과는 표에서 확인하도록 합니다.
    map_places = places.head(100)
    for _, row in map_places.iterrows():
        category = row["category"].split(", ")[0]
        color = CATEGORIES.get(category, {}).get("color", "blue")
        popup = (
            f"<b>{row['name']}</b><br>종류: {row['category']}<br>"
            f"거리: {row['distance']:.0f}m<br>주소: {row['address']}<br>"
            f"<a href='{row['osm_url']}' target='_blank'>OpenStreetMap에서 보기</a>"
        )
        folium.Marker(
            [row["lat"], row["lon"]],
            tooltip=row["name"],
            popup=folium.Popup(popup, max_width=280),
            icon=folium.Icon(color=color, icon="info-sign")
        ).add_to(map_obj)

    st.subheader("🗺️ 주변 시설 지도")
    if len(places) > 100:
        st.caption(f"지도에는 가까운 100개 시설만 표시하고, 아래 목록에는 전체 {len(places)}개를 표시합니다.")
    st_folium(map_obj, use_container_width=True, height=480, key="facility_map")

    st.subheader("📋 가까운 시설 목록")
    if places.empty:
        st.warning("선택한 조건에서 검색된 시설이 없습니다. 반경을 넓히거나 다른 시설을 선택해 보세요.")
    else:
        view = places[["name", "category", "distance", "address", "hours", "osm_url"]].copy()
        view["distance"] = view["distance"].round().astype(int).astype(str) + "m"
        view.columns = ["시설명", "종류", "거리", "주소", "운영시간", "지도 링크"]
        st.dataframe(
            view, use_container_width=True, hide_index=True,
            column_config={"지도 링크": st.column_config.LinkColumn("지도 링크", display_text="지도에서 보기")}
        )
        st.download_button(
            "📥 검색 결과 CSV 다운로드",
            data=places.to_csv(index=False).encode("utf-8-sig"),
            file_name="동네한눈에_검색결과.csv",
            mime="text/csv"
        )

st.divider()
st.caption("데이터 출처: © OpenStreetMap contributors. 시설 정보는 이용자 기여 데이터로 누락·오류·변경이 있을 수 있습니다.")
