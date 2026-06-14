import importlib.util
import json
import os
from pathlib import Path
from datetime import datetime

try:
    import streamlit as st
except ImportError as exc:
    raise ImportError(
        "Streamlit غير مثبت. الرجاء تثبيت المكتبة عبر الأمر:\n"
        "python -m pip install streamlit\n"
        "أو استخدم البيئة الصحيحة التي تحتوي على Streamlit."
    ) from exc

BASE_DIR = Path(__file__).resolve().parent
CODE_FILE = BASE_DIR / "Opd2.Code.py"


def load_opd2_module():
    spec = importlib.util.spec_from_file_location("opd2_code", CODE_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OPD2 = load_opd2_module()


def authenticate(username: str, password: str) -> bool:
    credentials = OPD2.load_credentials()
    return username.strip() == credentials["username"] and password.strip() == credentials["password"]


def authenticate_recovery(recovery_password: str) -> bool:
    credentials = OPD2.load_credentials()
    return recovery_password.strip() == credentials["recovery_password"]


def needs_initial_setup() -> bool:
    credentials_path = BASE_DIR / OPD2.CREDENTIALS_FILE if hasattr(OPD2, 'CREDENTIALS_FILE') else BASE_DIR / 'credentials.json'
    if not credentials_path.exists():
        return True
    credentials = OPD2.load_credentials()
    default_username = getattr(OPD2, 'DEFAULT_USERNAME', 'am3')
    default_password = getattr(OPD2, 'DEFAULT_PASSWORD', '2012')
    default_recovery = getattr(OPD2, 'DEFAULT_RECOVERY_PASSWORD', 'e60_m5')
    return (
        credentials.get('username') == default_username and
        credentials.get('password') == default_password and
        credentials.get('recovery_password') == default_recovery
    )


def render_initial_setup():
    st.header("إعداد الحساب لأول مرة")
    st.info("يُرجى إنشاء اسم مستخدم وكلمة مرور وكلمة سر احتياطية لجهازك.")
    with st.form("initial_setup_form"):
        username = st.text_input("اسم المستخدم الجديد")
        password = st.text_input("كلمة المرور الجديدة", type="password")
        recovery = st.text_input("كلمة السر الاحتياطية", type="password")
        submit = st.form_submit_button("إنشاء الحساب")
    if submit:
        if not username.strip() or not password.strip() or not recovery.strip():
            st.error("جميع الحقول مطلوبة.")
        else:
            OPD2.save_credentials(username.strip(), password.strip(), recovery.strip())
            st.success("تم إنشاء بيانات الاعتماد بنجاح. يمكنك الآن تسجيل الدخول.")
            st.experimental_rerun()


def get_custom_company_data():
    custom_db, custom_names = OPD2.load_custom_companies()
    all_db_files = {**OPD2.DB_FILES, **custom_db}
    all_company_names = {**OPD2.COMPANY_NAMES, **custom_names}
    return custom_db, custom_names, all_db_files, all_company_names


def get_company_filename(company_key: str) -> str:
    custom_db, _, _, _ = get_custom_company_data()
    return custom_db.get(company_key, OPD2.DB_FILES.get(company_key, ""))


def save_company_data(company_key: str, data: dict):
    filename = get_company_filename(company_key)
    if not filename:
        raise ValueError("Company file not found.")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def add_custom_company(name: str, uploaded_file) -> tuple[str, int]:
    custom_db, custom_names, _, all_company_names = get_custom_company_data()
    if not name:
        raise ValueError("اسم الشركة مطلوب.")

    if name in all_company_names.values():
        raise ValueError("هذا الاسم موجود بالفعل.")

    all_keys = list(OPD2.DB_FILES.keys()) + list(custom_db.keys())
    next_id = str(max(int(k) for k in all_keys) + 1) if all_keys else "20"
    filename = f"{name.replace(' ', '_').lower()}_faults.json"
    file_path = BASE_DIR / filename

    if uploaded_file is not None:
        try:
            fault_data = json.load(uploaded_file)
            if not isinstance(fault_data, dict):
                raise ValueError("ملف JSON غير صالح، يجب أن يحتوي على قاموس من الأكواد.")
        except json.JSONDecodeError:
            raise ValueError("ملف JSON غير قابل للقراءة.")
    else:
        fault_data = {}

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(fault_data, f, ensure_ascii=False, indent=4)

    custom_db[next_id] = filename
    custom_names[next_id] = name
    OPD2.save_custom_companies(custom_db, custom_names)
    return next_id, len(fault_data)


def delete_custom_company(company_key: str) -> bool:
    custom_db, custom_names, _, _ = get_custom_company_data()
    if company_key not in custom_names:
        return False
    filename = custom_db[company_key]
    if os.path.exists(filename):
        try:
            os.remove(filename)
        except OSError:
            pass
    del custom_db[company_key]
    del custom_names[company_key]
    OPD2.save_custom_companies(custom_db, custom_names)
    return True


def load_all_data() -> dict:
    return OPD2.load_all_data()


def find_fault(all_databases: dict, company_key: str, code: str):
    code = code.strip().upper()
    if not code:
        return None
    return all_databases.get(company_key, {}).get(code)


def add_fault(all_databases: dict, company_key: str, code: str, problem: str, solution: str) -> None:
    code = code.strip().upper()
    if not code:
        raise ValueError("الكود مطلوب.")
    if not problem.strip() or not solution.strip():
        raise ValueError("الوصف والحل مطلوبان.")
    database = all_databases.setdefault(company_key, {})
    if code in database:
        raise ValueError("هذا الكود موجود بالفعل.")
    database[code] = {"problem": problem.strip(), "solution": solution.strip()}
    save_company_data(company_key, database)


def delete_fault(all_databases: dict, company_key: str, code: str) -> bool:
    code = code.strip().upper()
    database = all_databases.get(company_key, {})
    if code in database:
        del database[code]
        save_company_data(company_key, database)
        return True
    return False


def build_sidebar():
    st.sidebar.title("القسم")
    page = st.sidebar.radio("اختر القسم", ["بحث الأعطال", "سوبر داينو", "إدارة الشركات", "الحماية", "تسجيل الخروج"])
    return page


def render_search_faults(all_databases: dict, all_company_names: dict):
    st.header("🔧 بحث عن كود عطل")
    company_key = st.selectbox("اختر الشركة", options=sorted(all_company_names.keys(), key=lambda x: int(x)), format_func=lambda k: all_company_names[k])
    code = st.text_input("أدخل كود العطل (مثال: P0300)").upper()
    if st.button("بحث"):
        if not code:
            st.warning("الرجاء إدخال الكود.")
        else:
            fault = find_fault(all_databases, company_key, code)
            if fault:
                st.success(f"تم العثور على الكود في {all_company_names[company_key]}")
                st.write("**التشخيص:**", fault["problem"])
                st.write("**الحل:**", fault["solution"])
                st.write("**الوقت:**", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            else:
                st.error(f"لم يُعثر على الكود {code} في قاعدة {all_company_names[company_key]}.")
                st.info("يمكنك إضافته في قسم إضافة كود عطل أسفل الصفحة.")

    st.markdown("---")
    st.subheader("➕ إضافة كود عطل جديد")
    with st.form("add_fault_form"):
        new_company = st.selectbox("اختر الشركة لإضافة الكود إليها", options=sorted(all_company_names.keys(), key=lambda x: int(x)), format_func=lambda k: all_company_names[k])
        new_code = st.text_input("كود العطل").upper()
        new_problem = st.text_area("وصف المشكلة")
        new_solution = st.text_area("الحل المقترح")
        if st.form_submit_button("حفظ الكود"):
            try:
                add_fault(all_databases, new_company, new_code, new_problem, new_solution)
                st.success(f"تم إضافة الكود {new_code} إلى {all_company_names[new_company]}")
            except ValueError as exc:
                st.error(str(exc))

    st.markdown("---")
    st.subheader("🗑️ حذف كود عطل")
    with st.form("delete_fault_form"):
        del_company = st.selectbox("اختر الشركة", options=sorted(all_company_names.keys(), key=lambda x: int(x)), format_func=lambda k: all_company_names[k], key="delete_company")
        del_code = st.text_input("كود العطل للحذف").upper()
        if st.form_submit_button("حذف الكود"):
            if delete_fault(all_databases, del_company, del_code):
                st.success(f"تم حذف الكود {del_code} من {all_company_names[del_company]}")
            else:
                st.error("لم يتم العثور على الكود للحذف.")

    st.markdown("---")
    st.subheader("📌 معلومات الشركات")
    st.write(f"إجمالي الشركات المدعومة: {len(all_company_names)}")
    company_rows = [{"الرقم": key, "اسم الشركة": name, "مخصصة": "نعم" if key not in OPD2.COMPANY_NAMES else "لا"} for key, name in sorted(all_company_names.items(), key=lambda item: int(item[0]))]
    st.table(company_rows)


def render_dyno():
    st.header("🚀 سوبر داينو")
    option = st.radio("ما تريد حسابه؟", ["حصان (HP)", "دورات في الدقيقة (RPM)", "عزم الدوران (Nm)"])

    if option == "حصان (HP)":
        torque = st.number_input("عزم الدوران (Nm)", min_value=0.0, format="%.2f")
        rpm = st.number_input("RPM", min_value=0.0, format="%.2f")
        if st.button("احسب القدرة"):
            if rpm == 0:
                st.error("لا يمكن أن يكون RPM صفر.")
            else:
                hp = torque * rpm / 5252
                st.success(f"التقدير: {hp:.2f} حصان")
    elif option == "دورات في الدقيقة (RPM)":
        hp = st.number_input("القدرة (HP)", min_value=0.0, format="%.2f")
        torque = st.number_input("عزم الدوران (Nm)", min_value=0.0, format="%.2f")
        if st.button("احسب RPM"):
            if torque == 0:
                st.error("لا يمكن أن يكون عزم الدوران صفر.")
            else:
                rpm = hp * 5252 / torque
                st.success(f"التقدير: {rpm:.2f} RPM")
    else:
        hp = st.number_input("القدرة (HP)", min_value=0.0, format="%.2f")
        rpm = st.number_input("RPM", min_value=0.0, format="%.2f")
        if st.button("احسب العزم"):
            if rpm == 0:
                st.error("لا يمكن أن يكون RPM صفر.")
            else:
                torque = hp * 5252 / rpm
                st.success(f"التقدير: {torque:.2f} Nm")


def render_company_management(all_databases: dict, all_company_names: dict, custom_names: dict):
    st.header("🏢 إدارة الشركات")
    st.subheader("إضافة شركة جديدة")
    with st.form("add_company_form"):
        company_name = st.text_input("اسم الشركة الجديدة")
        json_file = st.file_uploader("رفع ملف JSON لبيانات الأعطال (اختياري)", type=["json"])
        if st.form_submit_button("إضافة الشركة"):
            try:
                next_id, fault_count = add_custom_company(company_name.strip(), json_file)
                st.success(f"تم إضافة الشركة '{company_name}' برقم {next_id}. عدد الأكواد: {fault_count}")
            except ValueError as exc:
                st.error(str(exc))

    st.markdown("---")
    st.subheader("حذف شركة مخصصة")
    if custom_names:
        delete_key = st.selectbox("اختر الشركة المخصصة للحذف", options=sorted(custom_names.keys(), key=lambda x: int(x)), format_func=lambda k: custom_names[k])
        if st.button("حذف الشركة المخصصة"):
            if delete_custom_company(delete_key):
                st.success("تم حذف الشركة المخصصة بنجاح.")
            else:
                st.error("فشل حذف الشركة.")
    else:
        st.info("لا توجد شركات مخصصة حالياً.")

    st.markdown("---")
    st.subheader("قائمة الشركات")
    company_rows = [{"الرقم": key, "اسم الشركة": name, "مخصصة": "نعم" if key not in OPD2.COMPANY_NAMES else "لا"} for key, name in sorted(all_company_names.items(), key=lambda item: int(item[0]))]
    st.table(company_rows)


def render_protection():
    st.header("🔐 قسم الحماية")
    credentials = OPD2.load_credentials()
    st.write(f"**اسم المستخدم الحالي:** {credentials['username']}")

    with st.expander("تغيير اسم المستخدم"):
        with st.form("change_username_form"):
            current_password = st.text_input("كلمة المرور الحالية", type="password")
            new_username = st.text_input("اسم المستخدم الجديد")
            if st.form_submit_button("حفظ"):
                if current_password != credentials["password"]:
                    st.error("كلمة المرور الحالية غير صحيحة.")
                elif not new_username.strip():
                    st.error("اسم المستخدم الجديد لا يمكن أن يكون فارغاً.")
                else:
                    OPD2.save_credentials(new_username.strip(), credentials["password"], credentials["recovery_password"])
                    st.success("تم تغيير اسم المستخدم.")

    with st.expander("تغيير كلمة المرور"):
        with st.form("change_password_form"):
            current_password = st.text_input("كلمة المرور الحالية", type="password", key="password_current")
            new_password = st.text_input("كلمة المرور الجديدة", type="password", key="password_new")
            if st.form_submit_button("حفظ"):
                if current_password != credentials["password"]:
                    st.error("كلمة المرور الحالية غير صحيحة.")
                elif not new_password.strip():
                    st.error("كلمة المرور الجديدة لا يمكن أن تكون فارغة.")
                else:
                    OPD2.save_credentials(credentials["username"], new_password.strip(), credentials["recovery_password"])
                    st.success("تم تغيير كلمة المرور.")

    with st.expander("تغيير كلمة السر الاحتياطية"):
        with st.form("change_recovery_form"):
            current_password = st.text_input("كلمة المرور الحالية", type="password", key="recovery_current")
            new_recovery = st.text_input("كلمة السر الاحتياطية الجديدة", type="password", key="recovery_new")
            if st.form_submit_button("حفظ"):
                if current_password != credentials["password"]:
                    st.error("كلمة المرور الحالية غير صحيحة.")
                elif not new_recovery.strip():
                    st.error("كلمة السر الاحتياطية لا يمكن أن تكون فارغة.")
                else:
                    OPD2.save_credentials(credentials["username"], credentials["password"], new_recovery.strip())
                    st.success("تم تغيير كلمة السر الاحتياطية.")


def main():
    st.set_page_config(page_title="OBD Fault Web App", layout="wide")
    st.title("تطبيق أعطال السيارات")

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if needs_initial_setup():
        render_initial_setup()
        return

    if not st.session_state.authenticated:
        st.subheader("تسجيل الدخول")
        with st.form("login_form"):
            username = st.text_input("اسم المستخدم")
            password = st.text_input("كلمة المرور", type="password")
            login_pressed = st.form_submit_button("دخول")
        if login_pressed:
            if authenticate(username, password):
                st.session_state.authenticated = True
                st.experimental_rerun()
            else:
                st.error("اسم المستخدم أو كلمة المرور غير صحيح.")

        with st.expander("تسجيل الدخول الاحتياطي"):
            recovery = st.text_input("كلمة السر الاحتياطية", type="password")
            if st.button("استخدام كلمة السر الاحتياطية"):
                if authenticate_recovery(recovery):
                    st.session_state.authenticated = True
                    st.experimental_rerun()
                else:
                    st.error("كلمة السر الاحتياطية غير صحيحة.")

        st.info("إذا لم تمتلك بيانات اعتماد، يمكنك إنشاء حساب جديد عند أول تشغيل.")
        return

    page = build_sidebar()
    all_databases = load_all_data()
    _, custom_names, _, all_company_names = get_custom_company_data()

    if page == "بحث الأعطال":
        render_search_faults(all_databases, all_company_names)
    elif page == "سوبر داينو":
        render_dyno()
    elif page == "إدارة الشركات":
        render_company_management(all_databases, all_company_names, custom_names)
    elif page == "الحماية":
        render_protection()
    elif page == "تسجيل الخروج":
        st.session_state.authenticated = False
        st.success("تم تسجيل الخروج.")
        st.experimental_rerun()


if __name__ == "__main__":
    main()
