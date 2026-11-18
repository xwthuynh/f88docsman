# from asyncio import start_unix_server
from logging import PlaceHolder
import streamlit as st
import pandas as pd
from pathlib import Path
import pyodbc
import sqlalchemy as sql
# from jsonschema.benchmarks import contains
from polars.functions.aggregation import horizontal
from sqlalchemy import create_engine, text
import os
from contextlib import closing
import json


## CONNECT DATABASE:
SQL_SERVER = "10.2.200.7"
SQL_DATABASE = "sanpham"
SQL_USERNAME = "sp_khanhhp2"
SQL_PASSWORD = "Abcd@1234"

def get_connection():

    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={SQL_DATABASE};"
        f"UID={SQL_USERNAME};"
        f"PWD={SQL_PASSWORD};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
        "Connection Timeout=10;"
    )

    conn = pyodbc.connect(connection_string)

    return conn


## DATABASE FUNCTIONS
def save_new_form(form_data):
    doc = form_data['DOCS']
    docver = form_data['DOCVERS']
    docrule = form_data['DOCVERDTL']

    conn = get_connection()
    conn.autocommit = False

    try:
        cursor = conn.cursor()
        cursor.execute("""
                    INSERT INTO ptsp.DOCS
                    (
                        DOC_NAME,
                        DOC_NO,
                        DOC_TYPE,
                        ASSET,
                        DEPARTMENT,
                        DOC_LINK
                    )

                    OUTPUT INSERTED.DOC_ID

                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                       doc["DOC_NAME"],
                       doc["DOC_NO"],
                       doc["DOC_TYPE"],
                       ",".join(doc["ASSET"]),
                       doc["DEPARTMENT"],
                       doc['DOC_LINK']
                       )
        doc_id = cursor.fetchone()[0]

        cursor.execute("""
                INSERT INTO ptsp.DOCVERS
                (
                    DOC_ID,
                    DOC_VER_NO,
                    DOC_VER_TYPE,
                    PIC,
                    ISSUED_DT,
                    EFFECTIVE_FROM,
                    EFFECTIVE_TO
                )
                
                OUTPUT INSERTED.DOC_VER_ID

                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                   doc_id,
                   docver["DOC_VER_NO"],
                   docver["DOC_VER_TYPE"],
                   docver["PIC"],
                   docver["ISSUED_DT"],
                   docver["EFFECTIVE_FROM"],
                   docver["EFFECTIVE_TO"]
                   )
        doc_ver_id = cursor.fetchone()[0]

        for rule in docrule:
            cursor.execute("""
                   INSERT INTO ptsp.DOCVERDTL
                   (
                       DOC_VER_ID,
                       SCHEME_RULE
                   )

                   VALUES (?, ?)
               """,
                       doc_ver_id,
                       rule["SCHEME_RULE"]
                       )


        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


## GET DATA:
query_doc = "SELECT * FROM ptsp.DOCS"
query_ver = "SELECT * FROM ptsp.DOCVERS"
query_rule = "SELECT * FROM ptsp.DOCVERDTL"


@st.cache_data(ttl=300)
def get_data(query):

    conn = get_connection()

    try:
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

        df = pd.DataFrame(
            [tuple(row) for row in rows],
            columns=columns
        )

        return df

    finally:
        conn.close()

doc = get_data(query_doc)
doc_ver = get_data(query_ver)
doc_rule = get_data(query_rule)

## PROCESS DATA:
import polars as pl

doc = pl.from_pandas(doc)
doc_ver = pl.from_pandas(doc_ver)
doc_rule = pl.from_pandas(doc_rule)

df = (doc_ver.select(['DOC_VER_ID', 'DOC_VER_NO','DOC_ID', 'DOC_VER_TYPE', 'PIC', 'ISSUED_DT', 'EFFECTIVE_FROM', 'EFFECTIVE_TO',
                      'STATUS'])
      .join(doc.select(['DOC_ID', 'DOC_NAME', 'DOC_TYPE','DOC_NO', 'ASSET','DOC_LINK']), how='left', on=['DOC_ID'])
      .join(doc_rule.select(['DOC_VER_ID', 'SCHEME_RULE']), how='left', on=['DOC_VER_ID'])
      )

df = df.with_columns(pl.col('ISSUED_DT').cast(pl.Utf8).str.to_date(format='%Y-%m-%d').dt.strftime('%Y%m%d').str.slice(0,6).alias('ISSUED_MONTH'))

#1/ GET JSON FILTER:
df = df.with_columns(
    pl.col('SCHEME_RULE').str.json_path_match("$.fund").str.json_decode(pl.List(pl.String)).list.eval(pl.element().str.to_uppercase()).alias('FUND'),
            pl.col('SCHEME_RULE').str.json_path_match("$.products").str.json_decode(pl.List(pl.String)).list.eval(pl.element().str.to_uppercase()).alias('PRODUCTS')
)

fund_fil = df.select(pl.col('FUND').explode().unique())
nsp_fil = df.select(pl.col('PRODUCTS').explode().unique())


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

@st.dialog("Tạo văn bản mới",width="large",on_dismiss=reset_new_doc)
def add_new_doc():
    step = st.session_state.form_step

    st.caption(f"Bước {step}/3")

    if step == 1:

        with st.form(key='form_new_doc'):
            form_docname = st.text_input(label='Tên văn bản',placeholder='Nhập tên văn bản')

            new_doc_col1, new_doc_col2 = st.columns(2)
            with new_doc_col1:
                form_docno = st.text_input(label='Số văn bản',placeholder='Nhập số văn bản')
            with new_doc_col2:
                form_doclink = st.text_input(label='Link văn bản',type='url',placeholder='Dán đường link văn bản')

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
                                              'ASSET':form_asset,'DEPARTMENT':form_dept,'DOC_LINK':form_doclink}
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
                                        options=['Huỳnh Phùng Khánh', 'Nhâm Văn Quý', 'Nguyễn Thị Xuyến',
                                                 'Đặng Thị Thu Hà', 'Nguyễn Minh Ngọc','Phùng Thị Hồng Vân',
                                                 'Nguyễn Gia Phương Anh', 'Trần Thu Huyền', 'Nguyễn Thị Thùy Dương',
                                                 'Đoàn Hồng Ngọc', 'Trịnh Minh Anh','Phạm Thị Phương'], label='PIC',
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
                    st.multiselect("Nguồn", ["F88", 'CIMB', 'MB'], key=f"fund_{i}")
                with exp_col_2:
                    st.multiselect("Loại khách hàng", ["MỚI", 'CŨ'], key=f"custype_{i}")
                with exp_col_3:
                    st.multiselect("Điểm", ["Tốt","Khá","Trung bình","Kém","A", 'B', 'C', 'D', 'E'], key=f"score_{i}")
                with exp_col_4:
                    st.multiselect("Nhóm sản phẩm", ["OT BAU KHCN","OT BAU KHDN", "OT BAU HKD", "OT 3.6", 'OT 4.0', 'OT MYF88', 'OT KHQL'
                        , 'LĐTD', 'CN', 'VCVP', 'TXCN', 'TT', '6X', 'XM 5.4', 'XM KHQL', 'XM MYF88', 'XM GCK',
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
                    st.number_input("CPV (%)",key=f"cpv_{i}" )

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
                scheme_rule = {
                    "fund": st.session_state[f"fund_{i}"],
                    "custype": st.session_state[f"custype_{i}"],
                    "score": st.session_state[f"score_{i}"],
                    "paymethod": st.session_state[f"pttg_{i}"],
                    "products": st.session_state[f"nsp_{i}"],
                    "tradelead": st.session_state[f"vung_{i}"],
                    "province": st.session_state[f"tinh_{i}"],
                    "maxltv": st.session_state[f"ltv_{i}"],
                    "mints": st.session_state[f"ts_min_{i}"],
                    "maxts": st.session_state[f"ts_max_{i}"],
                    "cpv": st.session_state[f"cpv_{i}"]
                }
                doc_rule.append({"SCHEME_RULE": json.dumps(scheme_rule,ensure_ascii=False)})

            st.session_state.form_data['DOCVERDTL'] = doc_rule

            try:
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

    if searchbox:
        df_filtered = df_filtered.filter(pl.col("ISSUED_MONTH").is_in(month))

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
          .group_by(['DOC_VER_ID','DOC_ID'])
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
            sub_tbl1 = (detail.select(['DOC_NO','DOC_NAME','PIC','DOC_VER_ID','DOC_TYPE'])
                        .group_by(['DOC_NO','DOC_NAME','PIC','DOC_TYPE'])
                        .agg([
                pl.col('DOC_VER_ID').n_unique().alias('VER_COUNT')
                ])
                .rename({'DOC_NO':'Số văn bản','DOC_NAME':'Tên văn bản','VER_COUNT':'Số lượng phiên bản','DOC_TYPE':'Loại văn bản'})
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
                    'tradelead':'Vùng',
                    'province':'Tỉnh',
                    'maxltv':'Max LTV (%)',
                    'mints':'Giá trị vay tối thiểu (triệu)',
                    'maxts': 'Giá trị vay tối đa (triệu)',
                    'cpv': 'Chi phí vay (%)'

                }
                with st.expander(label=f'Rule {i}', expanded=True):
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

