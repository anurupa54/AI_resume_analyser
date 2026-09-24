from flask import Flask, render_template, request, send_file
from pypdf import PdfReader
from docx import Document
import os
import re
import sqlite3
import spacy
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak
)
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import inch
app = Flask(__name__)
DATABASE = "resume_analyzer.db"
nlp = spacy.blank("en")


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
    "PROFESSIONAL PROFILE",
    "PROFILE SUMMARY",
    "ABOUT ME",
    "CAREER OBJECTIVE",
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
def preprocess_with_spacy(text):
    doc = nlp(text)

    tokens = [
        token.text.lower()
        for token in doc
        if not token.is_stop and not token.is_punct and not token.is_space
    ]

    return tokens   


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
    recommendations,
    sections=None
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

    # --------------------------------
    # PDF document setup
    # --------------------------------
    doc = SimpleDocTemplate(
        report_path,
        pagesize=letter,
        rightMargin=45,
        leftMargin=45,
        topMargin=50,
        bottomMargin=45
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        alignment=TA_CENTER,
        spaceAfter=8
    )

    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=20
    )

  
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=17,
        textColor=colors.HexColor("#111111"),
        spaceBefore=3,
        spaceAfter=4
    )

    normal_style = ParagraphStyle(
        "NormalText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=11,
        textColor=colors.HexColor("#222222"),
        spaceBefore=0,
        spaceAfter=0
    )

    small_style = ParagraphStyle(
        "SmallText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=10,
        textColor=colors.HexColor("#444444"),
        spaceBefore=0,
        spaceAfter=0
    )

    score_style = ParagraphStyle(
        "Score",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#111111"),
        spaceBefore=0,
        spaceAfter=0
    )

    badge_style = ParagraphStyle(
        "Badge",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=10,
        alignment=TA_CENTER,
        spaceBefore=0,
        spaceAfter=0
    )
    story = []

    # --------------------------------
    # Header
    # --------------------------------
    story.append(
        Paragraph(
            "Smart Resume Analyzer",
            title_style
        )
    )

    story.append(
        Paragraph(
            "Resume Analysis Report",
            subtitle_style
        )
    )

    # --------------------------------
    # Resume information
    # --------------------------------
    resume_name = os.path.basename(filepath)

    info_data = [
        [
            Paragraph("<b>Resume File</b>", normal_style),
            Paragraph(resume_name, normal_style)
        ],
        [
            Paragraph("<b>Target Role</b>", normal_style),
            Paragraph(role, normal_style)
        ]
    ]

    info_table = Table(
        info_data,
        colWidths=[1.5 * inch, 5.4 * inch]
    )

    info_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f3f3")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#222222")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8)
        ])
    )

    story.append(info_table)
    story.append(Spacer(1, 7))

    # --------------------------------
    # Overall score
    # --------------------------------
    story.append(
        Paragraph(
            "Overall Resume Score",
            section_style
        )
    )

    overall_table = Table(
        [
            [
                Paragraph(
                    f"{overall_score}/100",
                    score_style
                )
            ]
        ],
        colWidths=[6.9 * inch],
        rowHeights=[0.75 * inch]
    )

    overall_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff3b0")),
            ("BOX", (0, 0), (-1, -1), 2, colors.HexColor("#111111")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER")
        ])
    )

    story.append(overall_table)
    story.append(Spacer(1, 15))

    # --------------------------------
    # Score breakdown
    # --------------------------------
    story.append(
        Paragraph(
            "Score Breakdown",
            section_style
        )
    )

    score_data = [
        [
            Paragraph("<b>Resume Completeness</b>", small_style),
            Paragraph("<b>Skill Match</b>", small_style),
            Paragraph("<b>ATS Compatibility</b>", small_style)
        ],
        [
            Paragraph(f"{score}/100", score_style),
            Paragraph(f"{skill_score}%", score_style),
            Paragraph(f"{ats_score}%", score_style)
        ]
    ]

    score_table = Table(
        score_data,
        colWidths=[
            2.3 * inch,
            2.3 * inch,
            2.3 * inch
        ],
        rowHeights=[0.35 * inch, 0.6 * inch]
    )

    score_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f3f3")),
            ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#222222")),
            ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#cccccc")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7)
        ])
    )

    story.append(score_table)

    # --------------------------------
    # Page 2 - Skills and ATS
    # --------------------------------
    story.append(PageBreak())

    story.append(
        Paragraph(
            "Skills Analysis",
            section_style
        )
    )

    story.append(
        Paragraph(
            "<b>Matched Skills</b>",
            normal_style
        )
    )

    if matched_skills:
        matched_text = " • ".join(matched_skills)
    else:
        matched_text = "No matching skills found."

    story.append(
        Paragraph(
            matched_text,
            small_style
        )
    )

    story.append(Spacer(1, 6))

    story.append(
        Paragraph(
            "<b>Missing Skills</b>",
            normal_style
        )
    )

    if missing_skills:
        missing_text = " • ".join(missing_skills)
    else:
        missing_text = "No major missing skills detected."

    story.append(
        Paragraph(
            missing_text,
            small_style
        )
    )

    story.append(Spacer(1, 10))

    # --------------------------------
    # ATS Analysis
    # --------------------------------
    story.append(
        Paragraph(
            "ATS Keyword Analysis",
            section_style
        )
    )

    story.append(
        Paragraph(
            "<b>Matched ATS Keywords</b>",
            normal_style
        )
    )

    if matched_keywords:
        matched_keyword_text = " • ".join(matched_keywords)
    else:
        matched_keyword_text = "No matching keywords found."

    story.append(
        Paragraph(
            matched_keyword_text,
            small_style
        )
    )

    story.append(Spacer(1, 6))

    story.append(
        Paragraph(
            "<b>Missing ATS Keywords</b>",
            normal_style
        )
    )

    if missing_keywords:
        missing_keyword_text = " • ".join(missing_keywords)
    else:
        missing_keyword_text = "No major missing keywords detected."

    story.append(
        Paragraph(
            missing_keyword_text,
            small_style
        )
    )

    # --------------------------------
    # Page 3 - Resume Sections
    # --------------------------------
    story.append(PageBreak())

    story.append(
        Paragraph(
            "Resume Sections",
            section_style
        )
    )

    section_data = [
        [
            Paragraph("<b>Resume Section</b>", small_style),
            Paragraph("<b>Status</b>", small_style)
        ]
    ]

    if sections:
        for section_name, present in sections.items():

            status = "Present" if present else "Missing"

            section_data.append(
                [
                    Paragraph(section_name, small_style),
                    Paragraph(status, badge_style)
                ]
            )
    else:
        section_data.append(
            [
                Paragraph(
                    "Section information unavailable",
                    small_style
                ),
                Paragraph("-", badge_style)
            ]
        )

    section_table = Table(
        section_data,
        colWidths=[5.2 * inch, 1.7 * inch],
        repeatRows=1
    )

    section_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f3f3")),
            ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#222222")),
            ("INNERGRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 1), (1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9)
        ])
    )

    # Add status backgrounds
    if sections:
        for row_number, (section_name, present) in enumerate(
            sections.items(),
            start=1
        ):
            if present:
                section_table.setStyle(
                    TableStyle([
                        (
                            "BACKGROUND",
                            (1, row_number),
                            (1, row_number),
                            colors.HexColor("#b9f6c5")
                        )
                    ])
                )
            else:
                section_table.setStyle(
                    TableStyle([
                        (
                            "BACKGROUND",
                            (1, row_number),
                            (1, row_number),
                            colors.HexColor("#ffb4c9")
                        )
                    ])
                )

    story.append(section_table)

    story.append(Spacer(1, 10))

    # --------------------------------
    # Smart Recommendations
    # --------------------------------
    story.append(
        Paragraph(
            "Smart Recommendations",
            section_style
        )
    )

    if recommendations:
        for number, recommendation in enumerate(
            recommendations,
            start=1
        ):
            story.append(
                Paragraph(
                    f"<b>{number}.</b> {recommendation}",
                    small_style
                )
            )
            story.append(Spacer(1, 4))
    else:
        story.append(
            Paragraph(
                "No additional recommendations.",
                small_style
            )
        )

    # --------------------------------
    # Footer
    # --------------------------------
    def add_footer(canvas_obj, document):
        canvas_obj.saveState()

        canvas_obj.setFont(
            "Helvetica",
            8
        )

        canvas_obj.setFillColor(
            colors.HexColor("#666666")
        )

        canvas_obj.drawCentredString(
            letter[0] / 2,
            25,
            f"Smart Resume Analyzer  •  Page {document.page}"
        )

        canvas_obj.restoreState()

    # Build PDF
    doc.build(
        story,
        onFirstPage=add_footer,
        onLaterPages=add_footer
    )

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

    spacy_tokens = preprocess_with_spacy(resume_text)
    spacy_token_count = len(spacy_tokens)

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
)  # Generate PDF report
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
        recommendations,
        sections
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
        spacy_token_count=spacy_token_count
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