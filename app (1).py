import streamlit as st
import pandas as pd
import os
from datetime import date

# ── 설정 ──────────────────────────────────────────────
CSV_FILE = "data/reading_log.csv"
COLUMNS  = ["날짜", "책 제목", "읽은 페이지", "읽은 시간(분)"]


# ── 데이터 함수 ───────────────────────────────────────
def load_data() -> pd.DataFrame:
    """CSV 파일을 읽어서 DataFrame으로 반환. 없으면 빈 DataFrame 생성."""
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE)
    return pd.DataFrame(columns=COLUMNS)


def save_record(record: dict):
    """새 기록 1건을 기존 CSV에 추가해서 저장."""
    df = load_data()                                      # 기존 데이터 불러오기
    new_row = pd.DataFrame([record])                      # 딕셔너리 → DataFrame 1행
    df = pd.concat([df, new_row], ignore_index=True)      # 기존 데이터 아래에 붙이기
    os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True) # data/ 폴더 없으면 생성
    df.to_csv(CSV_FILE, index=False)                      # CSV로 저장


def get_stats(df: pd.DataFrame) -> dict:
    """DataFrame에서 주요 통계값을 계산해서 딕셔너리로 반환."""
    if df.empty:
        return {}

    total_pages   = int(df["읽은 페이지"].sum())
    total_minutes = int(df["읽은 시간(분)"].sum())
    unique_days   = int(df["날짜"].nunique())   # nunique() : 중복 제거 후 개수

    # 시간 단위 변환 (가독성용)
    hours, mins = divmod(total_minutes, 60)     # divmod : 몫과 나머지를 동시에 계산

    # 하루 평균 (0으로 나누기 방지)
    avg_pages   = round(total_pages   / unique_days, 1) if unique_days else 0
    avg_minutes = round(total_minutes / unique_days, 1) if unique_days else 0

    return {
        "total_pages":   total_pages,
        "total_minutes": total_minutes,
        "hours":         hours,
        "mins":          mins,
        "unique_days":   unique_days,
        "avg_pages":     avg_pages,
        "avg_minutes":   avg_minutes,
    }


def get_daily_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """
    날짜별 독서 분석 테이블을 반환.

    계산 항목:
      - 읽은 페이지 합계  : 같은 날 여러 권 읽었다면 합산
      - 읽은 시간 합계    : 분 단위 합산
      - 독서 밀도         : 페이지 ÷ 시간(분)  →  1분당 몇 쪽 읽었는지
    """
    # groupby : 날짜가 같은 행끼리 묶어서 sum() 으로 합산
    daily = (
        df.groupby("날짜", as_index=False)
          .agg(
              페이지합계 = ("읽은 페이지",   "sum"),
              시간합계   = ("읽은 시간(분)", "sum"),
          )
    )

    # 독서 밀도 = 페이지 ÷ 분  (소수점 둘째 자리까지)
    # 시간이 0인 행은 0으로 처리해 ZeroDivisionError 방지
    daily["독서 밀도\n(쪽/분)"] = daily.apply(
        lambda row: round(row["페이지합계"] / row["시간합계"], 2)
        if row["시간합계"] > 0 else 0,
        axis=1,
    )

    # 날짜 내림차순 정렬 (최신 날짜가 위로)
    daily = daily.sort_values("날짜", ascending=False).reset_index(drop=True)
    daily.index = daily.index + 1  # 인덱스 1부터 시작

    return daily


# ── 페이지 설정 ───────────────────────────────────────
st.set_page_config(
    page_title="📚 독서 기록장",
    page_icon="📚",
    layout="centered",
)

st.title("📚 나의 독서 기록장")
st.caption("오늘 읽은 책을 기록해보세요.")

st.divider()


# ── 입력 폼 ───────────────────────────────────────────
st.subheader("✏️ 독서 기록 추가")

# 날짜 선택 — 기본값은 오늘
input_date = st.date_input("날짜", value=date.today())

# 책 제목 입력
input_title = st.text_input("책 제목", placeholder="예) 파친코")

# 두 입력값을 나란히 배치하기 위해 컬럼 2개로 분할
col1, col2 = st.columns(2)

with col1:
    # 읽은 페이지 수 (최소 1, 최대 2000)
    input_pages = st.number_input("읽은 페이지 수", min_value=1, max_value=2000, value=30)

with col2:
    # 읽은 시간 (분 단위, 최소 1, 최대 600)
    input_minutes = st.number_input("읽은 시간 (분)", min_value=1, max_value=600, value=30)

st.write("")  # 버튼 위 여백

# 저장 버튼
if st.button("💾 기록 저장", use_container_width=True):

    # 제목을 입력했는지 확인
    if not input_title.strip():
        st.warning("⚠️ 책 제목을 입력해주세요.")
    else:
        # 입력값을 딕셔너리로 묶어서 저장
        record = {
            "날짜":        str(input_date),
            "책 제목":     input_title.strip(),
            "읽은 페이지": input_pages,
            "읽은 시간(분)": input_minutes,
        }
        save_record(record)
        st.success(f"✅ 『{input_title}』 기록이 저장됐어요!")
        st.balloons()

st.divider()


# ── 데이터 불러오기 (이후 섹션에서 공통으로 사용) ─────
df = load_data()


# ── 📊 통계 요약 ──────────────────────────────────────
st.subheader("📊 나의 독서 통계")

if df.empty:
    st.info("기록이 쌓이면 통계가 표시돼요. 첫 번째 기록을 추가해보세요! 🙌")
else:
    s = get_stats(df)

    # 1행: 핵심 3가지 지표
    col1, col2, col3 = st.columns(3)

    col1.metric(
        label="📄 총 읽은 페이지",
        value=f"{s['total_pages']:,} 쪽",
    )
    col2.metric(
        label="⏱️ 총 독서 시간",
        value=f"{s['hours']}시간 {s['mins']}분",
        help=f"총 {s['total_minutes']:,}분",   # 마우스 오버 시 분 단위로도 확인 가능
    )
    col3.metric(
        label="📅 독서한 날짜 수",
        value=f"{s['unique_days']} 일",
    )

    st.write("")  # 행 사이 여백

    # 2행: 하루 평균 지표
    col4, col5, col6 = st.columns(3)

    col4.metric(
        label="📈 일 평균 페이지",
        value=f"{s['avg_pages']} 쪽",
    )
    col5.metric(
        label="⏰ 일 평균 독서 시간",
        value=f"{s['avg_minutes']} 분",
    )
    col6.metric(
        label="📚 총 기록 수",
        value=f"{len(df)} 건",
    )

st.divider()


# ── 📅 날짜별 독서 분석 ────────────────────────────────
st.subheader("📅 날짜별 독서 분석")

if df.empty:
    st.info("기록이 쌓이면 날짜별 분석이 표시돼요.")
else:
    daily = get_daily_analysis(df)

    # ① 날짜별 합산 테이블 ---------------------------------
    st.markdown("**📋 날짜별 독서 현황**")
    st.dataframe(daily, use_container_width=True)

    st.write("")  # 여백

    # ② 날짜별 핵심 지표 3가지 ----------------------------
    #    분석에 필요한 값들을 daily 테이블에서 바로 계산
    best_day_row   = daily.loc[daily["페이지합계"].idxmax()]   # 가장 많이 읽은 날
    densest_day_row = daily.loc[daily["독서 밀도\n(쪽/분)"].idxmax()]  # 밀도 최고인 날
    avg_pages_per_day = round(daily["페이지합계"].mean(), 1)    # 날짜 기준 하루 평균

    st.markdown("**🔍 분석 요약**")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        label="📖 하루 평균 독서량",
        value=f"{avg_pages_per_day} 쪽",
        help="독서한 날만 집계한 평균이에요.",
    )
    col2.metric(
        label="🏆 최다 독서일",
        value=f"{best_day_row['페이지합계']} 쪽",
        help=f"날짜: {best_day_row['날짜']}",   # 마우스 오버로 날짜 확인
    )
    col3.metric(
        label="⚡ 최고 독서 밀도",
        value=f"{densest_day_row['독서 밀도\n(쪽/분)']} 쪽/분",
        help=f"날짜: {densest_day_row['날짜']}",
    )

    st.write("")  # 여백

    # ③ 독서 밀도 해설 ------------------------------------
    #    전체 평균 밀도를 계산해서 수준을 텍스트로 안내
    avg_density = round(daily["독서 밀도\n(쪽/분)"].mean(), 2)

    if avg_density >= 2.0:
        level, comment = "🚀 매우 빠름", "속독에 가까운 페이스예요!"
    elif avg_density >= 1.0:
        level, comment = "📗 보통",     "안정적인 독서 습관이에요."
    else:
        level, comment = "🐢 천천히",   "꼼꼼하게 읽고 있어요."

    st.info(
        f"**평균 독서 밀도: {avg_density} 쪽/분** — {level}\n\n{comment}"
    )


st.divider()


# ── 최근 기록 5개 ─────────────────────────────────────
st.subheader("🕐 최근 기록 5개")

if df.empty:
    st.info("아직 기록이 없어요. 위에서 첫 번째 독서 기록을 추가해보세요! 🙌")
else:
    # tail(5) : 마지막 5행 선택 → iloc[::-1] : 최신순(아래→위)으로 뒤집기
    recent = df.tail(5).iloc[::-1].reset_index(drop=True)

    # 보기 좋게 인덱스를 1부터 시작하도록 변경
    recent.index = recent.index + 1

    st.dataframe(recent, use_container_width=True)


st.divider()


# ── 전체 기록 테이블 ──────────────────────────────────
st.subheader("📋 전체 기록")

if df.empty:
    st.info("저장된 기록이 없어요.")
else:
    # 날짜 내림차순(최신순)으로 정렬해서 표시
    df_sorted = df.sort_values("날짜", ascending=False).reset_index(drop=True)
    df_sorted.index = df_sorted.index + 1  # 인덱스 1부터 시작

    st.dataframe(df_sorted, use_container_width=True)
