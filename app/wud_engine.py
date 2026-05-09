import os
from io import BytesIO
from datetime import datetime
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

# ---> LIVE API IMPORT RESTORED <---
from app.core.ai_agent import generate_wud_content

def set_cell_background(cell, hex_color):
    """Helper function to set the background color of a table cell."""
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def create_wud_word(touchpoint_data: dict) -> BytesIO:
    """Generates a native Word doc using pure python-docx with live AWS Bedrock AI."""
    
    # Extract Variables
    td = touchpoint_data.get('techDetails', {})
    wud_id = touchpoint_data.get('id', 'TBD')
    api_name = touchpoint_data.get('name', td.get('apiName', 'Unnamed Integration'))
    target_sys = touchpoint_data.get('target', 'Target System')
    source_sys = touchpoint_data.get('source', 'Source System')
    owner = touchpoint_data.get('owner', 'SDGNext Team')
    business_purpose = touchpoint_data.get('business_purpose', 'No functional requirements listed.')
    
    # Extract specific variables for the AI Prompt
    business_flow_text = touchpoint_data.get('business_flow', business_purpose)
    input_request_text = td.get('apiReq', 'Not provided')
    output_response_text = td.get('apiRes', 'Not provided')
    module_name = touchpoint_data.get('module', 'Unassigned Module')
    crm_location = touchpoint_data.get('crm_location', 'the designated CRM process')

    # ==========================================
    # LIVE AWS BEDROCK AI CALL
    # ==========================================
    ai_content = generate_wud_content(
        api_name=api_name, 
        module_name=module_name, 
        crm_location=crm_location, 
        business_flow=business_flow_text, 
        input_req=input_request_text, 
        output_res=output_response_text
    )
    
    # Initialize Document
    doc = Document()

    # ==========================================
    # GLOBAL TYPOGRAPHY SETTINGS
    # ==========================================
    style_normal = doc.styles['Normal']
    style_normal.font.name = 'Poppins'
    style_normal.font.size = Pt(12)
    if style_normal.font.element.rPr is not None and style_normal.font.element.rPr.rFonts is not None:
        style_normal.font.element.rPr.rFonts.set(qn('w:asciiTheme'), '')
        style_normal.font.element.rPr.rFonts.set(qn('w:hAnsiTheme'), '')

    style_h1 = doc.styles['Heading 1']
    style_h1.font.name = 'Poppins'
    style_h1.font.size = Pt(16)
    style_h1.font.bold = True
    style_h1.font.color.rgb = RGBColor(0, 0, 0)
    if style_h1.font.element.rPr is not None and style_h1.font.element.rPr.rFonts is not None:
        style_h1.font.element.rPr.rFonts.set(qn('w:asciiTheme'), '')
        style_h1.font.element.rPr.rFonts.set(qn('w:hAnsiTheme'), '')

    style_h2 = doc.styles['Heading 2']
    style_h2.font.name = 'Poppins'
    style_h2.font.size = Pt(12)
    style_h2.font.bold = True
    style_h2.font.color.rgb = RGBColor(0, 0, 0)
    if style_h2.font.element.rPr is not None and style_h2.font.element.rPr.rFonts is not None:
        style_h2.font.element.rPr.rFonts.set(qn('w:asciiTheme'), '')
        style_h2.font.element.rPr.rFonts.set(qn('w:hAnsiTheme'), '')

    # ==========================================
    # PAGE 1: TITLE PAGE (Pure Python Layout)
    # ==========================================
    doc.add_paragraph("\n\n") 
    
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    run_api = title_para.add_run(api_name)
    run_api.font.name = 'Poppins'
    run_api.font.size = Pt(16)
    run_api.font.bold = True
    run_api.font.color.rgb = RGBColor(65, 105, 225) # Royal Blue
    run_api.font.underline = True
    
    run_wud = title_para.add_run(f"\nWork Unit Document (WUD ID: {wud_id})")
    run_wud.font.name = 'Poppins'
    run_wud.font.size = Pt(12)
    
    doc.add_paragraph("\n")
    
    img_para = doc.add_paragraph()
    img_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    building_img_path = os.path.join(os.path.dirname(__file__), 'static', 'skyscraper.jpg')
    
    if os.path.exists(building_img_path):
        img_para.add_run().add_picture(building_img_path, width=Inches(6.0))
    else:
        img_para.add_run("[ Skyscraper Image Placeholder - Please save 'skyscraper.jpg' in app/static/ ]")
        
    doc.add_paragraph("\n\n")
    
    footer_para = doc.add_paragraph("Confidential and Proprietary Information")
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_para.runs[0].font.name = 'Poppins'
    footer_para.runs[0].font.size = Pt(12)
    footer_para.runs[0].font.bold = True
    
    logo_para = doc.add_paragraph()
    logo_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    logo_img_path = os.path.join(os.path.dirname(__file__), 'static', 'logo.png')
    
    if os.path.exists(logo_img_path):
        logo_para.add_run().add_picture(logo_img_path, width=Inches(2.5))
    else:
        logo_para.add_run("[ Logo Placeholder - Please save 'logo.png' in app/static/ ]")

    doc.add_page_break()

    # ==========================================
    # PAGE 2: PROPRIETARY INFORMATION
    # ==========================================
    # Custom Pink Heading
    conf_para = doc.add_paragraph()
    conf_run = conf_para.add_run('Confidential and Proprietary')
    conf_run.font.name = 'Poppins'
    conf_run.font.size = Pt(16)
    conf_run.font.color.rgb = RGBColor(225, 29, 72) # Hot Pink/Magenta

    doc.add_paragraph("\n")

    # Copyright Bold
    copy_para = doc.add_paragraph()
    copy_run = copy_para.add_run('Copyright © 2025, Acidaes Solutions Pvt. Ltd. All Rights Reserved.')
    copy_run.font.name = 'Poppins'
    copy_run.font.size = Pt(12)
    copy_run.font.bold = True

    doc.add_paragraph()

    # Body Paragraph 1
    p1 = doc.add_paragraph()
    p1_run = p1.add_run("The management team of Acidaes Solutions Pvt. Limited has prepared this business document and it is being furnished to selected individuals within the customer organization for the sole purpose of proposal evaluation for the sale of BUSINESSNEXT.")
    p1_run.font.name = 'Poppins'
    p1_run.font.size = Pt(12)

    doc.add_paragraph()

    # Body Paragraph 2
    p2 = doc.add_paragraph()
    p2_run = p2.add_run("This document is confidential and contains ideas, concepts, processes, and other information that Acidaes Solutions considers proprietary. Readers are to treat the information contained herein as confidential and may not disseminate; copy or reproduce it in any form without the expressed written permission of Acidaes Solutions Pvt. Limited. ‘Acidaes’, ‘BUSINESSNEXT’, ‘Simplifying Technology’ and ‘business efficiency, on demand’ are applied trademarks of Acidaes Solutions Pvt. Ltd. All other trademarks are the property of their respective owners.")
    p2_run.font.name = 'Poppins'
    p2_run.font.size = Pt(12)

    doc.add_page_break()

    # ==========================================
    # PAGE 3: VERSION CONTROL
    # ==========================================
    vc_title = doc.add_paragraph()
    vc_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    vc_title_run = vc_title.add_run('Version Control')
    vc_title_run.font.name = 'Poppins'
    vc_title_run.font.size = Pt(14)
    
    doc.add_paragraph()

    vc_table = doc.add_table(rows=2, cols=5)
    vc_table.style = 'Table Grid'
    vc_headers = ["Sr. No.", "Date", "Version", "Description", "Author"]
    
    # Format Headers (Poppins 11pt Bold, Light Gray Background)
    for i, header in enumerate(vc_headers):
        cell = vc_table.rows[0].cells[i]
        set_cell_background(cell, "D9D9D9") # Light Gray Hex Color
        
        cell.text = "" 
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = para.add_run(header)
        run.font.name = 'Poppins'
        run.font.size = Pt(11)
        run.font.bold = True
        
    # Format Data (Poppins 11pt Normal)
    vc_data = ["1", datetime.now().strftime("%d-%m-%Y"), "1.0", f"{api_name}", owner]
    for i, text in enumerate(vc_data):
        cell = vc_table.rows[1].cells[i]
        cell.text = ""
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = para.add_run(text)
        run.font.name = 'Poppins'
        run.font.size = Pt(11)

    doc.add_page_break()

    # ==========================================
    # PAGE 4+: MAIN CONTENT
    # ==========================================
    doc.add_heading('1. Introduction', level=1)
    
    # ---> INJECTING LIVE AI INTRODUCTION <---
    intro_para = doc.add_paragraph()
    intro_run = intro_para.add_run(ai_content.get('introduction', 'Introduction could not be generated.'))
    intro_run.font.name = 'Poppins'
    intro_run.font.size = Pt(12)

    doc.add_heading(f'2. {api_name}', level=1)
    doc.add_paragraph(f"Source System: - {source_sys}", style='List Bullet')
    doc.add_paragraph(f"Target System: - {target_sys}", style='List Bullet')

    doc.add_heading('2.1. Technical Details', level=2)
    
    tech_details_para = doc.add_paragraph()
    tech_details_run = tech_details_para.add_run("Following are the technical details:")
    tech_details_run.font.name = 'Poppins'
    tech_details_run.font.size = Pt(10)
    
    table_data = [
        ("WUD ID", str(wud_id)),
        ("Source System", source_sys),
        ("Target System", target_sys),
        ("Owner", owner),
        ("Authentication", td.get('apiAuth', 'N/A')),
        ("Periodicity", "On Demand"),
        ("Interface", "API"),
        ("Methodology", td.get('apiMethod', 'NA')),
        ("API Type", td.get('apiType', 'RESTFUL')),
        ("EDS Name", api_name),
        ("Input Request Payload", td.get('apiReq', 'NA')),
        ("Output Response Payload", td.get('apiRes', 'NA')),
        ("Failure Response", "If Invalid Response is passed it will display respective error messages in response."),
        
        # ---> INJECTING LIVE AI TABLE DATA <---
        ("Expected Output", ai_content.get('expected_output', 'NA')), 
        ("Macro Logic", ai_content.get('macro_logic', 'NA')),
        
        ("Testing Strategy", "EDS will be tested as a part of functional scenario testing.\nExplicit testing can be performed through the Widget."),
        ("Watchouts", "For unhandled exceptions, application user needs to contact application administrator.\nService must be accessible from target environments.")
    ]

    tech_table = doc.add_table(rows=1, cols=2)
    tech_table.style = 'Table Grid'
    tech_table.autofit = False
    
    for i, (key, val) in enumerate(table_data):
        if i == 0:
            row = tech_table.rows[0] 
        else:
            row = tech_table.add_row()
            
        row.cells[0].width = Inches(2.0)
        row.cells[1].width = Inches(4.5)
            
        row.cells[0].text = "" 
        run_left = row.cells[0].paragraphs[0].add_run(key)
        run_left.font.name = 'Poppins'
        run_left.font.size = Pt(11)
        run_left.font.bold = True
        
        val_str = str(val) if val else "NA"
        row.cells[1].text = "" 
        run_right = row.cells[1].paragraphs[0].add_run(val_str)
        run_right.font.name = 'Poppins'
        run_right.font.size = Pt(11)

    doc.add_paragraph("\n")
    doc.add_heading('CONCLUSION', level=1)
    doc.add_paragraph(f"This WUD document formalizes the technical execution plan for the {api_name} integration.")

    word_buffer = BytesIO()
    doc.save(word_buffer)
    word_buffer.seek(0)
    
    return word_buffer