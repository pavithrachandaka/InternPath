import streamlit as st
import urllib.parse
import pandas as pd
from datetime import datetime
import pymongo
import bcrypt
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from deep_translator import GoogleTranslator
from translations import TRANSLATIONS  # Static UI translations

# ---------------- MongoDB Config ----------------
MONGO_URI = "mongodb+srv://bhuvanasaichappa22_db_user:5YDDctnDz02wer5K@cluster0.awalbog.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = pymongo.MongoClient(MONGO_URI)
db = client["InternshipPortal"]
users_collection = db["users"]

# --- Gmail SMTP Config ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "pminternshiplmtd.gov.in@gmail.com"
SMTP_PASSWORD = "pqcjbsovswsbabml"

# Supported languages
LANGUAGES = list(TRANSLATIONS.keys())

# Initialize default language
if 'target_language' not in st.session_state:
    st.session_state['target_language'] = 'English'

# --- TEXTBEE SMS FUNCTION ---
TEXTBEE_API_KEY = "9223d5ba-9762-41c5-b8e7-69c225be999e"  # Set to your actual TextBee API key
TEXTBEE_DEVICE_ID = "68d14f2e3d44c97447b1541c"  # Set to your actual TextBee device ID
BASE_URL = 'https://api.textbee.dev/api/v1'

def format_mobile_number(mobile):
    cleaned = ''.join(filter(str.isdigit, str(mobile)))
    if cleaned.startswith('91') and len(cleaned) == 12:
        return f'+{cleaned}'
    elif len(cleaned) == 10:
        return f'+91{cleaned}'
    elif cleaned.startswith('0') and len(cleaned) == 11:
        return f'+91{cleaned[1:]}'
    elif str(mobile).startswith('+'):
        return str(mobile)
    else:
        return f'+{cleaned}'

def send_application_sms(to_mobile, applicant_name, internship_title, company_name, application_id):
    if not TEXTBEE_API_KEY or not TEXTBEE_DEVICE_ID:
        st.warning(translate("TextBee API key or Device ID not set. SMS not sent."))
        return False
    # Robust phone formatting
    cleaned = ''.join(filter(str.isdigit, str(to_mobile)))
    if to_mobile.startswith('+'):
        sms_number = to_mobile
    elif cleaned.startswith('91') and len(cleaned) == 12:
        sms_number = f'+{cleaned}'
    elif len(cleaned) == 10:
        sms_number = f'+91{cleaned}'
    elif cleaned.startswith('0') and len(cleaned) == 11:
        sms_number = f'+91{cleaned[1:]}'
    else:
        sms_number = f'+{cleaned}'

    # Only translate the static parts, keep applicant_name, internship_title, application_id, PM Internship Team in English
    message_body = (
        f"{translate('Hi')} {applicant_name}, "
        f"{translate('your application for')} {internship_title} "
        f"{translate('at')} {company_name} "
        f"(ID: {application_id}) "
        f"{translate('has been received.')} - PM Internship Team"
    )

    url = f"{BASE_URL}/gateway/devices/{TEXTBEE_DEVICE_ID}/send-sms"
    payload = {
        'recipients': [sms_number],
        'message': message_body
    }
    headers = {'x-api-key': TEXTBEE_API_KEY}
    try:
        import requests
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in (200, 201):
            result = response.json()
            if result.get("success") or result.get("status") == "success":
                return True
            else:
                return True  # treat as success if 201
        else:
            try:
                error_msg = response.json().get('message', response.text)
            except Exception:
                error_msg = response.text
            st.error(f"{translate('Failed to send confirmation SMS')}: HTTP {response.status_code} - {error_msg}")
            return False
    except Exception as e:
        st.error(f"{translate('Failed to send confirmation SMS')}: {e}")
        return False

# ---------------- Translation Functions ----------------
def translate(text):
    target_lang = st.session_state['target_language']
    if target_lang == 'English' or not text.strip():
        return text
    try:
        # Check in dataset first
        translated = TRANSLATIONS.get(target_lang, {}).get(text)
        if translated:  # if found in dataset
            return translated
        # else use deep-translator
        return GoogleTranslator(source='auto', target=target_lang).translate(text)
    except Exception as e:
        # (optional) log the error if needed: print(f"Translation error: {e}")
        return text

def translate_dynamic(text):
    target_lang = st.session_state['target_language']
    if target_lang == 'English' or not text.strip():
        return text
    try:
        return GoogleTranslator(source='auto', target=target_lang).translate(text)
    except:
        return text

# ---------------- Email Function ----------------
def send_application_email(to_email, applicant_name, internship_title, company_name, application_id):
    subject = f"{translate('Application Confirmation')}: {internship_title} at {company_name}"
    body = f"""
{translate('Dear')} {applicant_name},

{translate('Thank you for applying for the position of')} {internship_title} {translate('at')} {company_name}.

{translate('Your application has been received successfully.')}
{translate('Application ID')}: {application_id}
{translate('Date')}: {datetime.now().strftime('%B %d, %Y')}

{translate('We will review your application and get back to you soon.')}

{translate('Best regards')},
PM Internship Team
"""
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"{translate('Failed to send confirmation email')}: {e}")
        return False

# ---------------- Data Loading ----------------
@st.cache_data
def load_data():
    try:
        students = pd.read_csv('student_profiles_dataset.csv')
        internships = pd.read_csv('pm_internship_opportunities.csv')
        applications = pd.read_csv('student_applications.csv')
        companies = pd.read_csv('companies_dataset.csv')
        skills_master = pd.read_csv('skills_master.csv')
        it_sector = pd.read_csv('it_sector.csv')  # Load IT sector dataset
        return students, internships, applications, companies, skills_master, it_sector
    except FileNotFoundError as e:
        st.error(f"{translate('Dataset file not found')}: {e}")
        return None, None, None, None, None, None

# ---------------- Recommendation Logic ----------------
def get_recommendations_pages(internships_df, student_profile):
    sector = student_profile['preferred_sector']
    location = student_profile['preferred_location']
    education = student_profile['education_level']
    skills = set([s.strip().lower() for s in student_profile['skills'].split(',')])

    # Education hierarchy
    education_hierarchy = ["High School", "Diploma", "Undergraduate"]
    if education not in education_hierarchy:
        allowed_educations = [education]
    else:
        idx = education_hierarchy.index(education)
        allowed_educations = education_hierarchy[:idx+1][::-1]

    recs = []
    for _, internship in internships_df.iterrows():
        # Strict sector, education, and location filter
        if internship['sector'] != sector:
            continue
        if internship['education_requirement'] not in allowed_educations:
            continue
        if internship['location'] != location:
            continue
        required_skills = set([s.strip().lower() for s in internship['required_skills'].split(',') if s.strip()])
        skill_overlap = len(skills.intersection(required_skills))

        # Skill filter logic
        if education == "High School":
            if required_skills and not required_skills.issubset(skills):
                continue
        else:
            if required_skills and skill_overlap == 0:
                continue

        match_score = 6 + ((skill_overlap / len(required_skills)) * 4 if len(required_skills) > 0 else 0)
        recs.append((internship, int((match_score / 10) * 100)))

    recs.sort(key=lambda x: x[1], reverse=True)
    page_size = 5
    pages = [recs[i:i + page_size] for i in range(0, len(recs), page_size)]
    return pages

# ---------------- Application Form ----------------
def show_application_form(internship):
    internship_title = internship['title']
    company_name = internship['company']
    internship_id = internship['internship_id']

    st.markdown("---")
    st.subheader(f"📝 {translate('Apply for')} {translate_dynamic(internship_title)}")
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #e3f2fd 0%, #f0f8f0 100%); padding: 16px; border-radius: 10px; border-left: 5px solid #1976d2; margin-bottom: 10px;">
        <span style="font-size: 18px; color: #1976d2; font-weight: bold;">🏢 {translate('Company')}:</span> <span style="font-size: 17px; color: #333;">{translate_dynamic(company_name)}</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown(translate("Please fill in your details to complete the application:"))

    if 'application_submitted' not in st.session_state:
        st.session_state['application_submitted'] = False

    with st.form(key=f"application_form_{internship_id}"):
        col1, col2 = st.columns(2)
        with col1:
            applicant_name = st.text_input(translate("Full Name *"), placeholder=translate("Enter your full name"))
            email = st.text_input(translate("Email Address *"), placeholder=translate("your.email@example.com"))
        with col2:
            mobile = st.text_input(translate("Mobile Number *"), placeholder="+91 XXXXXXXXXX")
            current_location = st.text_input(translate("Current Location"), placeholder=translate("City, State"))
        cover_letter = st.text_area(
            translate("Why are you interested in this internship? (Optional)"),
            placeholder=translate("Brief message about your interest..."),
            height=100
        )
        resume_file = st.file_uploader(
            translate("Upload Resume (Optional)"),
            type=['pdf', 'doc', 'docx'],
            help=translate("Upload your resume in PDF or Word format")
        )
        agree_terms = st.checkbox(
            translate("I agree to the Terms & Conditions and Privacy Policy *"), value=False
        )
        col_submit, col_cancel = st.columns([1, 1])
        with col_submit:
            submit_button = st.form_submit_button(translate(" Submit Application"), type="primary", use_container_width=True)
        with col_cancel:
            cancel_button = st.form_submit_button(translate("❌ Cancel"), use_container_width=True)

        if submit_button:
            errors = []
            if not applicant_name or len(applicant_name.strip()) < 2:
                errors.append(translate("Please enter a valid full name"))
            if not email or "@" not in email or "." not in email:
                errors.append(translate("Please enter a valid email address"))
            if not mobile or len(mobile.replace(" ", "").replace("+", "").replace("-", "")) < 10:
                errors.append(translate("Please enter a valid mobile number"))
            if not agree_terms:
                errors.append(translate("Please agree to Terms & Conditions"))
            if errors:
                for error in errors:
                    st.error(f"❌ {error}")
            else:
                with st.spinner(translate("Processing your application...")):
                    time.sleep(2)
                st.success(translate("🎉 Application Submitted Successfully!"))
                st.session_state['no_of_applications'] += 1

                application_id = f"APP{internship_id}{int(time.time())}"
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #e0f7fa 0%, #e8f5e9 100%); padding: 24px; border-radius: 16px; border-left: 7px solid #43a047; margin: 20px 0; box-shadow: 0 4px 16px #b2dfdb;">
                    <p style="font-size: 18px; margin-bottom: 8px;"><span style='color:#1a237e; font-weight:700;'>👤 {translate('Name')}:</span> <span style='color:#222'>{applicant_name}</span></p>
                    <p style="font-size: 18px; margin-bottom: 8px;"><span style='color:#1a237e; font-weight:700;'>📧 {translate('Email')}:</span> <span style='color:#222'>{email}</span></p>
                    <p style="font-size: 18px; margin-bottom: 8px;"><span style='color:#1a237e; font-weight:700;'>📱 {translate('Mobile')}:</span> <span style='color:#222'>{mobile}</span></p>
                    <p style="font-size: 18px; margin-bottom: 8px;"><span style='color:#1a237e; font-weight:700;'>🏢 {translate('Position')}:</span> <span style='color:#1976d2'>{translate_dynamic(internship_title)}</span></p>
                    <p style="font-size: 18px; margin-bottom: 8px;"><span style='color:#1a237e; font-weight:700;'>🏭 {translate('Company')}:</span> <span style='color:#1976d2'>{translate_dynamic(company_name)}</span></p>
                    <p style="font-size: 18px; margin-bottom: 8px;"><span style='color:#1a237e; font-weight:700;'>📅 {translate('Application Date')}:</span> <span style='color:#222'>{datetime.now().strftime('%B %d, %Y')}</span></p>
                    <p style="font-size: 18px; margin-bottom: 0;"><span style='color:#1a237e; font-weight:700;'>🆔 {translate('Application ID')}:</span> <span style='color:#222'>{application_id}</span></p>
                </div>
                """, unsafe_allow_html=True)

                st.markdown(f"### 🚀 {translate('What\'s Next?')}")
                st.info(
                    f"{translate('📩 Confirmation Email: You\'ll receive a confirmation email shortly.')}  \n"
                    f"{translate('⏱ Review Process: Applications are typically reviewed within 5-7 business days.')}  \n"
                    f"{translate('📱 Status Updates: Check your email and phone for updates from the company.')}  \n"
                    f"{translate('🔄 Follow Up: You can follow up after 1 week if you don\'t hear back.')}")

                application_data = {
                    'name': applicant_name,
                    'email': email,
                    'mobile': mobile,
                    'internship_id': internship_id,
                    'internship_title': internship_title,
                    'company': company_name,
                    'application_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'Applied'
                }
                if 'applications' not in st.session_state:
                    st.session_state.applications = []
                st.session_state.applications.append(application_data)

                email_sent = send_application_email(email, applicant_name, internship_title, company_name, application_id)
                if email_sent:
                    st.success(translate("Confirmation email sent successfully!"))
                else:
                    st.warning(translate("Failed to send confirmation email."))

                sms_sent = send_application_sms(mobile, applicant_name, internship_title, company_name, application_id)
                if sms_sent:
                    st.success("📱 SMS sent successfully!")
                else:
                    st.warning(translate("Failed to send confirmation SMS."))

                st.balloons()
                st.session_state['application_submitted'] = True

        if cancel_button:
            st.session_state.show_application_form = False
            st.session_state.selected_internship = None
            st.session_state.application_submitted = False
            st.rerun()

    if st.session_state.get('application_submitted', False):
        if st.button(translate("Get More Recommendations")):
            st.session_state.show_application_form = False
            st.session_state.selected_internship = None
            # Cycle to next recommendations page
            if st.session_state.recommendations_pages:
                st.session_state.page_index = (st.session_state.page_index + 1) % len(st.session_state.recommendations_pages)
            else:
                st.session_state.page_index = 0
            st.rerun()

# ---------------- IT Sector Courses Display ----------------
def show_it_courses(it_sector_df):
    st.subheader(f"💻 {translate('IT Sector Training Courses')}")
    
    # Filter options
    col1, col2 = st.columns(2)
    with col1:
        providers = ['All'] + list(it_sector_df['Provider'].unique())
        selected_provider = st.selectbox(translate("Filter by Provider"), providers)
    
    with col2:
        # Extract numeric duration for filtering
        durations = it_sector_df['Duration'].str.extract(r'(\d+)')[0].astype(float).dropna()
        if not durations.empty:
            min_duration = int(durations.min())
            max_duration = int(durations.max())
            duration_range = st.slider(
                translate("Duration Range (hours)"), 
                min_value=min_duration, 
                max_value=max_duration, 
                value=(min_duration, max_duration)
            )
        else:
            duration_range = (0, 100)
    
    # Filter data
    filtered_df = it_sector_df.copy()
    if selected_provider != 'All':
        filtered_df = filtered_df[filtered_df['Provider'] == selected_provider]
    
    # Filter by duration
    filtered_df['Duration_Hours'] = filtered_df['Duration'].str.extract(r'(\d+)').astype(float)
    filtered_df = filtered_df[
        (filtered_df['Duration_Hours'] >= duration_range[0]) & 
        (filtered_df['Duration_Hours'] <= duration_range[1])
    ].dropna(subset=['Duration_Hours'])
    
    st.write(f"{translate('Showing')} {len(filtered_df)} {translate('out of')} {len(it_sector_df)} {translate('courses')}")
    
    # Display courses in cards
    for idx, course in filtered_df.iterrows():
        with st.container():
            st.markdown(f"""
            <div style="border: 2px solid #e1f5fe; border-radius: 12px; padding: 20px; margin: 15px 0;
                            background: linear-gradient(135deg, #f0f4ff 0%, #e8f4fd 100%); box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);">
                <h4 style="color: #1976d2; margin: 0 0 10px 0;">{translate_dynamic(course['Title'])}</h4>
                <p style="color: #424242; margin: 5px 0;"><strong>🏫 {translate('Provider')}:</strong> {translate_dynamic(course['Provider'])}</p>
                <p style="color: #424242; margin: 5px 0;"><strong>⏱ {translate('Duration')}:</strong> {course['Duration']}</p>
                <p style="color: #424242; margin: 5px 0;"><strong>🔗 {translate('Course Link')}:</strong> <a href="{course['URL']}" target="_blank" style="color: #1976d2; text-decoration: none;">{translate('Visit Course')}</a></p>
            </div>
            """, unsafe_allow_html=True)
            
            col_save_course, col_view_details = st.columns([1, 1])
            with col_save_course:
                if st.button(f"{translate('Save Course')}", key=f"save_course_{idx}"):
                    if 'saved_courses' not in st.session_state:
                        st.session_state.saved_courses = []
                    
                    course_data = {
                        'title': course['Title'],
                        'provider': course['Provider'],
                        'duration': course['Duration'],
                        'url': course['URL'],
                        'saved_date': datetime.now().strftime('%Y-%m-%d')
                    }
                    
                    # Check if already saved
                    already_saved = any(
                        saved_course['title'] == course['Title'] 
                        for saved_course in st.session_state.saved_courses
                    )
                    
                    if not already_saved:
                        st.session_state.saved_courses.append(course_data)
                        st.success(f"{translate('Course saved successfully!')}")
                    else:
                        st.info(f"{translate('Course already saved!')}")
            
            with col_view_details:
                if st.button(f"{translate('Visit Course')}", key=f"visit_course_{idx}"):
                    st.markdown(f"[{translate('Open Course')}]({course['URL']})")

# ---------------- Enhanced Dashboard ----------------
def render_dashboard(internships, it_sector_df):
    st.subheader("📊 Dashboard")

    # First row
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Internships", f"{len(internships):,}")
    with col2:
        st.metric("Sectors", internships['sector'].nunique())

    # Second row
    col3, col4 = st.columns(2)
    with col3:
        avg_stipend = internships['stipend'].mean() if 'stipend' in internships else 0
        st.metric("Stipend", f"₹{avg_stipend:,.0f}")
    with col4:
        st.metric("Applied", f"{st.session_state.get('no_of_applications', 0):,}")

    st.markdown("---")
    st.subheader("💻 IT Training Overview")

    # IT Courses row
    col5, col6 = st.columns(2)
    with col5:
        st.metric("Courses", f"{len(it_sector_df):,}")
    with col6:
        st.metric("Providers", it_sector_df['Provider'].nunique())

    col7, col8 = st.columns(2)
    with col7:
        durations = it_sector_df['Duration'].str.extract(r'(\d+)')[0].astype(float).dropna()
        avg_duration = durations.mean() if not durations.empty else 0
        st.metric("Duration", f"{avg_duration:.0f} hours")
    with col8:
        saved_courses_count = len(st.session_state.get('saved_courses', []))
        st.metric("Saved", f"{saved_courses_count:,}")

    # Top providers chart data
    if len(it_sector_df) > 0:
        st.markdown("---")
        st.subheader(f"📈 {translate('Top Training Providers')}")
        
         # Clean the 'Provider' column to ensure accurate counting by removing extra spaces
        cleaned_providers = it_sector_df['Provider'].str.strip()
        provider_counts = cleaned_providers.value_counts().head(10)
        
        # Create a simple bar chart using Streamlit
        chart_data = pd.DataFrame({
            'Provider': provider_counts.index,
            'Courses': provider_counts.values
        })
        st.bar_chart(chart_data.set_index('Provider'))
    
    # Saved content sections
    if st.session_state.get('saved_jobs'):
        st.markdown("---")
        st.subheader(f"⭐ {translate('Saved Internships')}")
        for i, job in enumerate(st.session_state.saved_jobs, 1):
            st.markdown(f"{i}.** {translate_dynamic(job['title'])} - {translate_dynamic(job['company'])} | ₹{job['stipend']:,}/month")
    
    if st.session_state.get('saved_courses'):
        st.markdown("---")
        st.subheader(f"📚 {translate('Saved Courses')}")
        for i, course in enumerate(st.session_state.saved_courses, 1):
            st.markdown(f"{i}.** {translate_dynamic(course['title'])} - {translate_dynamic(course['provider'])} ({course['duration']})")
    
    # Recent applications
    if st.session_state.get('applications'):
        st.markdown("---")
        st.subheader(f"📝 {translate('Recent Applications')}")
        recent_apps = st.session_state.applications[-3:]  # Show last 3 applications
        for app in recent_apps:
            st.markdown(f"• {translate_dynamic(app['internship_title'])} at {translate_dynamic(app['company'])} - {app['application_date'][:10]}")

# ---------------- Auth UI ----------------
def show_auth_ui():
    st.title("InternPath")
    if 'auth_mode' not in st.session_state:
        st.session_state['auth_mode'] = 'login'
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
    if st.session_state['auth_mode'] == 'login':
        st.subheader("Login")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login"):
            user = users_collection.find_one({"email": email})
            if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
                st.session_state['authenticated'] = True
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid email or password.")
        st.markdown("Don't have an account? ")
        if st.button("Go to Signup"):
            st.session_state['auth_mode'] = 'signup'
            st.rerun()
    else:
        st.subheader("Signup")
        name = st.text_input("Name", key="signup_name")
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Signup"):
            if users_collection.find_one({"email": email}):
                st.error("Email already exists.")
            else:
                hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
                users_collection.insert_one({"name": name, "email": email, "password": hashed})
                st.success("Signup successful! Please login.")
                st.session_state['auth_mode'] = 'login'
                st.rerun()
        st.markdown("Already have an account?")
        if st.button("Go to Login"):
            st.session_state['auth_mode'] = 'login'
            st.rerun()

# --- Main Auth Gate ---
if 'authenticated' not in st.session_state or not st.session_state['authenticated']:
    show_auth_ui()
    st.stop()

# ---------------- Main App ----------------
def main():
    st.set_page_config(page_title=" Internship Recommendation Engine", page_icon="🎯", layout="wide")

    if 'no_of_applications' not in st.session_state:
        st.session_state['no_of_applications'] = 0
    if 'saved_jobs' not in st.session_state:
        st.session_state.saved_jobs = []
    if 'saved_courses' not in st.session_state:
        st.session_state.saved_courses = []
    if 'applications' not in st.session_state:
        st.session_state.applications = []

    # --- Language Selection ---
    st.sidebar.header("🌐 " + translate("Select Language"))
    st.session_state['target_language'] = st.sidebar.selectbox(
        translate("Language"), LANGUAGES, index=LANGUAGES.index(st.session_state['target_language'])
    )
    st.sidebar.markdown(f"Current Language: {st.session_state['target_language']}")

    st.title(translate("🎯  Internship Recommendation Engine"))
    st.markdown(translate("Find the perfect internship match based on your profile!"))

    # Load all datasets including IT sector
    students, internships, applications, companies, skills_master, it_sector = load_data()
    if internships is None or it_sector is None:
        st.error(translate("Failed to load required datasets"))
        return
    
    st.session_state.internships = internships
    st.session_state.it_sector = it_sector

    # --- Tab Navigation ---
    tab1, tab2, tab3 = st.tabs([
        f"🎯 {translate('Internships')}",
        f"💻 {translate('Courses')}",
        f"📊 {translate('Dashboard')}"
    ])

    with tab1:
        # --- Sidebar Profile ---
        st.sidebar.header("📝 " + translate("Your Profile"))
        name = st.sidebar.text_input(translate("Name"), translate("Your Name"))
        age = st.sidebar.slider(translate("Age"), 18, 30, 22)

        # --- Education Mapping ---
        EDUCATION_OPTIONS = {
            "High School": translate("High School"),
            "Diploma": translate("Diploma"),
            "Undergraduate": translate("Undergraduate")
        }
        education_choice = st.sidebar.selectbox(translate("Education Level"), list(EDUCATION_OPTIONS.values()))
        # Always store English value
        education_level = [k for k, v in EDUCATION_OPTIONS.items() if v == education_choice][0]

        cgpa = st.sidebar.slider(translate("CGPA/Percentage"), 4.0, 10.0, 7.5, 0.1)

        available_skills = skills_master['skill_name'].tolist() if skills_master is not None else [
            'Python', 'Java', 'Excel', 'Communication', 'Leadership', 'Problem Solving'
        ]
        selected_skills = st.sidebar.multiselect(
            translate("Your Skills (Select multiple)"),
            available_skills,
            default=['Communication', 'Problem Solving']
        )

        # --- Sector Mapping ---
        SECTOR_OPTIONS = {sector: translate(sector) for sector in internships['sector'].unique()}
        sector_choice = st.sidebar.selectbox(translate("Preferred Sector"), list(SECTOR_OPTIONS.values()))
        preferred_sector = [k for k, v in SECTOR_OPTIONS.items() if v == sector_choice][0]

        # --- Location Mapping ---
        LOCATION_OPTIONS = {loc: translate(loc) for loc in internships['location'].unique()}
        location_choice = st.sidebar.selectbox(translate("Preferred Location"), list(LOCATION_OPTIONS.values()))
        preferred_location = [k for k, v in LOCATION_OPTIONS.items() if v == location_choice][0]

        # --- Save Profile ---
        student_profile = {
            'name': name,
            'age': age,
            'education_level': education_level,   # ✅ English value
            'skills': ', '.join(selected_skills),
            'preferred_sector': preferred_sector, # ✅ English value
            'preferred_location': preferred_location  # ✅ English value
        }
        st.session_state.student_profile = student_profile

        # --- Main Internship Recommendation Section ---
        col1, col2 = st.columns([2, 1])
        with col1:
            if st.button(translate("Get Personalized Recommendations"), type="primary"):
                pages = get_recommendations_pages(internships, student_profile)
                if not pages:
                    st.warning(translate("No internships found matching your preferences."))
                    st.session_state.recommendations_pages = []
                    st.session_state.page_index = 0
                else:
                    st.session_state.recommendations_pages = pages
                    st.session_state.page_index = 0

            if st.session_state.get('recommendations_pages', []):
                current_page = st.session_state.recommendations_pages[st.session_state.page_index]
                batch_text = f"{translate('Showing internships batch')} {st.session_state.page_index + 1} {translate('of')} {len(st.session_state.recommendations_pages)}"
                st.success(batch_text)
                for i, (internship, match_score) in enumerate(current_page, 1):
                    st.markdown(f"""
                    <div style="border: 2px solid #e1f5fe; border-radius: 12px; padding: 20px; margin: 15px 0;
                                    background: linear-gradient(135deg, #f8f9ff 0%, #e8f4fd 100%); box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                            <div>
                                <h3 style="color: #1976d2; margin: 0 0 10px 0;">#{i} {translate_dynamic(internship['title'])}</h3>
                                <p style="color: #1976d2; font-size: 17px; margin: 5px 0 2px 0;"><strong>🏢 {translate('Company')}:</strong> <span style='color:#222'>{translate_dynamic(internship['company'])}</span></p>
                                <p style="color: #424242; margin: 5px 0 2px 0;"><strong>🎯 {translate('Sector')}:</strong> <span style='background: #e3f2fd; padding: 3px 8px; border-radius: 12px;'>{translate_dynamic(internship['sector'])}</span></p>
                                <p style="color: #424242; margin: 5px 0 2px 0;"><strong>📍 {translate('Location')}:</strong> {translate_dynamic(internship['location'])}</p>
                                <p style="color: #424242; margin: 5px 0 2px 0;"><strong>⏱ {translate('Duration')}:</strong> {internship['duration_months']} months</p>
                                <p style="color: #424242; margin: 5px 0 2px 0;"><strong>💰 {translate('Stipend')}:</strong> ₹{internship['stipend']:,}/month</p>
                                <p style="color: #424242; margin: 5px 0 2px 0;"><strong>🛠 {translate('Skills Required')}:</strong> {translate_dynamic(internship['required_skills'])}</p>
                                <p style="color: #666; font-size: 14px; margin: 10px 0 0 0;">{translate_dynamic(internship['description'])}</p>
                            </div>
                            <div style="text-align: center; min-width: 100px;">
                                <div style="background: {'#4caf50' if match_score >= 80 else '#ff9800' if match_score >= 60 else '#2196f3'};
                                                color: white; padding: 10px; border-radius: 50%; font-size: 18px; font-weight: bold; margin-bottom: 5px;">
                                    {match_score}%
                                </div>
                                <small style="color: #666;">{translate('Match')}</small>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    col_apply, col_save = st.columns([1, 1])
                    with col_apply:
                        if st.button(translate("Apply Now"), key=f"apply_{st.session_state.page_index}{i}{internship['internship_id']}"):
                            st.session_state.show_application_form = True
                            st.session_state.selected_internship = internship
                            st.rerun()
                    with col_save:
                        already_saved = any(job['title'] == internship['title'] for job in st.session_state.saved_jobs)
                        if st.button(translate("Save"), key=f"save_{st.session_state.page_index}{i}{internship['internship_id']}"):
                            if not already_saved:
                                saved_job = {
                                    'title': internship['title'],
                                    'company': internship['company'],
                                    'sector': internship['sector'],
                                    'location': internship['location'],
                                    'stipend': internship['stipend'],
                                    'saved_date': datetime.now().strftime('%Y-%m-%d')
                                }
                                st.session_state.saved_jobs.append(saved_job)
                                st.success(translate(f"{internship['title']} saved to your wishlist!"))
                            else:
                                st.info(translate("Already saved to your wishlist."))

                if st.button(translate("Browse More Internships"), key=f"browse_main_{st.session_state.page_index}"):
                    st.session_state.page_index = (st.session_state.page_index + 1) % len(st.session_state.recommendations_pages)
                    st.rerun()

        selected_internship = st.session_state.get('selected_internship', None)
        if st.session_state.get('show_application_form', False) and selected_internship is not None:
            show_application_form(selected_internship)
            return

        with col2:
            render_dashboard(internships, it_sector)

    with tab2:
        # IT Courses Section
        show_it_courses(it_sector)

    with tab3:
        # Full Dashboard View
        render_dashboard(internships, it_sector)

    st.markdown("---")
    st.markdown(f"""
    <div style="text-align: center; color: #666; padding: 20px;">
        <p> <strong>{translate('InternPath - Empowering India\'s Youth')}</strong></p>
        <p><em>{translate('Making internship discovery simple for everyone!')}</em></p>
    </div>
    """, unsafe_allow_html=True)

    # Footer with contact information
    def render_contact_footer(email: str = "pminternshiplmtd.gov.in@gmail.com", phone: str = "9392714970"):
        """Render contact footer with email, phone and a 'Click Here' button that opens Gmail compose."""
        st.markdown("---")
        st.markdown("### Contact Us")
        cols = st.columns(2)
        with cols[0]:
            st.markdown("📧 *Email*")
            st.markdown(f"{email}")
            to = urllib.parse.quote(email)
            gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={to}"
            st.markdown(
                f'<div style="margin-top:6px;"><a href="{gmail_url}" target="_blank">'
                f'<button style="padding:8px 12px;border-radius:6px;background:#1a73e8;color:#fff;border:none;">Click Here</button>'
                f'</a></div>',
                unsafe_allow_html=True,
            )
        with cols[1]:
            st.markdown("📞 *Contact*")
            if phone and not phone.startswith("+"):
                tel_link = f"+91{phone}" if len(phone) == 10 else phone
            else:
                tel_link = phone
            st.markdown(f"[{phone}](tel:{tel_link})")
        st.markdown("If you have any queries, feel free to reach out to us.")

    # Ensure footer is rendered when the app runs
    try:
        render_contact_footer()
    except Exception:
        pass

if __name__ == "__main__":
    main()