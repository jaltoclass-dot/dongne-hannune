import math
import requests
from urllib.parse import quote
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

# 카카오 로컬 API에서 사용할 검색어와 카테고리 코드
CATEGORIES = {
    "공중화장실": {"queries": ["공중화장실", "개방화장실"], "code": None, "color": "blue"},
    "편의점": {"queries": ["편의점"], "code": "CS2", "color": "green"},
    "주차장": {"queries": ["주차장"], "code": "PK6", "color": "orange"},
    "ATM": {"queries": ["ATM", "현금인출기"], "code": None, "color": "purple"},
    "무료 와이파이": {"queries": ["공공 와이파이", "무료 와이파이"], "code": None, "color": "cadetblue"},
    "약국": {"queries": ["약국"], "code": "PM9", "color": "pink"},
    "병원·의원": {"queries": ["병원"], "code": "HP8", "color": "red"},
    "무인민원발급기": {"queries": ["무인민원발급기", "무인발급기"], "code": None, "color": "darkblue"},
}

KAKAO_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def haversine(lat1, lon1, lat2, lon2):
    earth = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * earth * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@st.cache_data(ttl=300, max_entries=200, show_spinner=False)
def fetch_places(lat, lon, radius, selected_tuple, api_key):
    headers = {"Authorization": f"KakaoAK {api_key}"}
    rows = []
    errors = []

    for category in selected_tuple:
        settings = CATEGORIES[category]
        for keyword in settings["queries"]:
            # 한글 검색어를 UTF-8 URL 인코딩으로 변환해 HTTP 요청에 전달
            encoded_keyword = quote(keyword, safe="", encoding="utf-8")
            params = {
                "x": lon,
                "y": lat,
                "radius": radius,
                "sort": "distance",
                "size": 15,
                "page": 1,
            }
            if settings["code"]:
                params["category_group_code"] = settings["code"]

            try:
                request_url = f"{KAKAO_URL}?query={encoded_keyword}"
                response = requests.get(request_url, headers=headers, params=params, timeout=(5, 12))
                if response.status_code != 200:
                    try:
                        detail = response.json().get("msg", response.text[:200])
                    except Exception:
                        detail = response.text[:200]
                    raise RuntimeError(f"HTTP {response.status_code}: {detail}")

                for item in response.json().get("documents", []):
                    place_lat = float(item["y"])
                    place_lon = float(item["x"])
                    distance = haversine(lat, lon, place_lat, place_lon)
                    if distance > radius:
                        continue
                    rows.append({
                        "id": f"kakao/{item.get('id', '')}",
                        "name": item.get("place_name") or category,
                        "category": category,
                        "lat": place_lat,
                        "lon": place_lon,
                        "address": item.get("road_address_name") or item.get("address_name") or "주소 정보 미제공",
                        "hours": "운영시간 정보 미제공",
                        "distance": distance,
                        "osm_url": item.get("place_url") or "https://map.kakao.com/",
                    })
            except Exception as exc:
                errors.append(f"{category}({keyword}): {exc}")

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.drop_duplicates(subset=["id"]).sort_values("distance").reset_index(drop=True)
    if errors and result.empty:
        raise RuntimeError("카카오 장소 검색에 실패했습니다.\n" + "\n".join(errors[:4]))
    return result


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
    selected = st.multiselect("시설 종류", list(CATEGORIES.keys()), default=["공중화장실", "편의점"])
    search = st.button("주변 시설 검색", type="primary", use_container_width=True)
    st.caption("검색 결과는 카카오맵에 등록된 장소 정보를 기준으로 합니다.")

if "places" not in st.session_state:
    st.session_state["places"] = None

if search:
    if not selected:
        st.warning("시설 종류를 하나 이상 선택하세요.")
    elif "KAKAO_REST_API_KEY" not in st.secrets:
        st.error("카카오 API 키가 등록되지 않았습니다. Streamlit의 Settings → Secrets를 확인해 주세요.")
    else:
        try:
            with st.spinner("주변 시설을 검색하고 있습니다. 잠시만 기다려 주세요."):
                st.session_state["places"] = fetch_places(
                    lat, lon, radius, tuple(selected), st.secrets["KAKAO_REST_API_KEY"]
                )
                st.session_state["last_search"] = (lat, lon, radius, tuple(selected))
        except Exception as exc:
            st.error(str(exc))
            st.info("잠시 후 다시 시도하거나 카카오 개발자센터의 API 사용 설정과 키를 확인해 주세요.")

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

    for _, row in places.head(100).iterrows():
        category = row["category"]
        color = CATEGORIES.get(category, {}).get("color", "blue")
        popup = (
            f"<b>{row['name']}</b><br>종류: {category}<br>"
            f"거리: {row['distance']:.0f}m<br>주소: {row['address']}<br>"
            f"<a href='{row['osm_url']}' target='_blank'>지도에서 보기</a>"
        )
        folium.Marker(
            [row["lat"], row["lon"]], tooltip=row["name"],
            popup=folium.Popup(popup, max_width=280),
            icon=folium.Icon(color=color, icon="info-sign")
        ).add_to(map_obj)

    st.subheader("🗺️ 주변 시설 지도")
    st_folium(map_obj, use_container_width=True, height=480, key="facility_map")
    st.subheader("📋 가까운 시설 목록")
    if places.empty:
        st.warning("카카오맵에서 선택한 조건에 해당하는 장소를 찾지 못했습니다. 다른 시설 종류나 더 넓은 반경으로 시도해 보세요.")
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
st.caption("장소 데이터 출처: Kakao Local API. 시설 정보는 카카오맵 등록 여부에 따라 누락될 수 있습니다.")
