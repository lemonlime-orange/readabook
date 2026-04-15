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


def make_daily_chart_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    날짜별 페이지 합계를 날짜 오름차순으로 정렬한 차트용 DataFrame 반환.
    st.line_chart / st.bar_chart 는 인덱스를 X축으로 사용하므로
    날짜를 인덱스로 설정해서 반환한다.
    """
    daily = (
        df.groupby("날짜", as_index=False)
          .agg(읽은페이지=("읽은 페이지", "sum"))
          .sort_values("날짜")          # 날짜 오름차순 (왼쪽→오른쪽이 과거→최신)
    )
    daily["날짜"] = pd.to_datetime(daily["날짜"])   # 문자열 → datetime (X축 포맷 개선)
    daily = daily.set_index("날짜")                 # 날짜를 인덱스로 설정
    return daily


def make_cumulative_chart_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    날짜별 누적 페이지 수를 계산한 차트용 DataFrame 반환.
    cumsum() 으로 그날까지 읽은 총 페이지를 누적 합산한다.
    """
    daily = make_daily_chart_data(df).copy()

    # cumsum() : 위에서부터 차례로 더해가는 누적 합계
    # 예) [10, 20, 30] → [10, 30, 60]
    daily["누적페이지"] = daily["읽은페이지"].cumsum()

    return daily[["누적페이지"]]   # 누적 컬럼만 남기고 반환


def get_style_analysis(df: pd.DataFrame) -> dict:
    """
    독서 스타일을 두 가지 관점으로 분석해 결과를 딕셔너리로 반환.

    ① 꾸준형 vs 몰아읽기형
       - 날짜별 페이지 합계의 표준편차(std)를 평균으로 나눈 값 = 변동계수(CV)
       - CV가 낮을수록 매일 비슷하게 읽는 꾸준형
       - CV가 높을수록 어떤 날은 많이, 어떤 날은 조금 읽는 몰아읽기형

    ② 평일 vs 주말 독서량 비교
       - 날짜에서 요일을 추출(dayofweek: 월=0 … 일=6)
       - 평일(0~4)과 주말(5~6) 그룹으로 나눠 하루 평균 페이지 비교
    """
    # 날짜별 합계 테이블 (오름차순 정렬)
    daily = (
        df.groupby("날짜", as_index=False)
          .agg(페이지=("읽은 페이지", "sum"))
          .sort_values("날짜")
    )
    # 문자열 날짜 → datetime (요일 추출에 필요)
    daily["날짜"] = pd.to_datetime(daily["날짜"])

    # ── ① 변동성 분석 ────────────────────────────────
    mean_pages = daily["페이지"].mean()
    std_pages  = daily["페이지"].std()   # 표준편차: 값이 평균에서 얼마나 퍼져 있는지

    # 변동계수(CV) = 표준편차 ÷ 평균  (데이터가 1개이면 std=NaN → CV=0 처리)
    cv = round(std_pages / mean_pages, 2) if (mean_pages > 0 and len(daily) > 1) else 0

    if cv <= 0.4:
        style_type    = "📅 꾸준형"
        style_comment = (
            f"하루 평균 {mean_pages:.0f}쪽, 표준편차 {std_pages:.1f}쪽으로 "
            f"매일 비슷한 양을 읽고 있어요. 꾸준한 독서 습관을 가지고 있네요!"
        )
    elif cv <= 0.8:
        style_type    = "🌊 균형형"
        style_comment = (
            f"하루 평균 {mean_pages:.0f}쪽을 읽지만 날마다 편차(±{std_pages:.1f}쪽)가 있어요. "
            f"바쁜 날엔 조금, 여유로운 날엔 많이 읽는 균형 잡힌 스타일이에요."
        )
    else:
        style_type    = "🔥 집중형 (몰아읽기)"
        style_comment = (
            f"날마다 독서량 차이가 큰 편이에요(평균 {mean_pages:.0f}쪽, 편차 ±{std_pages:.1f}쪽). "
            f"한 번 읽을 때 집중해서 많이 읽는 타입이에요!"
        )

    # ── ② 평일 vs 주말 분석 ──────────────────────────
    # dayofweek : 월=0, 화=1, 수=2, 목=3, 금=4, 토=5, 일=6
    daily["요일구분"] = daily["날짜"].dt.dayofweek.apply(
        lambda d: "주말" if d >= 5 else "평일"
    )

    weekday_df = daily[daily["요일구분"] == "평일"]["페이지"]
    weekend_df = daily[daily["요일구분"] == "주말"]["페이지"]

    weekday_avg = round(weekday_df.mean(), 1) if not weekday_df.empty else None
    weekend_avg = round(weekend_df.mean(), 1) if not weekend_df.empty else None

    # 평일/주말 데이터가 모두 있을 때만 비교 문장 생성
    if weekday_avg is not None and weekend_avg is not None:
        diff      = round(abs(weekend_avg - weekday_avg), 1)
        who_more  = "주말" if weekend_avg >= weekday_avg else "평일"
        week_comment = (
            f"평일 평균 {weekday_avg}쪽, 주말 평균 {weekend_avg}쪽으로 "
            f"**{who_more}에 {diff}쪽 더 읽어요.**"
        )
    elif weekday_avg is not None:
        week_comment = f"아직 주말 기록이 없어요. 평일 평균은 {weekday_avg}쪽이에요."
    elif weekend_avg is not None:
        week_comment = f"아직 평일 기록이 없어요. 주말 평균은 {weekend_avg}쪽이에요."
    else:
        week_comment = "평일/주말 비교를 위한 데이터가 부족해요."

    return {
        "cv":           cv,
        "style_type":   style_type,
        "style_comment": style_comment,
        "weekday_avg":  weekday_avg,
        "weekend_avg":  weekend_avg,
        "week_comment": week_comment,
        "daily":        daily,          # 요일구분 컬럼 포함된 테이블 (차트용)
    }


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


# ── 🧠 독서 스타일 분석 ────────────────────────────────
st.subheader("🧠 나의 독서 스타일 분석")

if df.empty:
    st.info("기록이 쌓이면 독서 스타일을 분석해드려요.")
elif df["날짜"].nunique() < 3:
    st.info("날짜가 3일 이상 기록되면 스타일 분석이 가능해요.")
else:
    sa = get_style_analysis(df)

    # ① 독서 타입 카드 ----------------------------------------
    st.markdown("**📌 독서 타입**")
    st.success(f"### {sa['style_type']}\n\n{sa['style_comment']}")

    st.write("")  # 여백

    # ② 평일 vs 주말 비교 -------------------------------------
    st.markdown("**📆 평일 vs 주말 비교**")

    # 두 값이 모두 있을 때만 metric 카드 나란히 표시
    if sa["weekday_avg"] is not None and sa["weekend_avg"] is not None:
        col1, col2 = st.columns(2)
        col1.metric("🗓️ 평일 하루 평균", f"{sa['weekday_avg']} 쪽")
        col2.metric("🏖️ 주말 하루 평균", f"{sa['weekend_avg']} 쪽",
                    # delta: 주말이 평일보다 얼마나 많은지 표시 (양수=초록, 음수=빨강)
                    delta=f"{round(sa['weekend_avg'] - sa['weekday_avg'], 1)} 쪽")
        st.write("")

    st.info(sa["week_comment"])

    st.write("")  # 여백

    # ③ 변동계수 게이지 (텍스트 프로그레스 바) -------------------
    # CV 값을 0~1 범위로 clamp 해서 progress bar 로 시각화
    st.markdown("**📊 독서 변동성 지수 (낮을수록 꾸준한 타입)**")
    progress_val = min(sa["cv"], 1.0)   # 1.0 초과하면 bar 오류나므로 상한 고정
    st.progress(progress_val)
    st.caption(
        f"변동계수(CV) = {sa['cv']}  ·  "
        f"0 ~ 0.4: 꾸준형  /  0.4 ~ 0.8: 균형형  /  0.8+: 집중형"
    )


st.divider()


# ── 📈 독서량 시각화 ───────────────────────────────────
st.subheader("📈 독서량 시각화")

if df.empty:
    st.info("기록이 쌓이면 그래프가 표시돼요.")
elif df["날짜"].nunique() < 2:
    # 날짜가 1개뿐이면 선이 점 하나로만 표시되므로 안내 메시지 출력
    st.info("날짜가 2일 이상 기록되면 그래프를 볼 수 있어요.")
else:
    chart_daily = make_daily_chart_data(df)
    chart_cum   = make_cumulative_chart_data(df)

    # ① 날짜별 독서량 라인 차트 ----------------------------
    st.markdown("**📉 날짜별 읽은 페이지 수**")
    st.caption("하루에 읽은 페이지 수를 날짜별로 표시해요.")
    st.line_chart(
        chart_daily,
        y="읽은페이지",
        color="#4C9BE8",       # 선 색상
        height=250,
    )

    st.write("")  # 두 차트 사이 여백

    # ② 누적 독서량 라인 차트 ------------------------------
    st.markdown("**📈 누적 독서 페이지 수**")
    st.caption("첫 기록부터 오늘까지 쌓인 총 페이지 수예요. 그래프가 오를수록 꾸준히 읽고 있다는 뜻이에요!")
    st.line_chart(
        chart_cum,
        y="누적페이지",
        color="#34A853",       # 성장을 나타내는 초록색
        height=250,
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
