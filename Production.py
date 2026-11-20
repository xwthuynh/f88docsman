import gspread
import pandas as pd
import streamlit as st
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from datetime import date, datetime


# =====================================================
# CONNECT GOOGLE SHEETS
# =====================================================

GOOGLE_SHEET_ID = "1bwWXjAQzS7zyAef0gU7df7ad-cpDHDRwujzrEUbdiBI"

JSON_FILE = (
    Path(__file__).resolve().parent
    / "f88docsman-32668ab9bf17.json"
)

def get_connection():

    credentials = json.loads(
        st.secrets["google_service_account_json"]
    )

    gc = gspread.service_account_from_dict(
        credentials
    )

    conn = gc.open_by_key(GOOGLE_SHEET_ID)

    return conn

# JSON_FILE = r"C:\Users\khanhhp2\OneDrive - CONG TY CO PHAN KINH DOANH F88\APPS\F88Docs\f88docsman-b8396565e6b1.json"

#
# def get_connection():
#     gc = gspread.service_account(filename=JSON_FILE)
#     gc.set_timeout((10, 30))
#     conn = gc.open_by_key(GOOGLE_SHEET_ID)
#
#     return conn

# =====================================================
# DATABASE HELPER FUNCTIONS
# =====================================================

def get_next_id(worksheet, id_column):
    """
    Tự động tạo ID mới = MAX(ID) + 1
    """

    headers = worksheet.row_values(1)

    if id_column not in headers:
        raise ValueError(
            f"Không tìm thấy cột {id_column} "
            f"trong sheet {worksheet.title}"
        )

    column_index = headers.index(id_column) + 1

    values = worksheet.col_values(column_index)[1:]

    ids = [
        int(float(value))
        for value in values
        if str(value).strip()
    ]

    return max(ids, default=0) + 1


def convert_cell(value):
    """
    Chuyển giá trị Python sang định dạng Google Sheets.
    """

    if value is None:
        value = ""

    elif isinstance(value, (date, datetime)):
        value = value.isoformat()

    elif isinstance(value, (list, tuple)):
        value = ",".join(map(str, value))

    elif isinstance(value, dict):
        value = json.dumps(
            value,
            ensure_ascii=False
        )

    if isinstance(value, bool):
        result = {"boolValue": value}

    elif isinstance(value, (int, float)):
        result = {"numberValue": value}

    else:
        result = {"stringValue": str(value)}

    return {
        "userEnteredValue": result
    }


def build_insert(worksheet, row_data):
    """
    Tạo yêu cầu INSERT theo đúng thứ tự cột
    trong Google Sheets.
    """

    headers = worksheet.row_values(1)

    if not headers:
        raise ValueError(
            f"Sheet {worksheet.title} chưa có header"
        )

    missing = set(row_data.keys()) - set(headers)

    if missing:
        raise ValueError(
            f"Sheet {worksheet.title} thiếu cột: {missing}"
        )

    values = [
        convert_cell(row_data.get(column, ""))
        for column in headers
    ]

    return {
        "appendCells": {
            "sheetId": worksheet.id,
            "rows": [
                {"values": values}
            ],
            "fields": "userEnteredValue"
        }
    }


# =====================================================
# DATABASE FUNCTIONS
# =====================================================

def save_new_form(form_data):
    created_dt = datetime.now(
        ZoneInfo("Asia/Ho_Chi_Minh")
    ).isoformat(timespec="seconds")

    doc = form_data["DOCS"]
    docver = form_data["DOCVERS"]
    docrule = form_data["DOCVERDTL"]

    conn = get_connection()

    ws_doc = conn.worksheet("DOCS")
    ws_ver = conn.worksheet("DOCVERS")
    ws_rule = conn.worksheet("DOCVERDTL")

    # ---------------------------------
    # 1. TẠO DOC_ID
    # ---------------------------------

    doc_id = get_next_id(
        ws_doc,
        "DOC_ID"
    )

    doc_data = {
        "DOC_ID": doc_id,
        "DOC_NAME": doc["DOC_NAME"],
        "DOC_NO": doc["DOC_NO"],
        "DOC_TYPE": doc["DOC_TYPE"],
        "ASSET": ",".join(doc["ASSET"])
                 if isinstance(doc["ASSET"], (list, tuple))
                 else doc["ASSET"],
        "DEPARTMENT": doc["DEPARTMENT"],
        "DOC_LINK": doc["DOC_LINK"],
        'CREATED_DT': created_dt,
        "REPLACED_DOC_NO": doc['REPLACED_DOC_NO']
    }

    # ---------------------------------
    # 2. TẠO DOC_VER_ID
    # ---------------------------------

    doc_ver_id = get_next_id(
        ws_ver,
        "DOC_VER_ID"
    )

    ver_data = {
        "DOC_VER_ID": doc_ver_id,
        "DOC_ID": doc_id,
        "DOC_VER_NO": docver["DOC_VER_NO"],
        "DOC_VER_TYPE": docver["DOC_VER_TYPE"],
        "PIC": docver["PIC"],
        "ISSUED_DT": docver["ISSUED_DT"],
        "EFFECTIVE_FROM": docver["EFFECTIVE_FROM"],
        "EFFECTIVE_TO": docver["EFFECTIVE_TO"],
        'CREATED_DT': created_dt
    }

    # Thay thế một số giá trị DEFAULT của SQL Server.
    ver_headers = ws_ver.row_values(1)


    if "STATUS" in ver_headers:

        if docver["EFFECTIVE_TO"] is not None and docver["EFFECTIVE_TO"] < today:
            ver_data["STATUS"] = "INACTIVE"

        else:
            ver_data["STATUS"] = "ACTIVE"

    if "PARAM_CODES" in ver_headers:
        ver_data["PARAM_CODES"] = "[]"

    # ---------------------------------
    # 3. CHUẨN BỊ LƯU DỮ LIỆU
    # ---------------------------------

    requests = [
        build_insert(ws_doc, doc_data),
        build_insert(ws_ver, ver_data)
    ]

    # ---------------------------------
    # 4. LƯU SCHEME_RULE
    # ---------------------------------

    rule_headers = ws_rule.row_values(1)

    # Hỗ trợ hai cách đặt tên cột ID.
    rule_id_column = next(
        (
            col
            for col in [
                "DOC_VER_DTL_ID",
                "DOCVERDTL_ID"
            ]
            if col in rule_headers
        ),
        None
    )

    if rule_id_column:
        rule_id = get_next_id(
            ws_rule,
            rule_id_column
        )

    for i, rule in enumerate(docrule):

        scheme_rule = rule["SCHEME_RULE"]

        # Chuyển dictionary thành JSON string nếu cần.
        if isinstance(scheme_rule, dict):
            scheme_rule = json.dumps(
                scheme_rule,
                ensure_ascii=False
            )

        else:
            # Kiểm tra JSON string có hợp lệ không.
            json.loads(scheme_rule)

        rule_data = {
            "DOC_VER_ID": doc_ver_id,
            "SCHEME_RULE": scheme_rule,
            'CREATED_DT': created_dt
        }

        if rule_id_column:
            rule_data[rule_id_column] = rule_id + i

        requests.append(
            build_insert(
                ws_rule,
                rule_data
            )
        )

    # ---------------------------------
    # 5. INSERT GOOGLE SHEETS
    # ---------------------------------

    conn.batch_update({
        "requests": requests
    })

    # Cập nhật cache sau khi lưu.
    get_data.clear()

    return doc_id, doc_ver_id


# =====================================================
# GET DATA
# =====================================================

query_doc = "DOCS"
query_ver = "DOCVERS"
query_rule = "DOCVERDTL"


@st.cache_data(ttl=300)
def get_data(query):
    conn = get_connection()
    worksheet = conn.worksheet(query)
    headers = worksheet.row_values(1)
    data = worksheet.get_all_records(
        numericise_ignore=["all"]
    )

    df = pd.DataFrame(
        data,
        columns=headers
    )

    # Chuyển các cột ID về dạng số.
    id_columns = [
        "DOC_ID",
        "DOC_VER_ID",
        "DOC_VER_DTL_ID",
        "DOCVERDTL_ID"
    ]

    for col in id_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="raise"
            )

    # Chuyển các cột ngày về kiểu date.
    date_columns = [
        "ISSUED_DT",
        "EFFECTIVE_FROM",
        "EFFECTIVE_TO"
    ]

    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(
                df[col].replace("", None),
                errors="coerce"
            ).dt.date

    return df


# =====================================================
# LOAD DATA
# =====================================================

doc = get_data(query_doc)

doc_ver = get_data(query_ver)

doc_rule = get_data(query_rule)


## PROCESS DATA:
import polars as pl

@st.cache_data(ttl=300)
def process_data(doc,doc_ver,doc_rule, today):
    doc = pl.from_pandas(doc)
    doc_ver = pl.from_pandas(doc_ver)
    doc_rule = pl.from_pandas(doc_rule)

    doc_ver = doc_ver.with_columns(pl.col('EFFECTIVE_TO').cast(pl.Date))

    doc_ver = doc_ver.with_columns(pl.when(pl.col('EFFECTIVE_TO')<today).then(pl.lit('INACTIVE')).otherwise(pl.lit('ACTIVE')).alias('STATUS'))

    df = (doc_ver.select(['DOC_VER_ID', 'DOC_VER_NO','DOC_ID', 'DOC_VER_TYPE', 'PIC', 'ISSUED_DT', 'EFFECTIVE_FROM', 'EFFECTIVE_TO',
                      'STATUS'])
      .join(doc.select(['DOC_ID', 'DOC_NAME', 'DOC_TYPE','DOC_NO', 'ASSET','DOC_LINK']), how='left', on=['DOC_ID'])
      .join(doc_rule.select(['DOC_VER_ID', 'SCHEME_RULE']), how='left', on=['DOC_VER_ID'])
      )

    df = df.with_columns(pl.col('ISSUED_DT').cast(pl.Utf8).str.to_date(format='%Y-%m-%d').dt.strftime('%Y%m%d').str.slice(0,6).alias('ISSUED_MONTH'))

    df = df.with_columns(
        pl.col('SCHEME_RULE').str.json_path_match("$.fund").str.json_decode(pl.List(pl.String)).list.eval(pl.element().str.to_uppercase()).alias('FUND'),
            pl.col('SCHEME_RULE').str.json_path_match("$.products").str.json_decode(pl.List(pl.String)).list.eval(pl.element().str.to_uppercase()).alias('PRODUCTS')
    )

    fund_fil = df.select(pl.col('FUND').explode().unique())
    nsp_fil = df.select(pl.col('PRODUCTS').explode().unique())

    return doc, doc_ver, doc_rule, df, fund_fil, nsp_fil

today = datetime.now(
    ZoneInfo("Asia/Ho_Chi_Minh")
).date()

doc, doc_ver, doc_rule, df, fund_fil, nsp_fil = process_data(
    doc,
    doc_ver,
    doc_rule,
    today
)



## BUILD APP - SCREENS:
st.set_page_config(
    page_title="F88 Policy Management",
    page_icon="📋",
    layout="wide"
)

provinces = [
    "Toàn Quốc",
    "Hà Nội", "Vĩnh Phúc", "Bắc Ninh", "Quảng Ninh",
    "Hải Dương", "Hải Phòng", "Hưng Yên", "Thái Bình",
    "Hà Nam", "Nam Định", "Ninh Bình",

    "Hà Giang", "Cao Bằng", "Bắc Kạn", "Tuyên Quang",
    "Lào Cai", "Yên Bái", "Thái Nguyên", "Lạng Sơn",
    "Bắc Giang", "Phú Thọ", "Điện Biên", "Lai Châu",
    "Sơn La", "Hòa Bình",

    "Thanh Hóa", "Nghệ An", "Hà Tĩnh", "Quảng Bình",
    "Quảng Trị", "Huế", "Đà Nẵng", "Quảng Nam",
    "Quảng Ngãi", "Bình Định", "Phú Yên", "Khánh Hòa",
    "Ninh Thuận", "Bình Thuận",

    "Kon Tum", "Gia Lai", "Đắk Lắk", "Đắk Nông",
    "Lâm Đồng",

    "Bình Phước", "Tây Ninh", "Bình Dương", "Đồng Nai",
    "Bà Rịa - Vũng Tàu", "TP. Hồ Chí Minh",

    "Long An", "Tiền Giang", "Bến Tre", "Trà Vinh",
    "Vĩnh Long", "Đồng Tháp", "An Giang", "Kiên Giang",
    "Cần Thơ", "Hậu Giang", "Sóc Trăng", "Bạc Liêu",
    "Cà Mau"
]

# CONTAINER 1 - HOME HEADER
with st.container(key="home_header"):

    st.html("""
    <style>
        .home-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;

            background-color: #24496D;
            border: 2px solid #0C3042;
            border-bottom: 5px solid #FFC400;
            padding: 18px 20px;
            flex-wrap: wrap;
        }

        .home-header-content {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .home-header-title {
            color: white;
            font-size: 21px;
            font-weight: 700;
            margin: 0;
        }

        .home-header-subtitle {
            color: white;
            font-size: 15px;
            font-weight: 600;
            margin: 0;
        }

        .home-header-nav {
            display: flex;
            align-items: center;
            gap: 22px;
            flex-wrap: wrap;
        }

        .home-nav-item {
            color: white;
            font-size: 16px;
            white-space: nowrap;
        }

        .home-nav-active {
            color: #FFC400;
            font-weight: bold;
        }
    </style>

    <div class="home-header">

        <div class="home-header-content">
            <h1 class="home-header-title">
                PHÒNG PHÁT TRIỂN SẢN PHẨM
            </h1>

            <p class="home-header-subtitle">
                Công cụ tra cứu Quyết định-Điều chỉnh
                về Chính sách sản phẩm
            </p>
        </div>

        <nav class="home-header-nav">
            <span class="home-nav-item home-nav-active">Home</span>
            <span class="home-nav-item">Lịch sử điều chỉnh</span>
            <span class="home-nav-item">Báo cáo tổng hợp</span>
        </nav>

    </div>
    """)


## CONTAINER 2 - FILTER AND OVERVIEW
# CSS - BODY
st.html("""
<style>
    .st-key-home_body h3 {
        font-size: 16px;
        font-weight: 700;
    }
</style>
""")


with st.container(key="home_body"):
    #Row 1:
    st.subheader("DANH SÁCH VĂN BẢN ĐÃ BAN HÀNH")

    #Row 2: Các cột filter dòng 1
    filter_cols = st.columns(6)
    with filter_cols[0]:
        month = st.multiselect(key='fil_month',
            label="Tháng áp dụng",options = df['ISSUED_MONTH'].unique(), placeholder='Chọn tháng áp dụng')
    with filter_cols[1]:
        asset = st.multiselect(key='fil_asset',
            label="Tài sản",options = ['OT','XM'], placeholder='Chọn loại tài sản')
    with filter_cols[2]:
        fund = st.multiselect(key='fil_fund',
            label="Nguồn",options = fund_fil , placeholder='Chọn nguồn')
    with filter_cols[3]:
        nsp = st.multiselect(key='fil_nsp',
            label="Nhóm sản phẩm",options = nsp_fil, placeholder='Chọn nhóm sản phẩm')
    with filter_cols[4]:
        pic = st.multiselect(key='fil_pic',
            label="PIC",options = df['PIC'].unique(), placeholder='Chọn PIC')
    with filter_cols[5]:
        status = st.multiselect(key='fil_status',
            label="Trạng thái",options = df['STATUS'].unique(), placeholder='Chọn trạng thái')


    # Row 3: Tìm kiếm document - Cột filter dòng 2
    filter_cols = st.columns(1)
    with filter_cols[0]:
        searchbox = st.text_input(key='fil_searchbox',label='Tìm kiếm tên văn bản',placeholder='Nhập tên văn bản')

    # Row 4: Card Metric
    card_col1, card_col2, col_empty = st.columns([2,2,6])
    with card_col1:
        with st.container(border=True):
            st.metric(label='Tổng số văn bản ban hành',value=doc_ver.height)

    with card_col2:
        with st.container(border=True):
            st.metric(label='Số văn bản còn hiệu lực',value=doc_ver.filter(pl.col('STATUS')=='ACTIVE').height)


## FORM - ADD NEW:
if "form_step" not in st.session_state:
    st.session_state.form_step = 1

if "doc_type" not in st.session_state:
    st.session_state.doc_type = {}

if "form_data" not in st.session_state:
    st.session_state.form_data = {}

if "rule_count" not in st.session_state:
    st.session_state.rule_count = 1

def reset_new_doc():
    st.session_state.form_step = 1
    st.session_state.form_data = {}
    st.session_state.rule_count = 1

@st.dialog("Tạo văn bản mới",width="large",
           on_dismiss=reset_new_doc
           )
def add_new_doc():
    step = st.session_state.form_step

    st.caption(f"Bước {step}/3")

    if step == 1:

        with st.form(key='form_new_doc'):
            form_docname = st.text_input(label='Tên văn bản',placeholder='Nhập tên văn bản')

            new_doc_col1, new_doc_col2, new_doc_col3 = st.columns(3)
            with new_doc_col1:
                form_docno = st.text_input(label='Số văn bản',placeholder='Nhập số văn bản')
            with new_doc_col2:
                form_doclink = st.text_input(label='Link văn bản',type='url',placeholder='Dán đường link văn bản')
            with new_doc_col3:
                form_docreplace = st.multiselect(label='Văn bản bị thay thế'
                                                ,options=[]
                                                ,accept_new_options=True
                                                ,placeholder='Nhập số văn bản bị thay thế')

            form_col_1, form_col_2, form_col_3  = st.columns(3)
            with form_col_1:
                form_doctype = st.selectbox(key='form_doctype',index=None,options=['Ban hành mới','Điều chỉnh chính sách'],label='Phân nhóm',placeholder='Chọn phân nhóm')
            with form_col_2:
                form_asset = st.multiselect(key='form_asset',options=['OT','XM'],label='Tài sản',placeholder='Chọn tài sản')
            with form_col_3:
                form_dept = st.selectbox(key='form_dept',index=None,options=['PTSP','QTRR'],label='Phòng ban',placeholder='Chọn phòng ban')

            with st.container(key='form_btn_cont',
                              horizontal=True,
                              horizontal_alignment="right"
                              ):
                btn_form_nxt = st.form_submit_button(
                    label="Tiếp tục",
                    type="primary"
                )
                btn_form_can = st.form_submit_button(
                    label="Hủy",
                    type="secondary"
                )

        if btn_form_can:
            st.session_state.form_step = 1
            st.session_state.form_data = {}
            st.rerun()

        if btn_form_nxt:
            st.session_state.form_data['DOCS'] = {'DOC_NAME':form_docname,'DOC_NO':form_docno, 'DOC_TYPE':form_doctype,
                                              'ASSET':form_asset,'DEPARTMENT':form_dept,'DOC_LINK':form_doclink,'REPLACED_DOC_NO':form_docreplace}
            st.session_state.form_step = 2
            st.rerun(scope="fragment")

    elif step == 2:
        with st.form(key='form_new_docver'):
            form_col_1, form_col_2, form_col_3 = st.columns(3)
            with form_col_1:
                form_verno = st.text_input(key='form_verno',label='Số phiên bản', placeholder='Nhập số phiên bản')
            with form_col_2:
                form_vertype = st.text_input(label='Loại phiên bản',value='Mới',disabled=True)
            with form_col_3:
                form_pic = st.selectbox(key='form_pic', index=None,
                                        options=['Huỳnh Phùng Khánh', 'Nhâm Văn Quý', 'Nguyễn Thị Xuyến','Trần Thị Trang',
                                                 'Đặng Thị Thu Hà', 'Nguyễn Minh Ngọc','Phùng Thị Hồng Vân','Trần Thị Ngọc Trang',
                                                 'Nguyễn Gia Phương Anh', 'Trần Thu Huyền', 'Nguyễn Thị Thùy Dương',
                                                 'Đoàn Hồng Ngọc', 'Trịnh Minh Anh','Phạm Thị Phương','Trần Thùy Vân','Trần Nữ Vân Anh'], label='PIC',
                                        placeholder='Chọn PIC')

            form_col_4, form_col_5, form_col_6 = st.columns(3)
            with form_col_4:
                form_issuedate = st.date_input(key="form_issuedate",label="Ngày ban hành",value=None,format="DD/MM/YYYY")
            with form_col_5:
                form_effectstartdate = st.date_input(key="form_effectstartdate",label="Ngày hiệu lực",value=None,format="DD/MM/YYYY")
            with form_col_6:
                form_effectenddate = st.date_input(key="form_effectenddate",label="Ngày hết hiệu lực",value=None,format="DD/MM/YYYY")

            with st.container(key='form_btn_cont',
                              horizontal=True,
                              horizontal_alignment="right"
                              ):
                btn_form_back = st.form_submit_button(
                    label="Quay lại",
                    type="secondary"
                )

                btn_form_nxt = st.form_submit_button(
                    label="Tiếp tục",
                    type="primary"
                )

                btn_form_can = st.form_submit_button(
                    label="Hủy",
                    type="secondary"
                )

        if btn_form_back:
            st.session_state.form_step = 1
            st.rerun(scope="fragment")

        elif btn_form_can:
            st.session_state.form_step = 1
            st.session_state.form_data = {}
            st.rerun()

        elif btn_form_nxt:
            st.session_state.form_data['DOCVERS'] = {'DOC_VER_NO': form_verno, 'DOC_VER_TYPE': form_vertype, 'PIC': form_pic,
                                                  'ISSUED_DT': form_issuedate, 'EFFECTIVE_FROM': form_effectstartdate, 'EFFECTIVE_TO': form_effectenddate}
            st.session_state.form_step = 3
            st.rerun(scope="fragment")


    elif step == 3 and st.session_state.form_data['DOCS']['DOC_TYPE'] == 'Ban hành mới':
        for i in range(1, st.session_state.rule_count + 1):
            with st.expander(label=f'Rule {i}', expanded=True):
                exp_col_1, exp_col_2, exp_col_3, exp_col_4 = st.columns(4)
                with exp_col_1:
                    selected_fund = st.multiselect("Nguồn", ["F88", 'CIMB', 'MB'], key=f"fund_{i}")
                    is_f88 = 'F88' in selected_fund
                    is_partner = any(fund in selected_fund for fund in ['CIMB','MB'])
                with exp_col_2:
                    st.multiselect("Loại khách hàng", ["MỚI", 'CŨ'], key=f"custype_{i}")
                with exp_col_3:
                    st.multiselect("Điểm", ["Tốt","Khá","Trung bình","Kém","A", 'B', 'C', 'D', 'E'], key=f"score_{i}")
                with exp_col_4:
                    st.multiselect("Nhóm sản phẩm", ["OT BAU KHCN","OT BAU KHDN", "OT BAU HKD", "OT SALON", "OT 3.6", 'OT 4.0', 'OT MYF88', 'OT KHQL'
                        , 'LĐTD', 'CN', 'VCVP', 'TXCN', 'TT','KDOL','HUONGLUONG', 'XM 5.4', 'XM KHQL', 'XM MYF88', 'XM GCK',
                                                     'XM CMTNGT DIENNUOC',
                                                     'XM CMTNGT VIDIENTU']
                                   , key=f"nsp_{i}")

                exp_col_5, exp_col_6, exp_col_7, exp_col_8 = st.columns(4)
                with exp_col_5:
                    st.multiselect('Vùng', ['Toàn Quốc','HCM1','HN','TNB2','TN','TB','HCM2','ĐBB2','TBB','BTB','HN2','TNB2'
                               ,'HN1','ĐNB','NTB','ĐBB','ĐBB1'], key=f"vung_{i}",default='Toàn Quốc')
                with exp_col_6:
                    st.multiselect('Chọn Tỉnh',provinces,key=f"tinh_{i}",default='Toàn Quốc')
                with exp_col_7:
                    st.multiselect("Kỳ hạn", [1, 3, 6, 9, 12, 15, 18, 24, 36], key=f"tenor_{i}")
                with exp_col_8:
                    st.multiselect("Phương thức", ["GCK", "GHK"], key=f"pttg_{i}")

                exp_col_9, exp_col_10, exp_col_11, exp_col_12 = st.columns(4)
                with exp_col_9:
                    st.number_input("Max LTV (%)", key=f"ltv_{i}")
                with exp_col_10:
                    st.number_input("Min Ticket Size (triệu đồng)",min_value=1,max_value=2000,value=1,key=f"ts_min_{i}" )
                with exp_col_11:
                    st.number_input("Max Ticket Size (triệu đồng)",min_value=1,max_value=2000,value=1,key=f"ts_max_{i}" )
                with exp_col_12:
                    if is_f88:
                        st.number_input("CPV (%)",key=f"cpv_{i}" )
                    elif is_partner:
                        st.number_input("Phí ký gửi (%)",key=f"pkg_{i}" )

        col_addrule, col_delrule, col_empty2 = st.columns([1,1,8])
        with col_addrule:
            btn_add_rule = st.button("Thêm Rule", type="secondary")
        with col_delrule:
            if st.session_state.rule_count >=1:
                btn_del_rule = st.button("Xóa Rule", type="secondary")
                if btn_del_rule:
                    st.session_state.rule_count -= 1
                    st.rerun(scope="fragment")

        if btn_add_rule:
            st.session_state.rule_count += 1
            st.rerun(scope="fragment")

        with st.container(key='form_btn_cont',
                          horizontal=True,
                          horizontal_alignment="right"
                          ):
            btn_form_back = st.button(
                label="Quay lại",
                type="secondary"
            )

            btn_form_save = st.button(
                label="Lưu",
                type="primary"

            )

            btn_form_can = st.button(
                label="Hủy",
                type="secondary"
            )

        if btn_form_back:
            st.session_state.form_step = 2
            st.rerun(scope="fragment")

        elif btn_form_can:
            st.session_state.form_step = 1
            st.session_state.form_data = {}
            st.session_state.rule_count = 1
            st.rerun()

        elif btn_form_save:
            doc_rule = []
            for i in range(1, st.session_state.rule_count + 1):
                selected_fund = st.session_state.get(f"fund_{i}", [])
                cpv_value = None
                pkg_value = None

                if "F88" in selected_fund:
                    cpv_value = st.session_state.get(f"cpv_{i}", None)
                if "CIMB" in selected_fund or "MB" in selected_fund:
                    pkg_value = st.session_state.get(f"pkg_{i}", None)

                scheme_rule = {
                    "fund": st.session_state[f"fund_{i}"],
                    "custype": st.session_state[f"custype_{i}"],
                    "score": st.session_state[f"score_{i}"],
                    "paymethod": st.session_state[f"pttg_{i}"],
                    "products": st.session_state[f"nsp_{i}"],
                    "tenor":st.session_state[f"tenor_{i}"],
                    "tradelead": st.session_state[f"vung_{i}"],
                    "province": st.session_state[f"tinh_{i}"],
                    "maxltv": st.session_state[f"ltv_{i}"],
                    "mints": st.session_state[f"ts_min_{i}"],
                    "maxts": st.session_state[f"ts_max_{i}"],
                    "cpv": cpv_value,
                    "pkg": pkg_value
                    }

                doc_rule.append({"SCHEME_RULE": json.dumps(scheme_rule,ensure_ascii=False)})

            st.session_state.form_data['DOCVERDTL'] = doc_rule

            try:
                with st.spinner("⏳ Vui lòng chờ cập nhật dữ liệu...", show_time=True):
                    save_new_form(st.session_state.form_data)
                st.success("Đã tạo mới thành công!")
                st.session_state.form_step = 1
                st.rerun()

            except Exception as e:
                st.error(f"Lỗi khi lưu: {e}")
                get_data.clear()

## CONTAINER 3 - RESULTS
st.html("""
<style>
    .st-key-btn_add_new {
    font-size: 14px;
    display: flex;
    justify-content: flex-end;
    }
</style>
"""

)

with (st.container(key="home_result")):
    with st.container(
            horizontal=True,
            horizontal_alignment="right"
    ):
        if st.button(
                key="btn_add_new",
                label="Thêm mới"
        ):
            add_new_doc()

    df_filtered = df.clone()

    if searchbox and searchbox.strip():

        keywords = searchbox.strip().lower().split()

        for keyword in keywords:

            conditions = []

            for col_name, dtype in df_filtered.schema.items():

                if dtype == pl.List(pl.String):
                    expr = pl.col(col_name).list.join(" ")
                else:
                    expr = pl.col(col_name).cast(pl.String, strict=False)

                conditions.append(
                    expr.str.to_lowercase()
                    .str.contains(keyword, literal=True)
                    .fill_null(False)
                )

            df_filtered = df_filtered.filter(
                pl.any_horizontal(conditions)
            )

    if month:
        df_filtered = df_filtered.filter(pl.col("ISSUED_MONTH").is_in(month))

    if asset:
        df_filtered = df_filtered.filter(pl.col('ASSET').is_in(asset))

    if fund:
        df_filtered = df_filtered.filter(pl.col('FUND').list.set_intersection(fund).list.len()>0)

    if nsp:
        df_filtered = df_filtered.filter(pl.col('PRODUCTS').list.set_intersection(nsp).list.len()>0)

    if pic:
        df_filtered = df_filtered.filter(pl.col('PIC').is_in(pic))

    if status:
        df_filtered = df_filtered.filter(pl.col('STATUS').is_in(status))

    df_display = (df_filtered
          .sort(['DOC_VER_ID','ISSUED_DT'],descending=[False,True])
          .group_by(['DOC_VER_ID','DOC_ID'],maintain_order=True)
          .agg(
        [pl.col('DOC_NAME').first(),
         pl.col('DOC_VER_TYPE').first(),
         pl.col('DOC_NO').first(),
         pl.col('ISSUED_DT').first(),
         pl.col('STATUS').first(),
         pl.col('ASSET').first()
         ]
    )
    )

    if "home_tbl_ver" not in st.session_state:
        st.session_state.home_tbl_ver = 0

    def reset_home_tbl_ver():
        st.session_state.home_tbl_ver += 1

    home_tbl_event = st.dataframe(
        df_display,
        key=f'home_tbl_{st.session_state.home_tbl_ver}',
        on_select = "rerun",
        selection_mode = 'single-cell',
        hide_index=True,
        width="stretch",
        height=740,
        row_height=35,
        column_order=[
            "DOC_NAME",
            "DOC_VER_TYPE",
            "DOC_NO",
            "ISSUED_DT",
            "STATUS",
            "ASSET"
        ],

        column_config={
            "DOC_NAME": st.column_config.TextColumn(
                label="Tên văn bản",
                width="large"
            ),

            "DOC_VER_TYPE": st.column_config.TextColumn(
                label="Loại văn bản",
                width="medium"
            ),

            "DOC_NO": st.column_config.TextColumn(
                label="Số văn bản",
                width="medium"
            ),

            "ISSUED_DT": st.column_config.DateColumn(
                label="Ngày ban hành",
                format="DD/MM/YYYY",
                width="medium"
            ),

            "STATUS": st.column_config.TextColumn(
                label="Trạng thái",
                width="small"
            ),

            "ASSET": st.column_config.TextColumn(
                label="Nhóm tài sản",
                width="small"
            )
        }
    )


    @st.dialog("Chi tiết văn bản", width="large",on_dismiss=reset_home_tbl_ver)
    def show_doc_detail(detail):
        col_dtl_1, col_dtl_2 = st.columns([4,5])
        with col_dtl_1:
            st.markdown('Thông tin cơ bản')
            sub_tbl1 = (detail.select(['DOC_NO','DOC_NAME','PIC','DOC_VER_ID','DOC_TYPE','DOC_LINK'])
                        .group_by(['DOC_NO','DOC_NAME','PIC','DOC_TYPE','DOC_LINK'])
                        .agg([
                pl.col('DOC_VER_ID').n_unique().alias('VER_COUNT')
                ])
                .rename({'DOC_NO':'Số văn bản','DOC_NAME':'Tên văn bản','VER_COUNT':'Số lượng phiên bản','DOC_TYPE':'Loại văn bản',
                         'DOC_LINK':'Link văn bản'})
                ).transpose(include_header=True)

            st.table(sub_tbl1,hide_index=True,hide_header=True)

        with col_dtl_2:
            detail_filtered = detail.clone()
            with st.container(horizontal=True,horizontal_alignment="right"):
                dtl_filt_col1, dtl_filt_col2, dtl_filt_col3 = st.columns(3)
                with dtl_filt_col1:
                    st.selectbox(key='box_sl_ver',index=None,label='',options=detail_filtered.select(['DOC_VER_NO']).unique()
                         ,placeholder='Chọn version',label_visibility='collapsed')

                detail_filtered = detail_filtered.with_columns(
                        pl.col('SCHEME_RULE').str.json_path_match("$.fund").str.json_decode(
                            pl.List(pl.String)).list.eval(pl.element().str.to_uppercase()).alias('FUND'),
                        pl.col('SCHEME_RULE').str.json_path_match("$.products").str.json_decode(
                            pl.List(pl.String)).list.eval(pl.element().str.to_uppercase()).alias('PRODUCTS')
                    )
                with dtl_filt_col2:
                    box_sl_fund = st.selectbox(key='box_sl_fund',index=None,label='',options=detail_filtered.select(pl.col('FUND').explode().unique())
                         ,placeholder='Chọn nguồn',label_visibility='collapsed')

                with dtl_filt_col3:
                    box_sl_nsp = st.selectbox(key='box_sl_nsp', index=None, label='',options=detail_filtered.select(pl.col('PRODUCTS').explode().unique())
                        , placeholder='Chọn sản phẩm', label_visibility='collapsed')

            if box_sl_nsp:
                detail_filtered = detail_filtered.filter(pl.col('PRODUCTS').list.contains(box_sl_nsp))

            with st.container(key='scheme_dtl',
                              border=True
                              ):
                st.markdown('Chi tiết các điều kiện')

            for i, rule in enumerate(detail_filtered['SCHEME_RULE'], start=1):
                key_labels = {
                    'fund':'Nguồn',
                    'custype':'Loại khách hàng',
                    'score':'Điểm',
                    'paymethod':'Phương thức',
                    'products':'Sản phẩm',
                    "tenor": "Kỳ hạn",
                    'tradelead':'Vùng',
                    'province':'Tỉnh',
                    'maxltv':'Max LTV (%)',
                    'mints':'Giá trị vay tối thiểu (triệu)',
                    'maxts': 'Giá trị vay tối đa (triệu)',
                    'cpv': 'Chi phí vay (%)',
                    'pkg': 'Phí ký gửi (%)'

                }
                with st.expander(label=f'Rule {i}', expanded=False):
                    rule = json.loads(rule)
                    rule_tbl = pl.DataFrame({'key': [key_labels.get(key,key) for key in rule.keys()],
                                             'value': [', '.join(map(str,value)) if isinstance(value, list) else str(value) for value in rule.values()]
                                            })
                    st.table(rule_tbl,hide_index=True,hide_header=True)



    if home_tbl_event.selection.cells:
        row_index = home_tbl_event.selection.cells[0][0]
        selected_row = df_display.row(row_index,named=True)
        selected_doc_id = selected_row['DOC_ID']
        selected_ver_id = selected_row["DOC_VER_ID"]
        detail_filtered = df.filter(pl.col('DOC_ID')==selected_doc_id)
        # st.write(selected_doc_id)
        show_doc_detail(detail_filtered)
