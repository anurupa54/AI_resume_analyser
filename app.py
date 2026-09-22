from flask import Flask, render_template, request, send_file
from pypdf import PdfReader
from docx import Document
import os
import re
import sqlite3
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
app = Flask(__name__)
DATABASE = "resume_analyzer.db"


def get_role_data(role):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Get role ID
    cursor.execute(
        "SELECT role_id FROM roles WHERE role_name = ?",
        (role,)
    )

    result = cursor.fetchone()

    if not result:
        conn.close()
        return [], []

    role_id = result[0]

    # Get skills
    cursor.execute(
        "SELECT skill_name FROM role_skills WHERE role_id = ?",
        (role_id,)
    )

    skills = [row[0] for row in cursor.fetchall()]

    # Get ATS keywords
    cursor.execute(
        "SELECT keyword FROM ats_keywords WHERE role_id = ?",
        (role_id,)
    )

    keywords = [row[0] for row in cursor.fetchall()]

    conn.close()

    return skills, keywords

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# --------------------------------
# Extract text from PDF
# --------------------------------
def extract_pdf_text(filepath):

    reader = PdfReader(filepath)

    text = ""

    for page in reader.pages:

        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

    return text


# --------------------------------
# Extract text from DOCX
# --------------------------------
def extract_docx_text(filepath):

    document = Document(filepath)

    text = ""

    for paragraph in document.paragraphs:

        text += paragraph.text + "\n"

    return text


# --------------------------------
# Detect resume sections
# --------------------------------
def detect_sections(text):

    text_upper = text.upper()

    sections = {

        "Profile / Summary": [
            "PROFILE",
            "SUMMARY",
            "PROFESSIONAL SUMMARY",
            "OBJECTIVE"
        ],

        "Experience": [
            "PROFESSIONAL EXPERIENCE",
            "WORK EXPERIENCE",
            "EXPERIENCE",
            "EMPLOYMENT"
        ], 

        "Contact Information": [
             "CONTACT",
             "EMAIL",
             "PHONE",
             "MOBILE",
             "LINKEDIN",
             "GITHUB" ],

        "Education": [
            "EDUCATION",
            "ACADEMIC QUALIFICATIONS",
            "EDUCATIONAL QUALIFICATIONS"
        ],

        "Skills": [
            "SKILLS",
            "TECHNICAL SKILLS",
            "CORE SKILLS"
        ],

        "Projects": [
            "PROJECTS",
            "ACADEMIC PROJECTS",
            "PERSONAL PROJECTS"
        ],

        "Certifications": [
            "CERTIFICATIONS",
            "CERTIFICATES"
        ]
    }

    detected = {}

    for section, keywords in sections.items():

        found = False

        for keyword in keywords:

            if keyword in text_upper:
                found = True
                break

        detected[section] = found

    return detected


# --------------------------------
# Calculate section score
# --------------------------------
def calculate_score(sections):

    score = 0

    for present in sections.values():

        if present:
            score += 100 / len(sections)

    return round(score)


# --------------------------------
# Clean extracted text
# --------------------------------
def clean_text(text):

    text = text.replace("§", "•")

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# --------------------------------
# Check skills against resume
# --------------------------------
def match_skills(resume_text, role):
    # Get skills from the database
    role_skills, _ = get_role_data(role)

    resume_text = resume_text.lower()

    matched_skills = []
    missing_skills = []

    for skill in role_skills:
        if skill.lower() in resume_text:
            matched_skills.append(skill)
        else:
            missing_skills.append(skill)

    if len(role_skills) > 0:
        skill_score = round(
            (len(matched_skills) / len(role_skills)) * 100
        )
    else:
        skill_score = 0

    return matched_skills, missing_skills, skill_score
def analyze_ats_keywords(resume_text, role):
    # Get ATS keywords from the database
    _, keywords = get_role_data(role)

    resume_text = resume_text.lower()

    matched_keywords = []
    missing_keywords = []

    for keyword in keywords:
        if keyword.lower() in resume_text:
            matched_keywords.append(keyword)
        else:
            missing_keywords.append(keyword)

    if len(keywords) > 0:
        ats_score = round(
            (len(matched_keywords) / len(keywords)) * 100
        )
    else:
        ats_score = 0

    return matched_keywords, missing_keywords, ats_score
# --------------------------------
# Generate recommendations
# --------------------------------
def generate_recommendations(sections, missing_skills, role):

    recommendations = []

    # Missing sections
    if not sections["Education"]:
        recommendations.append(
            "Add an Education section to your resume."
        )

    if not sections["Contact Information"]:
        recommendations.append(
            "Add your contact information, such as email, phone, LinkedIn, or GitHub."
        )

    if not sections["Projects"]:
        recommendations.append(
            "Add relevant projects related to your target role."
        )

    if not sections["Experience"]:
        recommendations.append(
            "Add internship or relevant work experience if you have any."
        )

    if not sections["Certifications"]:
        recommendations.append(
            "Add relevant certifications if you have completed any."
        )

    if not sections["Skills"]:
        recommendations.append(
            "Add a dedicated Skills section."
        )
        # Resume formatting and structure feedback
    if not all(sections.values()):
        recommendations.append(
            "Improve resume formatting and structure by organizing all important sections clearly."
       )

    # Missing skills
    if missing_skills:

        for skill in missing_skills[:3]:

            recommendations.append(
                f"Consider adding {skill} if you have experience with it."
            )

    # If everything is present
    if not recommendations:

        recommendations.append(
            f"Your resume covers the main sections and skills "
            f"for the {role} role."
        )

    return recommendations

# --------------------------------
# Home page
# --------------------------------
@app.route("/")
def home():

    return render_template("index.html")


# --------------------------------
# Analyze resume
# --------------------------------
def generate_pdf_report(
    filepath,
    role,
    overall_score,
    score,
    skill_score,
    ats_score,
    matched_skills,
    missing_skills,
    matched_keywords,
    missing_keywords,
    recommendations
):
    report_folder = "reports"

    if not os.path.exists(report_folder):
        os.makedirs(report_folder)

    filename = os.path.splitext(
        os.path.basename(filepath)
    )[0] + "_analysis.pdf"

    report_path = os.path.join(
        report_folder,
        filename
    )

    pdf = canvas.Canvas(report_path, pagesize=letter)

    width, height = letter
    y = height - 50

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, y, "Smart Resume Analyzer")

    y -= 30

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, "Resume Analysis Report")

    y -= 35

    pdf.setFont("Helvetica", 11)

    pdf.drawString(50, y, f"Target Role: {role}")
    y -= 20

    pdf.drawString(
        50,
        y,
        f"Overall Resume Score: {overall_score}/100"
    )
    y -= 20

    pdf.drawString(
        50,
        y,
        f"Resume Completeness: {score}/100"
    )
    y -= 20

    pdf.drawString(
        50,
        y,
        f"Skill Match: {skill_score}%"
    )
    y -= 20

    pdf.drawString(
        50,
        y,
        f"ATS Compatibility: {ats_score}%"
    )

    y -= 35

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Matched Skills")

    y -= 20
    pdf.setFont("Helvetica", 10)

    for skill in matched_skills:
        pdf.drawString(60, y, f"- {skill}")
        y -= 15

    y -= 10

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Missing Skills")

    y -= 20
    pdf.setFont("Helvetica", 10)

    for skill in missing_skills:
        pdf.drawString(60, y, f"- {skill}")
        y -= 15

    y -= 10

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Matched ATS Keywords")

    y -= 20
    pdf.setFont("Helvetica", 10)

    for keyword in matched_keywords:
        pdf.drawString(60, y, f"- {keyword}")
        y -= 15

    y -= 10

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Missing ATS Keywords")

    y -= 20
    pdf.setFont("Helvetica", 10)

    for keyword in missing_keywords:
        pdf.drawString(60, y, f"- {keyword}")
        y -= 15

    y -= 10

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Smart Recommendations")

    y -= 20
    pdf.setFont("Helvetica", 10)

    for recommendation in recommendations:
        pdf.drawString(60, y, f"- {recommendation}")
        y -= 15

        if y < 50:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 10)

    pdf.save()

    return report_path
@app.route("/analyze", methods=["POST"])
def analyze():

    resume = request.files.get("resume")

    role = request.form.get("role")


    # Check file
    if not resume or resume.filename == "":

        return "Please upload a resume."


    # Save file
    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        resume.filename
    )

    resume.save(filepath)


    # Get extension
    extension = resume.filename.lower().split(".")[-1]


    # Extract text
    if extension == "pdf":

        resume_text = extract_pdf_text(filepath)

    elif extension == "docx":

        resume_text = extract_docx_text(filepath)

    else:

        return "Only PDF and DOCX files are supported."


    # Check extracted text
    if not resume_text.strip():

        return "Could not extract text from this resume."


    # Clean text
    resume_text = clean_text(resume_text)


    # Detect sections
    sections = detect_sections(resume_text)


    # Section score
    score = calculate_score(sections)


    # Match skills
    matched_skills, missing_skills, skill_score = match_skills(
        resume_text,
        role
    )
    # Analyze ATS keywords
    matched_keywords, missing_keywords, ats_score = analyze_ats_keywords(
        resume_text, role
    )
    # Generate recommendations
    recommendations = generate_recommendations(
        sections,
        missing_skills,
        role
    )
    # Calculate overall score
    overall_score = round(
        (score * 0.3) +
        (skill_score * 0.4) +
        (ats_score * 0.3)
)     # Generate PDF report
    report_path = generate_pdf_report(
        filepath,
        role,
        overall_score,
        score,
        skill_score,
        ats_score,
        matched_skills,
        missing_skills,
        matched_keywords,
        missing_keywords,
        recommendations
    )

    return render_template(
        "results.html",
        filename=resume.filename,
        role=role,
        score=score,
        overall_score=overall_score,
        sections=sections,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        skill_score=skill_score,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        ats_score=ats_score,
        recommendations=recommendations,
        resume_text=resume_text,
        report_path=report_path,
        report_filename=os.path.basename(report_path),
    )

@app.route("/download-report/<filename>")
def download_report(filename):
    report_path = os.path.join("reports", filename)

    if not os.path.exists(report_path):
        return "Report not found", 404

    return send_file(
        report_path,
        as_attachment=True
    )
if __name__ == "__main__":
    app.run(debug=True)